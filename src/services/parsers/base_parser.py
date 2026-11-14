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

    def parse_excel(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        """Processa arquivo Excel (.xlsx / .xls) específico da instituição."""
        return self.empty_dataframe()

    def parse_pdf(self, file_bytes: bytes, filename: str = "", password: str = "") -> pd.DataFrame:
        """Processa fatura ou extrato em PDF específico da instituição."""
        return self.empty_dataframe()

    def parse_zip(self, file_bytes: bytes, filename: str = "", password: str = "") -> pd.DataFrame:
        """Processa arquivo compactado .ZIP com proteção contra Zip-Bomb e Path Traversal."""
        import os
        from src.utils.logger import get_logger
        from src.utils.security import redact_secrets, safe_read_zip_entries, validate_upload_bytes

        log = get_logger("services", "parsers.base")

        pwd_candidates = []
        if password:
            pwd_candidates.append(password.strip())
        for env_k in ["PDF_INVOICE_C6_PASSWORD", "PDF_INVOICE_INTER_PASSWORD"]:
            val = os.getenv(env_k, "").strip()
            if val and val not in pwd_candidates:
                pwd_candidates.append(val)

        try:
            validate_upload_bytes(file_bytes, filename=filename or "archive.zip", allowed_extensions=[".zip"])
            entries = safe_read_zip_entries(
                file_bytes,
                password_candidates=pwd_candidates,
                allowed_inner_extensions=[".csv", ".ofx", ".xlsx", ".xls", ".pdf"],
            )

            dfs = []
            for safe_name, inner_bytes in entries:
                inner_lower = safe_name.lower()
                if inner_lower.endswith(".ofx"):
                    df_part = self.parse_ofx(inner_bytes, filename=safe_name)
                elif inner_lower.endswith(".xlsx") or inner_lower.endswith(".xls"):
                    df_part = self.parse_excel(inner_bytes, filename=safe_name)
                elif inner_lower.endswith(".pdf"):
                    df_part = self.parse_pdf(inner_bytes, filename=safe_name, password=password)
                else:
                    df_part = self.parse_csv(inner_bytes, filename=safe_name)

                if not df_part.empty:
                    dfs.append(df_part)

            if dfs:
                return pd.concat(dfs, ignore_index=True)
        except Exception as e:
            log.warning(f"Falha ao processar arquivo ZIP '{filename}': {redact_secrets(e)}")

        return self.empty_dataframe()

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """Processa comprovante/imagem da instituição (fallback padrão para IA)."""
        from src.services.ingestion_parser import parse_receipt_image
        return parse_receipt_image(file_bytes, mime_type=mime_type)

    @classmethod
    def empty_dataframe(cls) -> pd.DataFrame:
        """Retorna DataFrame vazio com schema padronizado."""
        return pd.DataFrame(columns=STANDARD_COLUMNS)
