# -*- coding: utf-8 -*-
"""
Parser Dedicado: Banco Inter
Trata particularidades como:
- Extratos de conta corrente e investimentos.
- Identificação de proventos e rendimentos em conta.
"""
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.inter")

class InterParser(BaseBankParser):
    institution_name: str = "Banco Inter"
    guidelines: str = "No App ou Internet Banking do Banco Inter, exporte seu extrato em formato .OFX ou .CSV de Conta Corrente."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        df = generic_parse_csv(file_bytes=file_bytes, filename=filename or "inter.csv")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "Inter" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "Inter" if r.get("Tipo") == "Receita" else "", axis=1)
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "inter.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "Inter" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "Inter" if r.get("Tipo") == "Receita" else "", axis=1)
        return df
