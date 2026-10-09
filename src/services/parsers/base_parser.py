# -*- coding: utf-8 -*-
"""
Contrato Base para Parsers Dedicados por Instituição Financeira.
Padroniza as colunas e formatos esperados na ingestão de extratos e comprovantes.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
import pandas as pd

STANDARD_COLUMNS = [
    "Data",
    "Descricao",
    "Valor",
    "Categoria",
    "Tipo",
    "Conta creditada",
    "Conta debitada",
    "Fixo vs. Variável",
    "Essencial vs. Não Essencial",
    "Forma_Pagamento",
    "Hash"
]

class BaseBankParser(ABC):
    """
    Interface base que todo parser de instituição financeira deve implementar.
    Garante consistência estrutural no DataFrame resultante.
    """
    institution_name: str = "Genérico"
    guidelines: str = "Exporte o extrato em formato .OFX ou .CSV de conta corrente ou cartão."

    @abstractmethod
    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        """Processa arquivo CSV específico da instituição."""
        pass

    @abstractmethod
    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        """Processa arquivo OFX específico da instituição."""
        pass

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """Processa comprovante/imagem da instituição (fallback padrão para IA)."""
        from src.services.ingestion_parser import parse_receipt_image
        return parse_receipt_image(file_bytes, mime_type=mime_type)

    @classmethod
    def empty_dataframe(cls) -> pd.DataFrame:
        """Retorna DataFrame vazio com schema padronizado."""
        return pd.DataFrame(columns=STANDARD_COLUMNS)
