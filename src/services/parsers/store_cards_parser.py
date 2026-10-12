# -*- coding: utf-8 -*-
"""
Parser Dedicado para Cartões de Loja e Carnês (Lojas Renner, Riachuelo, C&A, etc.).
Suporta processamento local com Tesseract OCR e regex para extrair parcelas e faturas.
"""
from typing import Any, List
import re
import datetime
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser, STANDARD_COLUMNS
from src.services.ingestion_parser import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.store_cards")


class StoreCardsParser(BaseBankParser):
    institution_name: str = "Cartões de Loja / Carnês (Renner, Riachuelo, etc.)"
    guidelines: str = "Envie prints/screenshots do aplicativo da loja (Renner, Riachuelo, C&A) mostrando carnês ou parcelas. O Tesseract OCR extrairá os valores e datas localmente."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_csv as generic_parse_csv
        return generic_parse_csv(file_bytes=file_bytes, filename=filename)

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        from src.services.ingestion_parser import parse_ofx as generic_parse_ofx
        return generic_parse_ofx(file_input=file_input, filename=filename)

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """
        Processa print de tela ou foto de carnê de loja via Tesseract OCR local.
        """
        try:
            import pytesseract
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(image, lang="por")
            logger.info("OCR Tesseract executado com sucesso no comprovante de loja")
            return self.parse_ocr_text(text)
        except Exception as e:
            logger.warning(f"Falha ao executar Tesseract OCR localmente: {e}. Tentando fallback...")
            # Fallback para Gemini Vision se disponível
            try:
                from src.services.ingestion_parser import parse_receipt_image
                return parse_receipt_image(file_bytes, mime_type=mime_type)
            except Exception as e_fallback:
                logger.error(f"Fallback também falhou: {e_fallback}")
                return self.empty_dataframe()

    def parse_ocr_text(self, text: str) -> pd.DataFrame:
        """
        Interpreta o texto extraído pelo OCR e extrai as parcelas estruturadas.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        records: List[dict] = []

        # Identifica a loja pelo contexto do texto
        loja_nome = "Renner"
        text_lower = text.lower()
        if "riachuelo" in text_lower:
            loja_nome = "Riachuelo"
        elif "c&a" in text_lower or "cea" in text_lower:
            loja_nome = "C&A"
        elif "renner" in text_lower:
            loja_nome = "Renner"
        elif "marisa" in text_lower:
            loja_nome = "Marisa"
        elif "pernambucanas" in text_lower:
            loja_nome = "Pernambucanas"

        i = 0
        while i < len(lines):
            line = lines[i]
            # Procura por linha de valor (ex: "Parcela de compra R$ 224,11" ou apenas "R$ 224,11")
            m_val = re.search(r"R\$\s*([0-9.,]+)", line)
            if m_val:
                valor_str = m_val.group(1).replace(".", "").replace(",", ".")
                try:
                    valor = float(valor_str)
                except ValueError:
                    valor = 0.0

                # Verifica se a próxima linha contém parcelas e data
                # Ex: "Lojas Renner - 4 de 5 03/11/2026" ou "4 de 5 03/11/2026"
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    m_parc = re.search(r"(\d+)\s+de\s+(\d+)\s+(\d{2}/\d{2}/\d{4})", next_line)
                    if m_parc:
                        p_atual, p_total, dt_str = m_parc.groups()
                        try:
                            dt_obj = datetime.datetime.strptime(dt_str, "%d/%m/%Y").date()
                        except Exception:
                            dt_obj = datetime.date.today()

                        desc = f"{loja_nome} {p_atual}/{p_total}"
                        records.append({
                            "Data": dt_obj,
                            "Descricao": desc,
                            "Valor": valor,
                            "Categoria": "Vestuário",
                            "Tipo": "Despesa",
                            "Conta creditada": "",
                            "Conta debitada": "Cartão de loja / Carnê",
                            "Fixo vs. Variável": "Variável",
                            "Essencial vs. Não Essencial": "Não Essencial",
                            "Forma_Pagamento": "Cartão de loja / Carnê"
                        })
                        i += 2
                        continue

                # Padrão alternativo: data na mesma linha do valor ou parcela invertida
                m_parc_same = re.search(r"(\d+)\s+de\s+(\d+)", line)
                m_date_same = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                if m_parc_same and m_date_same:
                    p_atual, p_total = m_parc_same.groups()
                    try:
                        dt_obj = datetime.datetime.strptime(m_date_same.group(1), "%d/%m/%Y").date()
                    except Exception:
                        dt_obj = datetime.date.today()
                    desc = f"{loja_nome} {p_atual}/{p_total}"
                    records.append({
                        "Data": dt_obj,
                        "Descricao": desc,
                        "Valor": valor,
                        "Categoria": "Vestuário",
                        "Tipo": "Despesa",
                        "Conta creditada": "",
                        "Conta debitada": "Cartão de loja / Carnê",
                        "Fixo vs. Variável": "Variável",
                        "Essencial vs. Não Essencial": "Não Essencial",
                        "Forma_Pagamento": "Cartão de loja / Carnê"
                    })
            i += 1

        if not records:
            # Padrão 2: Procura por blocos gerais de parcela no texto inteiro
            general_matches = re.finditer(
                r"(\d+)\s+de\s+(\d+)\s+(\d{2}/\d{2}/\d{4})[\s\S]*?R\$\s*([0-9.,]+)",
                text,
                re.IGNORECASE
            )
            for m in general_matches:
                p_atual, p_total, dt_str, val_str = m.groups()
                try:
                    dt_obj = datetime.datetime.strptime(dt_str, "%d/%m/%Y").date()
                    val = float(val_str.replace(".", "").replace(",", "."))
                except Exception:
                    continue
                records.append({
                    "Data": dt_obj,
                    "Descricao": f"{loja_nome} {p_atual}/{p_total}",
                    "Valor": val,
                    "Categoria": "Vestuário",
                    "Tipo": "Despesa",
                    "Conta creditada": "",
                    "Conta debitada": "Cartão de loja / Carnê",
                    "Fixo vs. Variável": "Variável",
                    "Essencial vs. Não Essencial": "Não Essencial",
                    "Forma_Pagamento": "Cartão de loja / Carnê"
                })

        if not records:
            logger.warning("Nenhuma parcela reconhecida no OCR pelo StoreCardsParser.")
            return self.empty_dataframe()

        df = pd.DataFrame(records)
        df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        return df[STANDARD_COLUMNS]
