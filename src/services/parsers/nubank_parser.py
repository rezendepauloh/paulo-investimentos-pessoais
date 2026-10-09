# -*- coding: utf-8 -*-
"""
Parser Dedicado: Nubank (Nu Pagamentos)
Trata particularidades como:
- CSVs de cartão: colunas 'date', 'category', 'title', 'amount'. No extrato de fatura, compras vêm com valor positivo e pagamentos/estornos como crédito.
- CSVs de conta corrente: colunas 'Data', 'Valor', 'Identificador', 'Descrição'.
- Normalização de sinal e atribuição de Conta = 'Nubank'.
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

logger = get_logger("services", "parsers.nubank")

class NubankParser(BaseBankParser):
    institution_name: str = "Nubank"
    guidelines: str = "No App Nubank, exporte o extrato da NuConta em .OFX ou .CSV, ou a fatura do cartão em .CSV."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        df_raw = None
        for enc in ["utf-8", "utf-8-sig", "latin1"]:
            try:
                sample = file_bytes[:4096].decode(enc, errors="ignore")
                sep = "," if sample.count(",") >= sample.count(";") else ";"
                temp = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, dtype=str)
                if not temp.empty and temp.shape[1] >= 2:
                    df_raw = temp
                    break
            except Exception:
                continue

        if df_raw is None or df_raw.empty:
            return self.empty_dataframe()

        cols_map = {str(col).strip(): str(col).lower().strip() for col in df_raw.columns}
        
        # Checa se é CSV de fatura Nubank: 'date', 'title', 'amount'
        is_card_csv = "date" in cols_map.values() and "amount" in cols_map.values() and ("title" in cols_map.values() or "category" in cols_map.values())

        records = []
        if is_card_csv:
            date_col = next(orig for orig, low in cols_map.items() if low == "date")
            desc_col = next((orig for orig, low in cols_map.items() if low == "title"), None) or next((orig for orig, low in cols_map.items() if low == "category"), None)
            val_col = next(orig for orig, low in cols_map.items() if low == "amount")
            cat_col = next((orig for orig, low in cols_map.items() if low == "category"), None)

            for _, row in df_raw.iterrows():
                d_val = str(row[date_col]).strip() if pd.notna(row[date_col]) else ""
                desc_val = str(row[desc_col]).strip() if pd.notna(row[desc_col]) else "Compra Nubank"
                v_raw = str(row[val_col]).strip() if pd.notna(row[val_col]) else "0"
                orig_cat = str(row[cat_col]).strip() if cat_col and pd.notna(row[cat_col]) else ""

                if not d_val or not v_raw:
                    continue

                dt_obj = pd.to_datetime(d_val, errors="coerce")
                if pd.isna(dt_obj):
                    continue

                try:
                    val_float = float(v_raw.replace(",", "."))
                except ValueError:
                    continue

                # No Nubank Card CSV: compras têm valor positivo (>0), pagamentos/estornos são negativos (<0)
                if "pagamento" in desc_val.lower() or val_float < 0:
                    tipo = "Receita"
                    categoria = "Salário" if "receb" in desc_val.lower() else "Outros"
                    conta_cred = "Nubank"
                    conta_deb = ""
                else:
                    tipo = "Despesa"
                    categoria = normalize_expense_category(f"{orig_cat} {desc_val}")
                    conta_cred = ""
                    conta_deb = "Nubank"

                fixo_var, essencial = infer_nature_and_essentiality(categoria, desc_val)

                records.append({
                    "Data": dt_obj.date(),
                    "Descricao": desc_val,
                    "Valor": abs(val_float),
                    "Categoria": categoria,
                    "Tipo": tipo,
                    "Conta creditada": conta_cred,
                    "Conta debitada": conta_deb,
                    "Fixo vs. Variável": fixo_var,
                    "Essencial vs. Não Essencial": essencial,
                    "Forma_Pagamento": "Cartão de crédito"
                })
        else:
            # Extrato geral NuConta
            from src.services.ingestion_parser import parse_csv as generic_parse_csv
            df_parsed = generic_parse_csv(file_bytes, filename=filename or "nubank.csv")
            if not df_parsed.empty:
                df_parsed["Conta debitada"] = df_parsed.apply(lambda r: "Nubank" if r.get("Tipo") == "Despesa" else "", axis=1)
                df_parsed["Conta creditada"] = df_parsed.apply(lambda r: "Nubank" if r.get("Tipo") == "Receita" else "", axis=1)
            return df_parsed

        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = self.empty_dataframe()
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "nubank.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "Nubank" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "Nubank" if r.get("Tipo") == "Receita" else "", axis=1)
        return df
