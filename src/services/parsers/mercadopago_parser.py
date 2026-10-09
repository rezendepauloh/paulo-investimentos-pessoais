# -*- coding: utf-8 -*-
"""
Parser Dedicado: Mercado Pago (Estrutura Base)
Particularidades: Taxas de serviço discriminadas, estornos e rendimentos automáticos de saldo.
"""
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.mercadopago")

class MercadoPagoParser(BaseBankParser):
    institution_name: str = "Mercado Pago"
    guidelines: str = "No App ou Web Mercado Pago, baixe o relatório de movimentações em formato .CSV."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        df = generic_parse_csv(file_bytes=file_bytes, filename=filename or "mercadopago.csv")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "Mercado Pago" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "Mercado Pago" if r.get("Tipo") == "Receita" else "", axis=1)
        return df

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        df = generic_parse_ofx(file_input=file_input, filename=filename or "mercadopago.ofx")
        if not df.empty:
            df["Conta debitada"] = df.apply(lambda r: "Mercado Pago" if r.get("Tipo") == "Despesa" else "", axis=1)
            df["Conta creditada"] = df.apply(lambda r: "Mercado Pago" if r.get("Tipo") == "Receita" else "", axis=1)
        return df
