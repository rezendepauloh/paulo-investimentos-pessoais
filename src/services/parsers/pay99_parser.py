# -*- coding: utf-8 -*-
"""
Parser Dedicado: 99 Pay (Estrutura Base)
Particularidades: Bonificação de CDI diária, recargas e pagamentos via aplicativo.
"""
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.99pay")

class Pay99Parser(BaseBankParser):
    institution_name: str = "99 Pay"
    guidelines: str = "No App 99 Pay, exporte o extrato em .CSV ou envie os comprovantes de transação."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        df = generic_parse_csv(file_bytes=file_bytes, filename=filename or "99pay.csv")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "99 Pay" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "99 Pay" if r.get("Tipo") == "Receita" else "", axis=1)
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "99pay.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "99 Pay" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "99 Pay" if r.get("Tipo") == "Receita" else "", axis=1)
        return df
