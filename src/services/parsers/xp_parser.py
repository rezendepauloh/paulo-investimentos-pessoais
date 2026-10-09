# -*- coding: utf-8 -*-
"""
Parser Dedicado: XP Investimentos (Estrutura Base)
Particularidades: Extrato de conta digital vs. custódia de proventos e corretagem.
"""
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.xp")

class XPParser(BaseBankParser):
    institution_name: str = "XP Investimentos"
    guidelines: str = "No Portal ou App XP, exporte o extrato financeiro da conta digital ou extrato de proventos em .CSV."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        df = generic_parse_csv(file_bytes=file_bytes, filename=filename or "xp.csv")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "XP" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "XP" if r.get("Tipo") == "Receita" else "", axis=1)
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "xp.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "XP" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "XP" if r.get("Tipo") == "Receita" else "", axis=1)
        return df
