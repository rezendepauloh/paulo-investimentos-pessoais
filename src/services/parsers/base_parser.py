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
        """Processa arquivo compactado .ZIP contendo extratos (.ofx, .csv, .xlsx, .pdf)."""
        import zipfile
        import io
        import os

        pwd_candidates = []
        if password:
            pwd_candidates.append(password.strip())
        for env_k in ["PDF_INVOICE_C6_PASSWORD", "PDF_INVOICE_INTER_PASSWORD"]:
            val = os.getenv(env_k, "").strip()
            if val and val not in pwd_candidates:
                pwd_candidates.append(val)
        pwd_candidates.append("")  # tentativa sem senha

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                # Ordena arquivos úteis
                valid_infos = [
                    info for info in z.infolist()
                    if not info.is_dir() and not info.filename.startswith("__MACOSX")
                    and any(info.filename.lower().endswith(ext) for ext in [".csv", ".ofx", ".xlsx", ".xls", ".pdf"])
                ]
                if not valid_infos:
                    # Se não filtrou por extensão, pega qualquer arquivo não diretório
                    valid_infos = [info for info in z.infolist() if not info.is_dir() and not info.filename.startswith("__MACOSX")]

                dfs = []
                for info in valid_infos:
                    inner_bytes = None
                    for pwd_str in pwd_candidates:
                        pwd_b = pwd_str.encode("utf-8") if pwd_str else None
                        try:
                            inner_bytes = z.read(info, pwd=pwd_b)
                            break
                        except (RuntimeError, zipfile.BadZipFile):
                            continue

                    if inner_bytes is None:
                        continue

                    inner_name = os.path.basename(info.filename).lower()
                    if inner_name.endswith(".ofx"):
                        df_part = self.parse_ofx(inner_bytes, filename=info.filename)
                    elif inner_name.endswith(".xlsx") or inner_name.endswith(".xls"):
                        df_part = self.parse_excel(inner_bytes, filename=info.filename)
                    elif inner_name.endswith(".pdf"):
                        df_part = self.parse_pdf(inner_bytes, filename=info.filename, password=password)
                    else:
                        df_part = self.parse_csv(inner_bytes, filename=info.filename)

                    if not df_part.empty:
                        dfs.append(df_part)

                if dfs:
                    return pd.concat(dfs, ignore_index=True)
        except Exception:
            pass

        return self.empty_dataframe()

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """Processa comprovante/imagem da instituição (fallback padrão para IA)."""
        from src.services.ingestion_parser import parse_receipt_image
        return parse_receipt_image(file_bytes, mime_type=mime_type)

    @classmethod
    def empty_dataframe(cls) -> pd.DataFrame:
        """Retorna DataFrame vazio com schema padronizado."""
        return pd.DataFrame(columns=STANDARD_COLUMNS)
