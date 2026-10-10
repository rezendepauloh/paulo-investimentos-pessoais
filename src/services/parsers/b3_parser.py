# -*- coding: utf-8 -*-
"""
Parser Dedicado: B3 (Área do Investidor)
Processa extratos oficiais da B3 baixados em https://www.investidor.b3.com.br/extrato/movimentacao (.xlsx ou .csv).

Mapeia:
- Empréstimo / Aluguel de Ações -> Categoria "Aluguel Ações BR" com o Ticker exato (ex: AZZA3, FLRY3, WEGE3).
- Rendimento (FII) -> Categoria "Rendimento FII" com o Ticker exato (ex: KNRI11, HGLG11).
- Dividendo -> Categoria "Dividendo BR" com o Ticker exato (ex: FLRY3).
- Juros Sobre Capital Próprio -> Categoria "Juros sobre Capital Próprio" com o Ticker exato (ex: ITUB3).
- Reembolso -> Categoria do provento com o Ticker exato.
- Conta creditada: Detecta automaticamente a corretora (Inter ou XP).
"""
import io
import re
import datetime
from typing import Any, Optional
import pandas as pd

from src.services.parsers.base_parser import BaseBankParser, STANDARD_COLUMNS
from src.services.deduplication import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.b3")

class B3Parser(BaseBankParser):
    institution_name: str = "B3 (Área do Investidor)"
    guidelines: str = "Acesse investidor.b3.com.br > Extratos > Movimentação e baixe o arquivo em formato .XLSX ou .CSV."

    # Mapeamento oficial de tipos de movimentação de proventos na B3
    MAPA_MOVIMENTACAO = {
        "empréstimo": ("Aluguel Ações BR", "Aluguel"),
        "emprestimo": ("Aluguel Ações BR", "Aluguel"),
        "rendimento": ("Rendimento FII", "Rendimento FII"),
        "dividendo": ("Dividendo BR", "Dividendo"),
        "juros sobre capital próprio": ("Juros sobre Capital Próprio", "JCP"),
        "juros sobre capital proprio": ("Juros sobre Capital Próprio", "JCP"),
        "reembolso": ("Juros sobre Capital Próprio", "Reembolso"),
    }

    @staticmethod
    def extract_ticker(produto_str: str) -> str:
        """
        Extrai o ticker de ações ou FII a partir do campo 'Produto' da B3.
        Ex: 'FLRY3 - FLEURY S.A.' -> 'FLRY3'
        Ex: 'KNRI11 - KINEA RENDA IMOBILIÁRIA FDO INV IMOB - FII' -> 'KNRI11'
        """
        if not produto_str:
            return ""
        clean = produto_str.strip()
        # Se contiver hífen, a primeira parte geralmente é o ticker
        parts = clean.split("-")
        candidate = parts[0].strip().upper()
        if re.match(r'^[A-Z]{4}[0-9]{1,2}$', candidate):
            return candidate

        # Procura por regex de ticker em qualquer parte do texto
        m = re.search(r'\b([A-Z]{4}[0-9]{1,2})\b', clean.upper())
        if m:
            return m.group(1)
        return candidate

    @staticmethod
    def detect_broker(instituicao_str: str) -> str:
        """
        Mapeia a razão social da corretora na B3 para o nome padronizado no app.
        Ex: 'INTER DISTRIBUIDORA...' -> 'Inter'
        Ex: 'XP INVESTIMENTOS...' -> 'XP'
        """
        inst_low = (instituicao_str or "").lower()
        if "inter" in inst_low:
            return "Inter"
        elif "xp" in inst_low:
            return "XP"
        elif "c6" in inst_low:
            return "C6"
        elif "nu" in inst_low or "easynvest" in inst_low:
            return "Nubank"
        elif "btg" in inst_low:
            return "BTG"
        elif "clear" in inst_low:
            return "Clear"
        elif "rico" in inst_low:
            return "Rico"
        elif "ágora" in inst_low or "agora" in inst_low:
            return "Ágora"
        elif "genial" in inst_low:
            return "Genial"
        return instituicao_str.strip() or "Inter"

    def parse_excel(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        """Processa a planilha .xlsx oficial da Área do Investidor B3."""
        try:
            df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0)
            return self._process_b3_dataframe(df_raw)
        except Exception as e:
            logger.error(f"Erro ao ler Excel da B3 ({filename}): {e}")
            return self.empty_dataframe()

    def parse_csv(self, file_bytes: bytes, filename: str = "") -> pd.DataFrame:
        """Processa arquivo CSV exportado da B3."""
        for sep in [";", ","]:
            for enc in ["utf-8-sig", "utf-8", "latin1"]:
                try:
                    df_raw = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc)
                    if any("moviment" in col.lower() for col in df_raw.columns):
                        return self._process_b3_dataframe(df_raw)
                except Exception:
                    continue
        return self.empty_dataframe()

    def parse_ofx(self, file_input: Any, filename: str = "") -> pd.DataFrame:
        """B3 não emite extrato em OFX; fallback seguro."""
        return self.empty_dataframe()

    def _process_b3_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza as colunas da B3 para o formato padrão do aplicativo.
        Filtra apenas proventos com valor financeiro positivo recebido.
        """
        if df.empty:
            return self.empty_dataframe()

        # Identifica nomes de colunas sem sensibilidade a maiúsculas/minúsculas
        cols_map = {c.lower().strip(): c for c in df.columns}
        col_data = cols_map.get("data")
        col_mov = cols_map.get("movimentação") or cols_map.get("movimentacao")
        col_prod = cols_map.get("produto")
        col_inst = cols_map.get("instituição") or cols_map.get("instituicao")
        col_val = cols_map.get("valor da operação") or cols_map.get("valor da operacao") or cols_map.get("valor")
        col_es = cols_map.get("entrada/saída") or cols_map.get("entrada/saida")

        if not all([col_data, col_mov, col_prod, col_val]):
            logger.warning("Colunas essenciais da B3 não foram encontradas na planilha.")
            return self.empty_dataframe()

        records = []
        for _, row in df.iterrows():
            # 1. Filtra apenas entradas/créditos ou movimentações com valor financeiro
            es_val = str(row.get(col_es, "Credito")).strip().lower()
            if "debito" in es_val or "débito" in es_val or "saida" in es_val or "saída" in es_val:
                continue

            # 2. Movimentação (Empréstimo, Rendimento, Dividendo, JCP, Reembolso)
            mov_raw = str(row.get(col_mov, "")).strip()
            mov_low = mov_raw.lower()
            cat_info = None
            for k, val in self.MAPA_MOVIMENTACAO.items():
                if k in mov_low:
                    cat_info = val
                    break

            if not cat_info:
                # Ignora transferências de custódia, subscrições sem valor, etc.
                continue

            categoria_padrao, label_prov = cat_info

            # 3. Valor financeiro
            val_raw = str(row.get(col_val, "")).strip().replace("R$", "").replace(" ", "")
            if val_raw in ["-", "", "nan", "None"]:
                continue
            try:
                # Trata formato BR (1.234,56) ou US (1234.56)
                if "," in val_raw and "." in val_raw:
                    val_num = float(val_raw.replace(".", "").replace(",", "."))
                elif "," in val_raw:
                    val_num = float(val_raw.replace(",", "."))
                else:
                    val_num = float(val_raw)
            except ValueError:
                continue

            if val_num <= 0:
                continue

            # 4. Data
            d_raw = str(row.get(col_data, "")).strip()
            dt_obj = None
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
                try:
                    dt_obj = datetime.datetime.strptime(d_raw, fmt).date()
                    break
                except ValueError:
                    pass
            if not dt_obj:
                try:
                    dt_obj = pd.to_datetime(d_raw, errors="coerce").date()
                except Exception:
                    pass
            if not dt_obj or pd.isnull(dt_obj):
                dt_obj = datetime.date.today()

            # 5. Ativo / Ticker e Instituição
            prod_raw = str(row.get(col_prod, "")).strip()
            ticker = self.extract_ticker(prod_raw)
            inst_raw = str(row.get(col_inst, "")).strip() if col_inst else "Inter"
            conta_cred = self.detect_broker(inst_raw)

            # Descrição amigável e limpa para o orçamento e gráficos
            if ticker:
                display_desc = f"{ticker} - {label_prov}"
            else:
                display_desc = f"{prod_raw} - {label_prov}"

            records.append({
                "Data": dt_obj,
                "Descricao": display_desc,
                "Valor": round(val_num, 2),
                "Categoria": categoria_padrao,
                "Tipo": "Receita",
                "Conta creditada": conta_cred,
                "Conta debitada": "",
                "Fixo vs. Variável": "Variável",
                "Essencial vs. Não Essencial": "Essencial",
                "Forma_Pagamento": "Conta corrente"
            })

        df_out = pd.DataFrame(records)
        if not df_out.empty:
            df_out["Hash"] = df_out.apply(
                lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1
            )
        else:
            df_out = self.empty_dataframe()

        logger.info(f"B3 Parser processou com sucesso {len(df_out)} proventos financeiros.")
        return df_out
