# -*- coding: utf-8 -*-
"""
Parser Dedicado: C6 Bank
Particularidades: Faturas em PDF protegidas por senha (6 primeiros dígitos do CPF),
extratos em CSV/OFX e detalhamento de compras internacionais com conversão USD e IOF.
"""
import io
import os
import re
import datetime
from typing import Any
import pandas as pd
import pypdf

from src.services.parsers.base_parser import BaseBankParser
from src.services.ingestion_parser import (
    normalize_expense_category,
    infer_nature_and_essentiality
)
from src.services.deduplication import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.c6")

class C6BankParser(BaseBankParser):
    institution_name: str = "C6 Bank"
    guidelines: str = "No App C6 Bank, exporte o extrato em .OFX, .CSV ou envie o PDF da fatura do cartão (protegido pela senha de 6 dígitos)."

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

    def parse_pdf(self, file_bytes: bytes, filename: str = "", password: str = "") -> pd.DataFrame:
        """
        Processa fatura de cartão de crédito do C6 Bank em PDF (protegida por senha - 6 dígitos do CPF).
        Extrai data de vencimento da fatura e todas as despesas lançadas na fatura.
        Formata parcelas como: 'NOME DA LOJA X/Y (Compra: DD/MM)'
        Trata transações internacionais em moeda estrangeira (USD) e IOF correspondente.
        Atribui a data contábil de vencimento da fatura (dia 10 do mês), Conta debitada = 'Cartão de crédito'.
        """
        pwd = (password or os.getenv("PDF_INVOICE_C6_PASSWORD") or os.getenv("PDF_INVOICE_INTER_PASSWORD", "")).strip()

        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        except Exception as e:
            logger.error(f"Erro ao abrir PDF da fatura do C6 Bank ({filename}): {e}")
            return self.empty_dataframe()

        if reader.is_encrypted:
            if not pwd:
                logger.warning(f"Fatura {filename} é protegida por senha, mas nenhuma senha foi informada ou encontrada no .env.")
                return self.empty_dataframe()
            try:
                decrypted = reader.decrypt(pwd)
                if not decrypted:
                    logger.error(f"Falha ao descriptografar fatura {filename}: senha inválida.")
                    return self.empty_dataframe()
            except Exception as e:
                logger.error(f"Erro ao aplicar senha no PDF {filename}: {e}")
                return self.empty_dataframe()

        pt_months = {
            "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
            "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12
        }

        # 1. Extração da data de vencimento completa (DD/MM/AAAA)
        data_vencimento = None
        for p in reader.pages:
            txt = p.extract_text() or ""
            m_venc_full = re.search(r'Vencimento:\s*\n?\s*(\d{2})/(\d{2})/(\d{4})', txt, re.IGNORECASE)
            if m_venc_full:
                d_v, m_v, a_v = int(m_venc_full.group(1)), int(m_venc_full.group(2)), int(m_venc_full.group(3))
                data_vencimento = datetime.date(a_v, m_v, d_v)
                break

        if not data_vencimento:
            # Fallback para regex genérica de data na primeira ou última página
            for p in [reader.pages[0], reader.pages[-1]]:
                txt = p.extract_text() or ""
                m_dates = re.findall(r'(\d{2})/(\d{2})/(\d{4})', txt)
                if m_dates:
                    d_s, m_s, a_s = m_dates[0].split("/")
                    data_vencimento = datetime.date(int(a_s), int(m_s), int(d_s))
                    break

        if not data_vencimento:
            data_vencimento = datetime.date.today()

        records = []
        for page_idx in range(len(reader.pages)):
            page_text = reader.pages[page_idx].extract_text() or ""
            for line in page_text.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Ignora linhas de totalizadores, pagamentos de fatura anterior e cabeçalhos de resumo
                if any(x in line.lower() for x in [
                    "inclusao de pagamento", "inclusão de pagamento", "subtotal",
                    "total a pagar", "total da fatura", "fatura anterior", "saldo da fatura"
                ]):
                    continue

                # 3 Padrões possíveis na fatura C6:
                # 1) IOF Internacional: DD mmm NOME R$IOF Transações Exterior
                m_iof = re.match(r'^(\d{2})\s+([a-z]{3})\s+(.+?)\s+([\d\.,]+)IOF\s+Transa[cç][oõ]es\s+Exterior', line, re.I)
                # 2) Compra USD Internacional: DD mmm NOME R$USD xx,xx | Cotação USD: R$x,xx
                m_usd = re.match(r'^(\d{2})\s+([a-z]{3})\s+(.+?)\s+([\d\.,]+)USD\s+([\d\.,]+)', line, re.I)
                # 3) Lançamento Nacional / Parcelado: DD mmm NOME R$
                m_reg = re.match(r'^(\d{2})\s+([a-z]{3})\s+(.+?)\s+([\d\.,]+)$', line, re.I)

                if m_iof:
                    d_compra, mon_str, desc_raw, val_str = m_iof.groups()
                    desc_prefix = "IOF "
                elif m_usd:
                    d_compra, mon_str, desc_raw, val_str, _ = m_usd.groups()
                    desc_prefix = ""
                elif m_reg:
                    d_compra, mon_str, desc_raw, val_str = m_reg.groups()
                    desc_prefix = ""
                else:
                    continue

                mon_prefix = mon_str.lower()[:3]
                m_compra_num = pt_months.get(mon_prefix, 1)

                val_clean = val_str.replace(".", "").replace(",", ".")
                try:
                    val_float = float(val_clean)
                except ValueError:
                    continue

                if val_float <= 0:
                    continue

                clean_desc = desc_raw.strip()
                # Verifica se há indicação de parcela: ex: 'AREZZO - Parcela 2/6'
                m_parc = re.search(r'-\s*Parcela\s+(\d+/\d+)', clean_desc, re.IGNORECASE)
                compra_tag = f"(Compra: {int(d_compra):02d}/{m_compra_num:02d})"

                if m_parc:
                    parc_str = m_parc.group(1).strip()
                    base_name = re.sub(r'-\s*Parcela\s+\d+/\d+', '', clean_desc, flags=re.IGNORECASE).strip()
                    base_name = re.sub(r'\s+', ' ', base_name).strip()
                    display_desc = f"{desc_prefix}{base_name} {parc_str} {compra_tag}"
                else:
                    base_name = re.sub(r'\s+', ' ', clean_desc).strip()
                    display_desc = f"{desc_prefix}{base_name} {compra_tag}"

                display_desc = re.sub(r'\s+', ' ', display_desc).strip()

                # Categorização da despesa
                categoria = normalize_expense_category(f"{desc_prefix}{clean_desc}")
                fixo_var, essencial = infer_nature_and_essentiality(categoria, display_desc)

                records.append({
                    "Data": data_vencimento,
                    "Descricao": display_desc,
                    "Valor": val_float,
                    "Categoria": categoria,
                    "Tipo": "Despesa",
                    "Conta creditada": "",
                    "Conta debitada": "Cartão de crédito",
                    "Fixo vs. Variável": fixo_var,
                    "Essencial vs. Não Essencial": essencial,
                    "Forma_Pagamento": "Cartão de crédito"
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
            logger.info(f"Fatura PDF do C6 Bank processada com sucesso: {len(df)} despesas extraídas (totalizando R$ {df['Valor'].sum():.2f}).")
        else:
            logger.warning(f"Nenhuma despesa localizada na fatura PDF do C6 Bank ({filename}).")
            df = self.empty_dataframe()

        return df
