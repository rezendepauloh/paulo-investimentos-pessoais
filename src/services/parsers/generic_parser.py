# -*- coding: utf-8 -*-
"""
Parser Genérico / Universal com auto-detecção heurística.
Atua como motor universal e fallback seguro para qualquer instituição.
"""
from typing import Any
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser, STANDARD_COLUMNS

class GenericBankParser(BaseBankParser):
    institution_name: str = "Outro / Genérico"
    guidelines: str = "Compatível com arquivos .OFX e .CSV padrão bancário brasileiro (delimitador vírgula ou ponto-e-vírgula)."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        return generic_parse_csv(file_bytes=file_bytes, filename=filename)

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        return generic_parse_ofx(file_input=file_input, filename=filename)
