# -*- coding: utf-8 -*-
"""
Parser Dedicado: Vuon Card
Particularidades: Faturas em PDF do cartão Vuon Card (Supermercado Comper / Fort Atacadista).
Extrai automaticamente compras à vista, parcelas (ex: HIPER COMPER 360 YPE 1/2) e tarifas.
"""
import io
import re
import datetime
from typing import Any
import pandas as pd
import pypdf

from src.services.parsers.base_parser import BaseBankParser, STANDARD_COLUMNS
from src.services.ingestion_parser import (
    normalize_expense_category,
    infer_nature_and_essentiality
)
from src.services.deduplication import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.vuon")


class VuonCardParser(BaseBankParser):
    institution_name: str = "Vuon Card"
    guidelines: str = "Envie a fatura em PDF do Vuon Card (Comper / Fort Atacadista). O sistema extrai automaticamente compras, parcelas e tarifas."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        df = generic_parse_csv(file_bytes=file_bytes, filename=filename or "vuon.csv")
        if not df.empty:
            df["Conta debitada"] = "Vuon Card"
            df["Forma_Pagamento"] = "Cartão de crédito"
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "vuon.ofx")
        if not df.empty:
            df["Conta debitada"] = "Vuon Card"
            df["Forma_Pagamento"] = "Cartão de crédito"
        return df

    def parse_pdf(self, file_bytes: bytes, filename: str = "", password: str = "") -> pd.DataFrame:
        """
        Processa faturas em PDF emitidas pelo Vuon Card.
        Analisa as páginas procurando a tabela de lançamentos com o formato:
        Data Descrição Origem Valor (ex: 03/09/2026 HIPER COMPER 360 YPE 1/2 PAULO H GONCALVES REZENDE R$ 142,91+)
        """
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                if password:
                    reader.decrypt(password)
                else:
                    reader.decrypt("")
        except Exception as e:
            logger.error(f"Erro ao abrir PDF do Vuon Card: {e}")
            return self.empty_dataframe()

        records = []
        # 1. Extração da data de vencimento da fatura (DD/MM/AAAA)
        data_vencimento = None
        for p in reader.pages:
            try:
                txt_p = p.extract_text() or ""
                m_venc = re.search(r'Vencimento\s*\n?\s*(\d{2}/\d{2}/\d{4})', txt_p, re.IGNORECASE)
                if m_venc:
                    data_vencimento = datetime.datetime.strptime(m_venc.group(1), "%d/%m/%Y").date()
                    break
            except Exception:
                continue

        if not data_vencimento:
            data_vencimento = datetime.date.today()

        # Linha padrão de lançamentos: 03/09/2026 HIPER COMPER 360 YPE 1/2 PAULO H GONCALVES REZENDE R$ 142,91+
        line_pattern = re.compile(
            r"^(\d{2}/\d{2}/\d{4})\s+(.*?)\s+R\$\s*([0-9.,]+)([+-])$"
        )

        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                continue

            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            for line in lines:
                m = line_pattern.match(line)
                if not m:
                    continue

                dt_str, desc_raw, val_str, sign = m.groups()

                # Ignora saldo anterior e pagamento de fatura anterior
                desc_upper = desc_raw.upper()
                if "SALDO FATURA ANTERIOR" in desc_upper or "PAGAMENTO EM BANCO" in desc_upper or "PAGAMENTO DE FATURA" in desc_upper:
                    continue

                try:
                    valor = float(val_str.replace(".", "").replace(",", "."))
                except Exception:
                    valor = 0.0

                if valor <= 0:
                    continue

                # Remove o nome do titular no final da descrição se houver (ex: PAULO H GONCALVES REZENDE)
                desc_clean = re.sub(r"\s+PAULO\s+H.*$", "", desc_raw, flags=re.IGNORECASE).strip()
                desc_clean = re.sub(r"\s+FATURA\s+ANTERIOR$", "", desc_clean, flags=re.IGNORECASE).strip()

                # Se não for tarifa, anexa a tag (Compra: DD/MM) para manter o padrão das faturas de cartão
                desc_lower = desc_clean.lower()
                is_tarifa = "tarifa" in desc_lower or "anuidade" in desc_lower or "manutencao" in desc_lower or "manutenção" in desc_lower
                if not is_tarifa and len(dt_str) >= 5:
                    d_c, m_c = dt_str[:2], dt_str[3:5]
                    display_desc = f"{desc_clean} (Compra: {d_c}/{m_c})"
                else:
                    display_desc = desc_clean

                # Tipo: se '+' é despesa na fatura do cartão
                tipo = "Despesa" if sign == "+" else "Receita"

                # Categoria
                if "comper" in desc_lower or "fort" in desc_lower or "supermercado" in desc_lower or "hiper" in desc_lower:
                    cat = "Supermercado"
                elif is_tarifa:
                    cat = "Serviços / Manutenção"
                else:
                    cat = normalize_expense_category(desc_clean)

                fixo_var, essencial = infer_nature_and_essentiality(cat, display_desc)

                records.append({
                    "Data": data_vencimento,
                    "Descricao": display_desc,
                    "Valor": valor,
                    "Categoria": cat,
                    "Tipo": tipo,
                    "Conta creditada": "" if tipo == "Despesa" else "Vuon Card",
                    "Conta debitada": "Vuon Card" if tipo == "Despesa" else "",
                    "Fixo vs. Variável": fixo_var,
                    "Essencial vs. Não Essencial": essencial,
                    "Forma_Pagamento": "Cartão de crédito"
                })

        if not records:
            logger.warning(f"Nenhum lançamento identificado no PDF Vuon Card: {filename}")
            return self.empty_dataframe()

        df = pd.DataFrame(records)
        df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        logger.info(f"Vuon Card processou com sucesso {len(df)} transações do PDF '{filename}'.")
        return df[STANDARD_COLUMNS]

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """
        Se enviado como print/comprovante na aba de imagens, executa OCR Tesseract.
        """
        try:
            import pytesseract
            from PIL import Image
            image = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(image, lang="por")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            records = []
            line_pattern = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.*?)\s+R\$\s*([0-9.,]+)([+-])?$")
            for line in lines:
                m = line_pattern.match(line)
                if m:
                    dt_str, desc_raw, val_str, _ = m.groups()
                    desc_clean = re.sub(r"\s+PAULO\s+H.*$", "", desc_raw, flags=re.IGNORECASE).strip()
                    try:
                        dt_obj = datetime.datetime.strptime(dt_str, "%d/%m/%Y").date()
                        val = float(val_str.replace(".", "").replace(",", "."))
                    except Exception:
                        continue
                    cat = "Supermercado" if "comper" in desc_clean.lower() else "Outros"
                    records.append({
                        "Data": dt_obj,
                        "Descricao": desc_clean,
                        "Valor": val,
                        "Categoria": cat,
                        "Tipo": "Despesa",
                        "Conta creditada": "",
                        "Conta debitada": "Vuon Card",
                        "Fixo vs. Variável": "Variável",
                        "Essencial vs. Não Essencial": "Essencial",
                        "Forma_Pagamento": "Cartão de crédito"
                    })
            if records:
                df = pd.DataFrame(records)
                df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
                return df[STANDARD_COLUMNS]
        except Exception:
            pass

        return self.empty_dataframe()
