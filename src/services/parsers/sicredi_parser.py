# -*- coding: utf-8 -*-
"""
Parser Dedicado: Sicredi (Cooperativa de Crédito)
Trata particularidades como:
- CSVs com delimitador ';' e codificações Windows-1252 / Latin-1 / UTF-8.
- Prefixos típicos: PIX ENVIADO, PIX RECEBIDO, COMPRA CARTAO DEB, PGTO TITULO, etc.
- Atribuição automática de 'Sicredi' para Conta debitada / creditada.
"""
import io
import re
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.services.ingestion_parser import (
    normalize_expense_category,
    normalize_income_category,
    infer_nature_and_essentiality
)
from src.services.deduplication import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.sicredi")

class SicrediParser(BaseBankParser):
    institution_name: str = "Sicredi"
    guidelines: str = "No Internet Banking Sicredi ou App Mobile, exporte o extrato no formato .OFX ou .CSV de Conta Corrente."

    def _clean_sicredi_description(self, memo: str) -> tuple[str, str]:
        """
        Limpa prefixos operacionais do Sicredi e identifica forma de pagamento.
        Retorna (descricao_limpa, forma_pagamento).
        """
        raw = memo.strip()
        forma = "Conta corrente"

        # Identificação da forma de pagamento
        if re.search(r'\bPIX\b', raw, re.IGNORECASE):
            forma = "Pix"
        elif re.search(r'\b(CARTAO|COMPRA CARTAO|DEB)\b', raw, re.IGNORECASE):
            forma = "Débito"
        elif re.search(r'\b(TITULO|BOLETO|CONVENIO)\b', raw, re.IGNORECASE):
            forma = "Boleto"
        elif re.search(r'\b(TED|DOC|TRANSF)\b', raw, re.IGNORECASE):
            forma = "Transferência"

        # Limpeza de prefixos frequentes do Sicredi
        cleaned = re.sub(
            r'^(PIX\s+ENVIADO\s*-\s*|PIX\s+RECEBIDO\s*-\s*|COMPRA\s+CARTAO\s+DEB\s*-\s*|PGTO\s+TITULO\s*-\s*|TRANSF\s+ENTRE\s+CONTAS\s*-\s*)',
            '',
            raw,
            flags=re.IGNORECASE
        ).strip()

        return cleaned if cleaned else raw, forma

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        """
        Processa extrato CSV emitido pelo Sicredi.
        """
        df_raw = None
        for enc in ["latin1", "cp1252", "utf-8-sig", "utf-8"]:
            try:
                sample = file_bytes[:4096].decode(enc, errors="ignore")
                sep = ";" if sample.count(";") >= sample.count(",") else ","
                temp = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, dtype=str)
                if temp.shape[1] >= 2 and not temp.empty:
                    df_raw = temp
                    break
            except Exception:
                continue

        if df_raw is None or df_raw.empty:
            return self.empty_dataframe()

        cols_map = {str(col).strip(): str(col).lower().strip() for col in df_raw.columns}
        date_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["data", "dt"])), None)
        desc_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["descricao", "descrição", "historico", "histórico", "memo"])), None)
        val_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["valor", "amount"]) and "saldo" not in low), None)
        tipo_col = next((orig for orig, low in cols_map.items() if low in ["tipo", "c/d"]), None)

        if not val_col:
            # Fallback genérico para CSV
            from src.services.ingestion_parser import parse_csv as generic_parse_csv
            df_fallback = generic_parse_csv(file_bytes, filename=filename)
            df_fallback["Conta debitada"] = df_fallback.apply(lambda r: "Sicredi" if r.get("Tipo") == "Despesa" else "", axis=1)
            df_fallback["Conta creditada"] = df_fallback.apply(lambda r: "Sicredi" if r.get("Tipo") == "Receita" else "", axis=1)
            return df_fallback

        records = []
        for _, row in df_raw.iterrows():
            d_val = str(row[date_col]).strip() if date_col and pd.notna(row[date_col]) else ""
            desc_val = str(row[desc_col]).strip() if desc_col and pd.notna(row[desc_col]) else "Lançamento Sicredi"
            v_raw = str(row[val_col]).strip() if val_col and pd.notna(row[val_col]) else "0"
            t_raw = str(row[tipo_col]).strip().upper() if tipo_col and pd.notna(row[tipo_col]) else ""

            if not d_val or not v_raw or v_raw in ("0", "0,00", "0.00"):
                continue

            dt_obj = pd.to_datetime(d_val, dayfirst=True, errors="coerce")
            if pd.isna(dt_obj):
                continue

            # Valores do Sicredi com ponto/vírgula
            is_negative = "-" in v_raw or "D" in t_raw or "DEBITO" in t_raw or "DÉBITO" in t_raw
            is_credit = "+" in v_raw or "C" in t_raw or "CREDITO" in t_raw or "CRÉDITO" in t_raw

            v_clean = re.sub(r"[R\$\s\xa0\+\-]", "", v_raw).strip()
            if "," in v_clean and "." in v_clean:
                if v_clean.find(",") > v_clean.find("."):
                    v_clean = v_clean.replace(".", "").replace(",", ".")
                else:
                    v_clean = v_clean.replace(",", "")
            elif "," in v_clean:
                v_clean = v_clean.replace(",", ".")

            try:
                val_float = float(v_clean)
            except ValueError:
                continue

            # Limpeza de descrição e identificação da forma
            cleaned_desc, forma_pagto = self._clean_sicredi_description(desc_val)

            # Determinação de Tipo
            if is_negative:
                tipo = "Despesa"
            elif is_credit:
                tipo = "Receita"
            elif "recebido" in desc_val.lower() or "cred" in desc_val.lower():
                tipo = "Receita"
            else:
                tipo = "Despesa"

            if tipo == "Receita":
                categoria = normalize_income_category(cleaned_desc)
                conta_cred = "Sicredi"
                conta_deb = ""
            else:
                categoria = normalize_expense_category(cleaned_desc)
                conta_cred = ""
                conta_deb = "Sicredi"

            fixo_var, essencial = infer_nature_and_essentiality(categoria, cleaned_desc)

            records.append({
                "Data": dt_obj.date(),
                "Descricao": cleaned_desc,
                "Valor": abs(val_float),
                "Categoria": categoria,
                "Tipo": tipo,
                "Conta creditada": conta_cred,
                "Conta debitada": conta_deb,
                "Fixo vs. Variável": fixo_var,
                "Essencial vs. Não Essencial": essencial,
                "Forma_Pagamento": forma_pagto
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = self.empty_dataframe()
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        """
        Processa arquivo OFX do Sicredi garantindo marcação de contas Sicredi e limpeza de memo.
        """
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "sicredi.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "Sicredi" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "Sicredi" if r.get("Tipo") == "Receita" else "", axis=1)
            # Refina descrições retirando prefixos
            df["Descricao"] = df["Descricao"].apply(lambda d: self._clean_sicredi_description(str(d))[0])
        return df
