# -*- coding: utf-8 -*-
"""
Parser Dedicado: C6 Bank (Estrutura Base)
Particularidades: Faturas em CSV/OFX com parcelas '(01/10)' e cabeçalhos OFX não-estritos.
"""
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.c6")

class C6BankParser(BaseBankParser):
    institution_name: str = "C6 Bank"
    guidelines: str = "No App C6 Bank, exporte o extrato em formato .OFX ou a fatura detalhada em .CSV."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        df = generic_parse_csv(file_bytes=file_bytes, filename=filename or "c6.csv")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "C6" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "C6" if r.get("Tipo") == "Receita" else "", axis=1)
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "c6.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "C6" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "C6" if r.get("Tipo") == "Receita" else "", axis=1)
        return df
