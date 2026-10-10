# -*- coding: utf-8 -*-
"""
Parser Dedicado: Banco Inter
Trata particularidades como:
- Extratos de conta corrente e investimentos.
- Identificação de proventos e rendimentos em conta.
"""
import os
import io
import re
import datetime
from typing import Any
import pandas as pd
import pypdf
from src.services.parsers.base_parser import BaseBankParser
from src.services.ingestion_parser import (
    normalize_expense_category,
    normalize_income_category,
    infer_nature_and_essentiality
)
from src.services.deduplication import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.inter")

class InterParser(BaseBankParser):
    institution_name: str = "Banco Inter"
    guidelines: str = "No App ou Internet Banking do Banco Inter, exporte seu extrato em .OFX/.CSV de Conta Corrente ou faça upload da fatura do cartão em .PDF recebida por e-mail."

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        """
        Processa extrato CSV emitido pelo Banco Inter.
        Trata o cabeçalho descritivo com metadados (ex: Conta, Período, Saldo) antes da tabela real.
        """
        lines = []
        for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
            try:
                decoded = file_bytes.decode(enc)
                lines = decoded.splitlines()
                break
            except Exception:
                continue

        if not lines:
            return self.empty_dataframe()

        # Identifica a linha onde começa a tabela de transações
        header_idx = None
        sep = ";"
        for idx, line in enumerate(lines):
            l_low = line.lower()
            if "data" in l_low and any(k in l_low for k in ["valor", "saldo", "histórico", "historico", "descrição", "descricao"]):
                header_idx = idx
                sep = ";" if line.count(";") >= line.count(",") else ","
                break

        if header_idx is None:
            # Fallback para o parse genérico se o formato for atípico
            from src.services.ingestion_parser import parse_csv as generic_parse_csv
            return generic_parse_csv(file_bytes=file_bytes, filename=filename or "inter.csv")

        csv_body = "\n".join(lines[header_idx:])
        try:
            df_raw = pd.read_csv(io.StringIO(csv_body), sep=sep, dtype=str)
        except Exception as e:
            logger.error(f"Erro ao ler linhas do CSV do Inter: {e}")
            return self.empty_dataframe()

        if df_raw.empty:
            return self.empty_dataframe()

        cols_map = {str(col).strip(): str(col).lower().strip() for col in df_raw.columns}
        date_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["data", "dt"])), None)
        hist_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["histórico", "historico"])), None)
        desc_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["descrição", "descricao", "memo", "title"])), None)
        val_col = next((orig for orig, low in cols_map.items() if any(k in low for k in ["valor", "amount"]) and "saldo" not in low), None)

        if not date_col or not val_col:
            logger.warning("Colunas mínimas (data, valor) não localizadas no CSV do Inter.")
            return self.empty_dataframe()

        records = []
        for _, row in df_raw.iterrows():
            d_raw = str(row[date_col]).strip() if pd.notna(row[date_col]) else ""
            hist_raw = str(row[hist_col]).strip() if hist_col and pd.notna(row[hist_col]) else ""
            desc_raw = str(row[desc_col]).strip() if desc_col and pd.notna(row[desc_col]) else ""
            v_raw = str(row[val_col]).strip() if pd.notna(row[val_col]) else "0"

            if not d_raw or d_raw.lower() in ["nan", "none", ""]:
                continue

            # Parsing de Data (DD/MM/YYYY ou YYYY-MM-DD)
            dt_obj = None
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
                try:
                    dt_obj = datetime.datetime.strptime(d_raw, fmt).date()
                    break
                except ValueError:
                    pass

            if not dt_obj:
                continue

            # Normalização de Valor Numérico (BR format: 3.958,09 ou US: 3958.09)
            v_clean = v_raw.replace("R$", "").replace(" ", "")
            if "," in v_clean and "." in v_clean:
                v_clean = v_clean.replace(".", "").replace(",", ".")
            elif "," in v_clean:
                v_clean = v_clean.replace(",", ".")

            try:
                val_float = float(v_clean)
            except ValueError:
                continue

            tipo = "Receita" if val_float > 0 else "Despesa"
            val_abs = abs(val_float)

            # Sanitização descritiva
            clean_desc = re.sub(r'\s+', ' ', desc_raw).strip()
            clean_hist = re.sub(r'\s+', ' ', hist_raw).strip()

            # Remove marcadores de proventos brutos da B3 / Inter
            display_desc = clean_desc
            if display_desc.startswith("* Prov * "):
                display_desc = display_desc[len("* Prov * "):]
            elif display_desc.startswith("* Prov *"):
                display_desc = display_desc[len("* Prov *"):].strip()

            # Normaliza e formata proventos de investimentos se ticker detectado
            ticker_match = re.search(r'\b([A-Z]{4}[0-9]{1,2})\b', display_desc.upper())
            if ticker_match and any(k in (clean_hist + " " + display_desc).lower() for k in ["rendimento", "dividendo", "juros", "jcp", "reembolso", "aluguel"]):
                t_sym = ticker_match.group(1)
                # Remove o ticker do final ou meio para evitar repetição
                desc_sem_ticker = re.sub(rf'\b{t_sym}\b', '', display_desc, flags=re.IGNORECASE).strip()
                desc_sem_ticker = re.sub(r'\s+', ' ', desc_sem_ticker).strip()
                display_desc = f"{t_sym} - {desc_sem_ticker}" if desc_sem_ticker else t_sym

            # Contextualização inteligente da descrição
            if clean_hist and clean_hist.lower() not in display_desc.lower():
                full_text_for_cat = f"{clean_hist} - {clean_desc}"
                if any(k in clean_hist.lower() for k in ["pix", "pagamento", "transferência", "transferencia"]):
                    display_desc = f"{clean_hist} - {display_desc}"
            else:
                full_text_for_cat = clean_desc

            # Forma de Pagamento
            forma = "Conta corrente"
            t_check = (clean_hist + " " + clean_desc).lower()
            if "pix" in t_check:
                forma = "Pix"
            elif any(k in t_check for k in ["fatura", "cartao", "cartão"]):
                forma = "Cartão de crédito"
            elif any(k in t_check for k in ["ted", "doc", "transf"]):
                forma = "Transferência"
            elif "boleto" in t_check:
                forma = "Boleto"

            # Categorização
            if tipo == "Receita":
                categoria = normalize_income_category(full_text_for_cat)
            else:
                categoria = normalize_expense_category(full_text_for_cat)

            fixo_var, essencial = infer_nature_and_essentiality(categoria, display_desc)

            records.append({
                "Data": dt_obj,
                "Descricao": display_desc,
                "Valor": val_abs,
                "Categoria": categoria,
                "Tipo": tipo,
                "Conta creditada": "Inter" if tipo == "Receita" else "",
                "Conta debitada": "Inter" if tipo == "Despesa" else "",
                "Fixo vs. Variável": fixo_var,
                "Essencial vs. Não Essencial": essencial,
                "Forma_Pagamento": forma
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = self.empty_dataframe()
        return df

    @staticmethod
    def _clean_inter_description(memo: str, name: str) -> str:
        """
        Unifica e limpa os campos MEMO e NAME do Banco Inter, removendo códigos internos (Cp :xxx),
        marcadores de proventos (* Prov *) e preservando o contexto da operação (Pix, Fatura, Proventos).
        """
        memo_str = (memo or "").strip()
        name_str = (name or "").strip()

        # Extrai conteúdo entre aspas se presente no memo
        m_inner = ""
        quote_match = re.search(r'\"([^\"]+)\"', memo_str)
        if quote_match:
            m_inner = quote_match.group(1).strip()
        if m_inner:
            m_inner = re.sub(r'^Cp\s*:\d+-', '', m_inner).strip()

        prefix = memo_str.split(':')[0].strip() if ':' in memo_str else ''
        base = name_str if name_str else (m_inner or memo_str)

        # Remove prefixos de proventos brutos da B3 (* Prov *)
        base = re.sub(r'^\*\s*prov\s*\*\s*', '', base, flags=re.IGNORECASE).strip()
        # Normaliza espaços múltiplos
        base = re.sub(r'\s+', ' ', base).strip()

        # Adiciona prefixo operacional para Pix ou Pagamento se ausente
        if prefix and any(k in prefix.lower() for k in ['pix', 'pagamento', 'transferência', 'transferencia']):
            if prefix.lower() not in base.lower():
                base = f"{prefix} - {base}"

        # Normaliza e formata proventos com ticker na frente se detectado
        ticker_match = re.search(r'\b([A-Z]{4}[0-9]{1,2})\b', base.upper())
        if ticker_match and any(k in (memo_str + " " + base).lower() for k in ["rendimento", "dividendo", "juros", "jcp", "reembolso", "aluguel"]):
            t_sym = ticker_match.group(1)
            desc_sem_ticker = re.sub(rf'\b{t_sym}\b', '', base, flags=re.IGNORECASE).strip()
            desc_sem_ticker = re.sub(r'\s+', ' ', desc_sem_ticker).strip()
            base = f"{t_sym} - {desc_sem_ticker}" if desc_sem_ticker else t_sym

        return base

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        """
        Processa arquivo OFX do Banco Inter garantindo marcação de contas,
        sanitização das descrições (MEMO/NAME) e classificação refinada de proventos.
        """
        if isinstance(file_input, str):
            content_str = file_input
        elif isinstance(file_input, bytes):
            content_str = ""
            for enc in ['utf-8', 'latin1', 'cp1252']:
                try:
                    content_str = file_input.decode(enc)
                    break
                except Exception:
                    continue
        elif hasattr(file_input, "read"):
            raw = file_input.read()
            if isinstance(raw, str):
                content_str = raw
            else:
                content_str = ""
                for enc in ['utf-8', 'latin1', 'cp1252']:
                    try:
                        content_str = raw.decode(enc)
                        break
                    except Exception:
                        continue
        else:
            content_str = str(file_input)

        if not content_str or not content_str.strip():
            return self.empty_dataframe()

        records = []
        blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', content_str, re.DOTALL | re.IGNORECASE)
        for b in blocks:
            dtposted = re.search(r'<DTPOSTED>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)
            trnamt = re.search(r'<TRNAMT>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)
            memo_match = re.search(r'<MEMO>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)
            name_match = re.search(r'<NAME>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)

            # Data de Lançamento
            raw_date = dtposted.group(1).strip() if dtposted else ""
            date_obj = None
            if len(raw_date) >= 8:
                try:
                    date_obj = datetime.date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
                except Exception:
                    date_obj = datetime.date.today()
            else:
                date_obj = datetime.date.today()

            # Valor Numérico
            raw_val = trnamt.group(1).strip() if trnamt else "0"
            try:
                val_float = float(raw_val.replace(',', '.'))
            except ValueError:
                val_float = 0.0

            tipo = "Receita" if val_float > 0 else "Despesa"
            valor_abs = abs(val_float)

            memo_str = memo_match.group(1).strip() if memo_match else ""
            name_str = name_match.group(1).strip() if name_match else ""

            display_desc = self._clean_inter_description(memo_str, name_str)
            full_text_for_cat = f"{memo_str} {name_str}"

            # Categorização
            if tipo == "Receita":
                categoria = normalize_income_category(full_text_for_cat)
            else:
                categoria = normalize_expense_category(full_text_for_cat)

            # Forma de pagamento
            forma = "Conta corrente"
            t_check = full_text_for_cat.lower()
            if "pix" in t_check:
                forma = "Pix"
            elif any(k in t_check for k in ["fatura", "cartao", "cartão"]):
                forma = "Cartão de crédito"
            elif any(k in t_check for k in ["ted", "doc", "transf"]):
                forma = "Transferência"
            elif "boleto" in t_check:
                forma = "Boleto"

            fixo_var, essencial = infer_nature_and_essentiality(categoria, display_desc)

            records.append({
                "Data": date_obj,
                "Descricao": display_desc,
                "Valor": valor_abs,
                "Categoria": categoria,
                "Tipo": tipo,
                "Conta creditada": "Inter" if tipo == "Receita" else "",
                "Conta debitada": "Inter" if tipo == "Despesa" else "",
                "Fixo vs. Variável": fixo_var,
                "Essencial vs. Não Essencial": essencial,
                "Forma_Pagamento": forma
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = self.empty_dataframe()
        return df

    def parse_pdf(self, file_bytes: bytes, filename: str = "", password: str = "") -> pd.DataFrame:
        """
        Processa fatura de cartão de crédito do Banco Inter em PDF (protegida por senha - 6 dígitos do CPF).
        Extrai data de fechamento/competência da fatura e todas as despesas lançadas na fatura.
        Formata parcelas como: 'NOME DA LOJA 1/7 (Compra: DD/MM)'
        Atribui a data contábil do fechamento da fatura (dia 20 do mês de vencimento) e Conta Debitada = 'Cartão de crédito'.
        """
        pwd = (password or os.getenv("PDF_INVOICE_INTER_PASSWORD", "")).strip()

        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        except Exception as e:
            logger.error(f"Erro ao abrir PDF da fatura do Inter ({filename}): {e}")
            return self.empty_dataframe()

        if reader.is_encrypted:
            if not pwd:
                logger.warning(f"Fatura {filename} é protegida por senha, mas nenhuma senha foi informada ou encontrada no .env (PDF_INVOICE_INTER_PASSWORD).")
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

        # 1. Extrai data de vencimento da fatura da capa (página 1)
        data_fechamento_fatura = None
        p1_text = reader.pages[0].extract_text() if len(reader.pages) > 0 else ""
        m_venc = re.search(r'Data de Vencimento\s*\n?\s*(\d{2})/(\d{2})/(\d{4})', p1_text, re.IGNORECASE)
        if not m_venc:
            # Fallback em todas as páginas para o padrão do cabeçalho: 5364****6448 22/08/2026 R$
            for p in reader.pages[:3]:
                txt = p.extract_text() or ""
                m_header = re.search(r'\b\d{4}\*{4}\d{4}\s+(\d{2})/(\d{2})/(\d{4})\b', txt)
                if m_header:
                    m_venc = m_header
                    break

        if m_venc:
            d_v, m_v, a_v = int(m_venc.group(1)), int(m_venc.group(2)), int(m_venc.group(3))
            # Define data de fechamento/competência financeira da fatura (dia 20 do mês de vencimento)
            data_fechamento_fatura = datetime.date(a_v, m_v, 20)
        else:
            data_fechamento_fatura = datetime.date.today()

        records = []
        for page_idx in range(len(reader.pages)):
            page_text = reader.pages[page_idx].extract_text() or ""
            for line in page_text.splitlines():
                line = line.strip()
                if not line or "total" in line.lower() and "cartão" in line.lower():
                    continue

                # Padrão de lançamento: DD de MMM. AAAA Descrição - R$ Valor
                m_trans = re.match(r'^(\d{2})\s+de\s+(\w+)\.?\s+(\d{4})\s+(.+?)\s+-\s+R\$\s*([\d\.,]+)$', line)
                if not m_trans:
                    continue

                d_compra, mon_str, a_compra, desc_raw, val_str = m_trans.groups()
                mon_prefix = mon_str.lower()[:3]
                m_compra_num = pt_months.get(mon_prefix, 1)

                val_clean = val_str.replace(".", "").replace(",", ".")
                try:
                    val_float = float(val_clean)
                except ValueError:
                    continue

                if val_float <= 0:
                    continue

                # Normalização descritiva de parcelas
                # Ex: SHOPEE *SHPSTECNOLOGIA (Parcela 01 de 07) -> SHOPEE *SHPSTECNOLOGIA 1/7 (Compra: 23/07)
                clean_desc = desc_raw.strip()
                m_parc = re.search(r'\(Parcela\s+(\d+)\s+de\s+(\d+)\)', clean_desc, re.IGNORECASE)
                compra_tag = f"(Compra: {int(d_compra):02d}/{m_compra_num:02d})"
                if m_parc:
                    cur_p = int(m_parc.group(1))
                    tot_p = int(m_parc.group(2))
                    base_name = re.sub(r'\(Parcela\s+\d+\s+de\s+\d+\)', '', clean_desc, flags=re.IGNORECASE).strip()
                    base_name = re.sub(r'\s+', ' ', base_name).strip()
                    display_desc = f"{base_name} {cur_p}/{tot_p} {compra_tag}"
                else:
                    display_desc = f"{clean_desc} {compra_tag}"

                display_desc = re.sub(r'\s+', ' ', display_desc).strip()

                # Categorização da despesa
                categoria = normalize_expense_category(clean_desc)
                fixo_var, essencial = infer_nature_and_essentiality(categoria, display_desc)

                records.append({
                    "Data": data_fechamento_fatura,
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
            logger.info(f"Fatura PDF do Inter processada com sucesso: {len(df)} despesas extraídas (totalizando R$ {df['Valor'].sum():.2f}).")
        else:
            logger.warning(f"Nenhuma despesa localizada na fatura PDF do Inter ({filename}).")
            df = self.empty_dataframe()

        return df
