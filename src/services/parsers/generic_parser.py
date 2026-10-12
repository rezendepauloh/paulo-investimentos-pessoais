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

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """
        Processa comprovante genérico via Tesseract OCR local.
        Detecta automaticamente se é do 99 Pay, Lojas Renner ou outros formatos conhecidos.
        """
        try:
            import pytesseract
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(image, lang="por")
            text_lower = text.lower()

            if "99pay" in text_lower or "transferir para" in text_lower or "id da transação 99pay" in text_lower:
                from src.services.parsers.pay99_parser import Pay99Parser
                return Pay99Parser().parse_ocr_text(text)
            elif "carnê" in text_lower or "carne" in text_lower or "renner" in text_lower or "parcela de compra" in text_lower:
                from src.services.parsers.store_cards_parser import StoreCardsParser
                return StoreCardsParser().parse_ocr_text(text)
        except Exception:
            pass

        return super().parse_receipt(file_bytes, mime_type=mime_type)

