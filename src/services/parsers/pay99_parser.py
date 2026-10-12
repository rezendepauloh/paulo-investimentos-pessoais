# -*- coding: utf-8 -*-
"""
Parser Dedicado: 99 Pay
Particularidades: Leitura de extratos CSV/OFX e comprovantes de transferências Pix / Boletos em imagem/PDF.
Utiliza Tesseract OCR local para decodificar comprovantes do 99Pay, extraindo Valor, Data,
Destinatário e, primordialmente, a Observação inserida pelo usuário para categorização automática.
"""
from typing import Any
import io
import re
import datetime
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser, STANDARD_COLUMNS
from src.services.ingestion_parser import (
    normalize_expense_category,
    infer_nature_and_essentiality,
    generate_transaction_hash
)
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.99pay")


class Pay99Parser(BaseBankParser):
    institution_name: str = "99 Pay"
    guidelines: str = "No App 99 Pay, envie os comprovantes de Pix/Pagamento em imagem (.JPG, .PNG) ou PDF. O OCR extrairá valor, data e a observação para categorização."

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

    def parse_receipt(self, file_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
        """
        Processa comprovante de pagamento / Pix do 99 Pay via Tesseract OCR local.
        """
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(image, lang="por")
            logger.info("OCR Tesseract executado no comprovante 99 Pay.")
            return self.parse_ocr_text(text)
        except Exception as e:
            logger.warning(f"Erro no OCR local do 99 Pay: {e}. Tentando fallback IA...")
            try:
                from src.services.ingestion_parser import parse_receipt_image
                return parse_receipt_image(file_bytes, mime_type=mime_type)
            except Exception as e_fallback:
                logger.error(f"Fallback também falhou: {e_fallback}")
                return self.empty_dataframe()

    def parse_ocr_text(self, text: str) -> pd.DataFrame:
        """
        Interpreta o texto OCR de comprovante do 99 Pay (tanto Pix quanto Boletos).
        """
        if not text or not text.strip():
            return self.empty_dataframe()

        text_lower = text.lower()
        is_boleto = "detalhes do boleto" in text_lower or "valor do boleto" in text_lower or "beneficiário" in text_lower or "beneficiario" in text_lower

        # -----------------------------------------------------------
        # FLUXO 1: COMPROVANTES DE BOLETO
        # -----------------------------------------------------------
        if is_boleto:
            # 1. Valor: "Valor final pago R$2.080,89" ou primeiro R$ do topo
            m_pago = re.search(r"Valor final pago\s*R\$\s*([0-9.,\s]+)", text, re.IGNORECASE)
            if m_pago:
                val_raw = m_pago.group(1).replace(" ", "").strip()
            else:
                m_topo = re.search(r"R\$\s*([0-9.,\s]+)", text)
                val_raw = m_topo.group(1).replace(" ", "").strip() if m_topo else "0"

            try:
                valor = float(val_raw.replace(".", "").replace(",", "."))
            except Exception:
                valor = 0.0

            if valor <= 0:
                logger.warning("Não foi possível identificar o valor no comprovante de boleto do 99 Pay.")
                return self.empty_dataframe()

            # 2. Data: Horário do pagamento, Data de vencimento ou Solicitação processada em
            m_dt = re.search(r"Horário do pagamento\s*(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)
            if not m_dt:
                m_dt = re.search(r"Data de vencimento\s*(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)
            if not m_dt:
                m_dt = re.search(r"Solicitação processada em\s*(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)

            dt_obj = datetime.date.today()
            if m_dt:
                parts = m_dt.group(1).split("/")
                if len(parts) == 3:
                    d, m, y = parts
                    if len(y) == 2:
                        y = f"20{y}"
                    try:
                        dt_obj = datetime.date(int(y), int(m), int(d))
                    except Exception:
                        dt_obj = datetime.date.today()

            # 3. Beneficiário (multilinha até encontrar próxima seção)
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            ben_lines = []
            capture = False
            for l in lines:
                if re.search(r"^Beneficiário\b", l, re.IGNORECASE) and not capture:
                    capture = True
                    after = re.sub(r"^Beneficiário\s*:?", "", l, flags=re.IGNORECASE).strip()
                    if after:
                        ben_lines.append(after)
                    continue
                if capture:
                    if any(stop in l.lower() for stop in ["documento", "pagador", "código", "beneficiário final", "data", "valor"]):
                        break
                    ben_lines.append(l)

            beneficiario = " ".join(ben_lines).strip() if ben_lines else ""
            if not beneficiario:
                m_ben = re.search(r"Beneficiário\s*(.*?)(?:\n\n|\nDocumento|\nPagador|\nCódigo|\nBeneficiário final|\nData)", text, re.DOTALL | re.IGNORECASE)
                beneficiario = m_ben.group(1).replace("\n", " ").strip() if m_ben else "Boleto 99Pay"

            beneficiario = re.sub(r"\s+", " ", beneficiario).strip()
            descricao = f"Boleto {beneficiario}" if not beneficiario.lower().startswith("boleto") else beneficiario

            # Categorização Inteligente do Boleto
            ben_lower = beneficiario.lower()
            if any(k in ben_lower for k in ["santa ines", "reserva", "eucalyptus", "condominio", "condomínio"]):
                cat = "Condomínio"
            elif any(k in ben_lower for k in ["claro", "vivo", "tim", "telefonia"]):
                cat = "Telefonia"
            elif any(k in ben_lower for k in ["sage", "protecao", "veicular", "seguro"]):
                cat = "Serviços / Manutenção"
            elif any(k in ben_lower for k in ["simples nacional", "das", "iptu", "tributo", "imposto"]):
                cat = "Tributo"
            elif any(k in ben_lower for k in ["luz", "energisa", "enel"]):
                cat = "Luz"
            elif any(k in ben_lower for k in ["água", "agua", "sanesul", "sabesp"]):
                cat = "Água"
            else:
                cat = normalize_expense_category(beneficiario)

            fixo_var, essencial = infer_nature_and_essentiality(cat, descricao)

            record = {
                "Data": dt_obj,
                "Descricao": descricao,
                "Valor": valor,
                "Categoria": cat,
                "Tipo": "Despesa",
                "Conta creditada": "",
                "Conta debitada": "99 Pay",
                "Fixo vs. Variável": fixo_var,
                "Essencial vs. Não Essencial": essencial,
                "Forma_Pagamento": "Boleto"
            }

            df = pd.DataFrame([record])
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
            return df[STANDARD_COLUMNS]

        # -----------------------------------------------------------
        # FLUXO 2: COMPROVANTES DE PIX (TRANSFERÊNCIA)
        # -----------------------------------------------------------
        # 1. Extração do Valor
        # Procura por "Valor da conta R$84,00" ou linha no topo "R$84,00"
        m_val = re.search(r"Valor da conta\s*R\$\s*([0-9.,]+)", text, re.IGNORECASE)
        if not m_val:
            m_val = re.search(r"R\$\s*([0-9.,]+)", text)

        if not m_val:
            logger.warning("Não foi possível encontrar o valor no comprovante 99 Pay.")
            return self.empty_dataframe()

        try:
            valor = float(m_val.group(1).replace(".", "").replace(",", "."))
        except Exception:
            valor = 0.0

        if valor <= 0:
            return self.empty_dataframe()

        # 2. Extração da Data
        # "Data de pagamento 01/09/26", "Data da transferência 04/09/26" ou "Data agendada 10/09/26"
        m_dt = re.search(r"Data de pagamento\s*(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)
        if not m_dt:
            m_dt = re.search(r"Data da transferência\s*(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)
        if not m_dt:
            m_dt = re.search(r"Data agendada\s*(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)

        dt_obj = datetime.date.today()
        if m_dt:
            dt_str = m_dt.group(1)
            parts = dt_str.split("/")
            if len(parts) == 3:
                d, m, y = parts
                if len(y) == 2:
                    y = f"20{y}"
                try:
                    dt_obj = datetime.date(int(y), int(m), int(d))
                except Exception:
                    dt_obj = datetime.date.today()

        # 3. Extração da Observação (chave essencial para identificar o gasto)
        m_obs = re.search(r"Observação\s*(.*?)(?:\n\n|\n[A-Z]|\nDetalhes|\nData|\nInstituição)", text, re.DOTALL | re.IGNORECASE)
        obs = m_obs.group(1).replace("\n", " ").replace("|", "").strip() if m_obs else ""

        # 4. Extração do Destinatário
        m_dest = re.search(r"Transferir para\s*(.*?)(?:\n\n|\n[A-Z]|\nData|\nID)", text, re.DOTALL | re.IGNORECASE)
        dest = m_dest.group(1).replace("\n", " ").replace("|", "").strip() if m_dest else ""

        # Montagem da Descrição
        # Se houver observação, ela vem primeiro e mais destacada, com o destinatário como complemento
        if obs and dest:
            descricao = f"{obs} ({dest})"
        elif obs:
            descricao = obs
        elif dest:
            descricao = f"Pix para {dest}"
        else:
            descricao = "Transferência Pix 99Pay"

        # Categorização Inteligente guiada pela observação
        obs_lower = obs.lower()
        if any(k in obs_lower for k in ["bolão", "bolao", "mega da virada", "loteria"]):
            cat = "Eventos"
        elif any(k in obs_lower for k in ["salgado", "lanche", "churros", "dico", "pastel"]):
            cat = "Lanches"
        elif any(k in obs_lower for k in ["almoço", "almoco", "jantar", "restaurante"]):
            cat = "Restaurante"
        elif any(k in obs_lower for k in ["canula", "cânula", "medicamento", "remédio", "remedio"]):
            cat = "Médicos e terapeutas"
        elif any(k in obs_lower for k in ["creme", "cabelo", "estetica", "estética", "manicure", "salao", "salão"]):
            cat = "Salão de beleza"
        elif any(k in obs_lower for k in ["extensão", "extensao", "powerbank", "eletronico", "cabo"]):
            cat = "Compras"
        elif any(k in obs_lower for k in ["pneu", "seguro", "conserto", "oficina"]):
            cat = "Serviços / Manutenção"
        elif any(k in obs_lower for k in ["liga do bem", "doação", "doacao", "presente"]):
            cat = "Presentes"
        elif any(k in obs_lower for k in ["condomínio", "condominio"]):
            cat = "Condomínio"
        elif any(k in obs_lower for k in ["luz", "energisa", "energia"]):
            cat = "Luz"
        elif any(k in obs_lower for k in ["claro", "vivo", "tim", "telefone", "celular"]):
            cat = "Telefonia"
        elif any(k in obs_lower for k in ["iptu", "ipva", "tributo", "imposto"]):
            cat = "Tributo"
        else:
            # Fallback para a normalização genérica unindo observação e destinatário
            cat = normalize_expense_category(f"{obs} {dest}")

        fixo_var, essencial = infer_nature_and_essentiality(cat, descricao)

        record = {
            "Data": dt_obj,
            "Descricao": descricao,
            "Valor": valor,
            "Categoria": cat,
            "Tipo": "Despesa",
            "Conta creditada": "",
            "Conta debitada": "99 Pay",
            "Fixo vs. Variável": fixo_var,
            "Essencial vs. Não Essencial": essencial,
            "Forma_Pagamento": "Pix"
        }

        df = pd.DataFrame([record])
        df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        return df[STANDARD_COLUMNS]

