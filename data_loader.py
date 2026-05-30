import os
import re
import json
import logging
from logging.handlers import RotatingFileHandler
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import streamlit as st

# Cria a pasta de logs se ela não existir
os.makedirs("logs", exist_ok=True)

# Configuração do Logger Rotativo (máximo 3 arquivos de 3MB)
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = RotatingFileHandler("logs/app.log", maxBytes=3 * 1024 * 1024, backupCount=2, encoding="utf-8")
log_handler.setFormatter(log_formatter)

logger = logging.getLogger("DataLoader")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(log_handler)

# Carrega variáveis de ambiente (override=True garante atualização dinâmica)
load_dotenv(override=True)

# Escopos do Google API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def clean_currency(val):
    """
    Limpa strings de valores monetários no formato brasileiro (ex: R$ 1.234,56 ou -R$ 50,00)
    para o formato float do Python.
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    val_str = str(val).strip()
    # Remove símbolos de moeda e espaços em branco
    val_str = re.sub(r"[R\$\s\xa0]", "", val_str)
    
    # Tratamento para pontuações no padrão BR (1.234,56 ou 1234,56)
    if "," in val_str:
        val_str = val_str.replace(".", "")  # remove separador de milhar
        val_str = val_str.replace(",", ".")  # substitui vírgula por ponto decimal
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def clean_float(val):
    """
    Converte valores decimais de forma robusta, suportando formatos BR (1.234,56) e US (1,234.56).
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    val_str = str(val).strip()
    # Remove símbolos monetários comuns e espaços
    val_str = re.sub(r"[R\$\s\xa0US]", "", val_str)
    
    if "," in val_str and "." in val_str:
        if val_str.find(",") > val_str.find("."):
            # Padrão BR: 1.234,56
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            # Padrão US: 1,234.56
            val_str = val_str.replace(",", "")
    elif "," in val_str:
        # Se tiver apenas vírgula, ex: 1,5 ou 1.500
        val_str = val_str.replace(",", ".")
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def clean_int(val):
    """
    Converte valores inteiros de forma segura, preservando strings de status.
    """
    if pd.isna(val) or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    
    val_str = str(val).strip()
    try:
        return int(val_str.replace(".", ""))
    except ValueError:
        try:
            return int(float(val_str.replace(".", "")))
        except ValueError:
            return val
 
def clean_percent_or_float(val):
    """
    Limpa e converte strings de percentuais ou decimais para float (ex: 105% -> 1.05, 5,85% -> 0.0585).
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    is_pct = False
    if "%" in val_str:
        val_str = val_str.replace("%", "").strip()
        is_pct = True
    if "," in val_str:
        val_str = val_str.replace(".", "").replace(",", ".")
    try:
        f = float(val_str)
        return f / 100.0 if is_pct else f
    except ValueError:
        return 0.0

@st.cache_resource
def get_gspread_client():
    """
    Inicializa e faz cache do cliente gspread usando a conta de serviço especificada.
    """
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Arquivo de credenciais do Google Cloud '{creds_path}' não encontrado. "
            "Por favor, configure o arquivo localmente ou ajuste o caminho no arquivo .env."
        )
    
    credentials = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(credentials)

@st.cache_data(ttl=600)  # Cache de 10 minutos para não estourar cota do Sheets
def load_sheet_data(spreadsheet_id, sheet_name):
    """
    Carrega os dados de uma aba específica de uma planilha como um DataFrame do Pandas.
    """
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        records = worksheet.get_all_records()
        
        if not records:
            data = worksheet.get_all_values()
            if len(data) > 1:
                headers = [h.strip() for h in data[0]]
                rows = data[1:]
                df = pd.DataFrame(rows, columns=headers)
            else:
                return pd.DataFrame()
        else:
            df = pd.DataFrame(records)
            
        df.columns = [col.strip() for col in df.columns]
        return df
    except Exception as e:
        logger.error(f"Erro ao carregar a aba '{sheet_name}' da planilha '{spreadsheet_id}': {e}")
        st.error(f"Erro ao carregar a aba '{sheet_name}' da planilha '{spreadsheet_id}': {e}")
        return pd.DataFrame()

def get_mock_data():
    """
    Gera dados simulados de alta qualidade para demonstração do aplicativo.
    """
    receitas_data = [
        {"Nome": "Salário Principal", "Valor": 8500.0, "Categoria": "Trabalho", "Recebido em": "05/05/2026", "Dias até": 0},
        {"Nome": "Projeto Freelance", "Valor": 2200.0, "Categoria": "Renda Extra", "Recebido em": "12/05/2026", "Dias até": 0},
    ]
    df_receitas = pd.DataFrame(receitas_data)
    df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], format="%d/%m/%Y")
    df_receitas["Valor"] = df_receitas["Valor"].astype(float)
    df_receitas["Dias até"] = df_receitas["Dias até"].astype(int)

    despesas_data = [
        {"Nome": "Aluguel & Condomínio", "Valor": 2800.0, "Categoria": "Moradia", "Conta debitada": "Itaú", "Gasto em": "02/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo", "Fixo vs. Variável": "Fixo", "Essencial vs. Não Essencial": "Essencial"},
        {"Nome": "Supermercado", "Valor": 1100.0, "Categoria": "Alimentação", "Conta debitada": "Nubank", "Gasto em": "10/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável", "Fixo vs. Variável": "Variável", "Essencial vs. Não Essencial": "Essencial"},
        {"Nome": "Combustível", "Valor": 450.0, "Categoria": "Transporte", "Conta debitada": "Nubank", "Gasto em": "15/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável", "Fixo vs. Variável": "Variável", "Essencial vs. Não Essencial": "Essencial"},
        {"Nome": "Academia", "Valor": 150.0, "Categoria": "Saúde", "Conta debitada": "Nubank", "Gasto em": "05/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo", "Fixo vs. Variável": "Fixo", "Essencial vs. Não Essencial": "Não essencial"},
        {"Nome": "Streaming & Internet", "Valor": 180.0, "Categoria": "Lazer", "Conta debitada": "Itaú", "Gasto em": "08/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo", "Fixo vs. Variável": "Fixo", "Essencial vs. Não Essencial": "Não essencial"},
        {"Nome": "Jantar Fora", "Valor": 350.0, "Categoria": "Lazer", "Conta debitada": "Nubank", "Gasto em": "20/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável", "Fixo vs. Variável": "Variável", "Essencial vs. Não Essencial": "Não essencial"},
    ]
    df_despesas = pd.DataFrame(despesas_data)
    df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], format="%d/%m/%Y")
    df_despesas["Valor"] = df_despesas["Valor"].astype(float)
    df_despesas["Dias até"] = df_despesas["Dias até"].astype(int)

    dividendos_data = [
        {"Nome": "Rendimento HGLG11", "Valor": 110.0, "Ativo": "HGLG11", "Categoria": "FIIs", "Recebido em": "15/05/2026", "Dias até": 0},
        {"Nome": "Dividendos PETR4", "Valor": 320.0, "Ativo": "PETR4", "Categoria": "Ações", "Recebido em": "20/05/2026", "Dias até": 0},
        {"Nome": "Proventos WEGE3", "Valor": 45.0, "Ativo": "WEGE3", "Categoria": "Ações", "Recebido em": "22/05/2026", "Dias até": 0},
    ]
    df_dividendos = pd.DataFrame(dividendos_data)
    df_dividendos["Recebido em"] = pd.to_datetime(df_dividendos["Recebido em"], format="%d/%m/%Y")
    df_dividendos["Valor"] = df_dividendos["Valor"].astype(float)
    df_dividendos["Dias até"] = df_dividendos["Dias até"].astype(int)

    ordens_data = [
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "WEGE3", "Qtd Executada": 100, "Preço médio": 35.0, "Total": 3500.0, "data envio": "15/01/2025 10:30:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 35.0, "Total líquido": 3500.0, "Setor Econômico": "Bens Industriais / Máquinas"},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "PETR4", "Qtd Executada": 150, "Preço médio": 28.0, "Total": 4200.0, "data envio": "18/01/2025 11:15:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 28.0, "Total líquido": 4200.0, "Setor Econômico": "Petróleo, Gás e Biocombustíveis"},
        {"Compra/Venda": "Compra", "Tipo": "FIIs", "Moeda": "BRL", "Papel": "HGLG11", "Qtd Executada": 50, "Preço médio": 155.0, "Total": 7750.0, "data envio": "20/01/2025 14:00:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 155.0, "Total líquido": 7750.0, "Setor Econômico": "Imobiliário"},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "VALE3", "Qtd Executada": 50, "Preço médio": 62.0, "Total": 3100.0, "data envio": "10/07/2025 10:45:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 62.0, "Total líquido": 3100.0, "Setor Econômico": "Materiais Básicos / Mineração"},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "WEGE3", "Qtd Executada": 50, "Preço médio": 38.5, "Total": 1925.0, "data envio": "12/07/2025 15:20:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 38.5, "Total líquido": 1925.0, "Setor Econômico": "Bens Industriais / Máquinas"},
        {"Compra/Venda": "Compra", "Tipo": "Internacional", "Moeda": "USD", "Papel": "IVV", "Qtd Executada": 10, "Preço médio": 480.0, "Total": 4800.0, "data envio": "05/01/2026 16:00:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 480.0, "Total líquido": 24000.0, "Setor Econômico": "Tecnologia"},
    ]
    df_ordens = pd.DataFrame(ordens_data)
    df_ordens["data envio"] = pd.to_datetime(df_ordens["data envio"], format="%d/%m/%Y %H:%M:%S")
    
    return df_receitas, df_despesas, df_dividendos, df_ordens

def clean_and_normalize_orders(df_orders):
    """
    Limpa, normaliza colunas e valores, e aplica autocorreções no DataFrame de ordens.
    """
    if df_orders.empty:
        return df_orders
        
    col_mapping = {}
    for col in df_orders.columns:
        c_lower = str(col).lower().strip()
        if c_lower in ["data envio", "data de envio", "data_envio", "data", "data de envio de ordens"]:
            col_mapping[col] = "data envio"
        elif c_lower in ["compra/venda", "compra ou venda", "operação", "operacao", "c/v", "tipo de operacao", "tipo de operação"]:
            col_mapping[col] = "Compra/Venda"
        elif c_lower in ["tipo", "classe", "categoria"]:
            col_mapping[col] = "Tipo"
        elif c_lower in ["moeda"]:
            col_mapping[col] = "Moeda"
        elif c_lower in ["papel", "ativo", "ticker", "código", "codigo"]:
            col_mapping[col] = "Papel"
        elif c_lower in ["qtd executada", "quantidade", "qtd", "quantidade executada", "volume"]:
            col_mapping[col] = "Qtd Executada"
        elif c_lower in ["preço médio", "preco medio", "preço unitário", "preco unitario", "pm"]:
            col_mapping[col] = "Preço médio"
        elif c_lower in ["total", "valor total", "valor"]:
            col_mapping[col] = "Total"
        elif c_lower in ["cód. cliente", "cod. cliente", "cliente", "cod cliente", "código cliente"]:
            col_mapping[col] = "Cód. Cliente"
        elif c_lower in ["corretagem", "taxas", "taxa", "custos"]:
            col_mapping[col] = "Corretagem"
        elif c_lower in ["preço médio + corretagem", "preco medio + corretagem", "preço médio com corretagem", "pm+corretagem"]:
            col_mapping[col] = "Preço médio + corretagem"
        elif c_lower in ["total líquido", "total liquido", "valor líquido", "valor liquido"]:
            col_mapping[col] = "Total líquido"
        elif c_lower in ["setor econômico", "setor economico", "setor", "setor econômico"]:
            col_mapping[col] = "Setor Econômico"
        elif c_lower in ["indexador", "index", "tipo indexador"]:
            col_mapping[col] = "Indexador"
        elif c_lower in ["taxa indexador", "taxa index", "taxa", "taxaindexador", "taxaindex"]:
            col_mapping[col] = "Taxa Indexador"
            
    if col_mapping:
        df_orders = df_orders.rename(columns=col_mapping)
        
    if "data envio" not in df_orders.columns:
        for col in df_orders.columns:
            if "data" in str(col).lower():
                df_orders = df_orders.rename(columns={col: "data envio"})
                break
        if "data envio" not in df_orders.columns:
            df_orders["data envio"] = pd.Timestamp.now()
            
    if "Papel" not in df_orders.columns:
        for col in df_orders.columns:
            if "ativo" in str(col).lower() or "papel" in str(col).lower() or "ticker" in str(col).lower():
                df_orders = df_orders.rename(columns={col: "Papel"})
                break
        if "Papel" not in df_orders.columns:
            df_orders["Papel"] = "AtivoIndefinido"
            
    if "Qtd Executada" not in df_orders.columns:
        for col in df_orders.columns:
            if "qtd" in str(col).lower() or "quant" in str(col).lower():
                df_orders = df_orders.rename(columns={col: "Qtd Executada"})
                break
                
    numeric_cols = ["Qtd Executada", "Preço médio", "Total", "Corretagem", "Preço médio + corretagem", "Total líquido"]
    for col in numeric_cols:
        if col in df_orders.columns:
            if col == "Qtd Executada":
                df_orders[col] = df_orders[col].apply(clean_float)
            else:
                df_orders[col] = df_orders[col].apply(clean_currency)
        else:
            df_orders[col] = 0.0
            
    if "Qtd Executada" in df_orders.columns and "Total" in df_orders.columns and "Preço médio" in df_orders.columns:
        import math
        for idx, row in df_orders.iterrows():
            try:
                qty = float(row["Qtd Executada"])
                tot = float(row["Total"])
                pm = float(row["Preço médio"])
                
                if qty > 0 and tot > 0 and pm > 0:
                    expected_qty = tot / pm
                    if qty > expected_qty * 3.0:
                        ratio = qty / expected_qty
                        power = round(math.log10(ratio))
                        if power > 0:
                            df_orders.at[idx, "Qtd Executada"] = qty / (10 ** power)
            except Exception:
                pass
                
    if "data envio" in df_orders.columns:
        raw_dates = df_orders["data envio"].copy()
        df_orders["data envio"] = pd.to_datetime(raw_dates, dayfirst=True, errors="coerce")
        
    string_cols = ["Compra/Venda", "Tipo", "Moeda", "Papel", "Setor Econômico", "Indexador"]
    for col in string_cols:
        if col in df_orders.columns:
            df_orders[col] = df_orders[col].astype(str).str.strip()
        else:
            df_orders[col] = ""
            
    if "Taxa Indexador" in df_orders.columns:
        df_orders["Taxa Indexador"] = df_orders["Taxa Indexador"].apply(clean_percent_or_float)
    else:
        df_orders["Taxa Indexador"] = 0.0
            
    # Autocorreção in-app de segurança contra distorções de milhar/localidade em bonificações
    for idx, row in df_orders.iterrows():
        try:
            op = str(row.get("Compra/Venda", "")).strip().upper()
            if "BONIFICAÇÃO" in op or "BONIFICACAO" in op or "DESDOBRAMENTO" in op:
                papel = str(row.get("Papel", "")).strip().upper()
                data_dt = row.get("data envio")
                if pd.isna(data_dt) or data_dt == "":
                    continue
                
                data_str = ""
                if hasattr(data_dt, "strftime"):
                    data_str = data_dt.strftime("%d/%m/%Y")
                else:
                    val_str = str(data_dt).strip()
                    match = re.search(r"(\d{2}/\d{2}/\d{4})", val_str)
                    if match:
                        data_str = match.group(1)
                    else:
                        match_us = re.search(r"(\d{4})-(\d{2})-(\d{2})", val_str)
                        if match_us:
                            data_str = f"{match_us.group(3)}/{match_us.group(2)}/{match_us.group(1)}"
                            
                if not data_str:
                    continue
                    
                chave = (papel, data_str)
                
                correcoes_conhecidas = {}
                correcoes_env = os.getenv("CORRECOES_CONHECIDAS", "{}")
                try:
                    correcoes_dict = json.loads(correcoes_env)
                    correcoes_conhecidas = {tuple(k.split("|")): float(v) for k, v in correcoes_dict.items()}
                except Exception as e:
                    logger.error(f"Erro ao carregar CORRECOES_CONHECIDAS do .env: {e}")
                
                if chave in correcoes_conhecidas:
                    old_val = df_orders.at[idx, "Qtd Executada"]
                    df_orders.at[idx, "Qtd Executada"] = correcoes_conhecidas[chave]
                    logger.info(f"Autocorreção de bonificação aplicada na memória: {papel} em {data_str} corrigido de {old_val} para {correcoes_conhecidas[chave]}")
        except Exception as e:
            logger.error(f"Erro ao processar autocorreção de bonificação na linha {idx}: {e}")
            
    return df_orders


def get_budget_data(use_mock=False):
    """
    Carrega os dados de Orçamento. Prioriza a leitura do banco de dados SQLite local,
    caindo de volta para o Google Sheets se o SQLite estiver vazio.
    """
    load_dotenv(override=True)
    if use_mock:
        df_r, df_d, df_div, _ = get_mock_data()
        return df_r, df_d, df_div
        
    import db_manager
    try:
        db_conn = db_manager.get_db_connection()
        c_receitas = pd.read_sql_query("SELECT count(*) as count FROM receitas", db_conn).iloc[0]["count"]
        c_despesas = pd.read_sql_query("SELECT count(*) as count FROM despesas", db_conn).iloc[0]["count"]
        c_dividendos = pd.read_sql_query("SELECT count(*) as count FROM dividendos", db_conn).iloc[0]["count"]
        
        if c_receitas > 0 or c_despesas > 0 or c_dividendos > 0:
            logger.info("Carregando dados de Orçamento diretamente do SQLite local.")
            df_receitas = pd.read_sql_query("SELECT * FROM receitas", db_conn)
            df_despesas = pd.read_sql_query("SELECT * FROM despesas", db_conn)
            df_dividendos = pd.read_sql_query("SELECT * FROM dividendos", db_conn)
            db_conn.close()
            
            # Mapeamento reverso para manter total retrocompatibilidade com o app.py
            map_rev = {
                "nome": "Nome", "valor": "Valor", "categoria": "Categoria",
                "recebido_em": "Recebido em", "dias_ate": "Dias até",
                "conta_debitada": "Conta debitada", "gasto_em": "Gasto em",
                "tipo_cobranca": "Tipo de Cobrança", "ativo": "Ativo",
                "fixo_variavel": "Fixo vs. Variável", "essencial_nao_essencial": "Essencial vs. Não Essencial"
            }
            df_receitas = df_receitas.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            df_despesas = df_despesas.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            df_dividendos = df_dividendos.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            
            # Trata tipos de data
            if "Recebido em" in df_receitas.columns:
                df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], errors="coerce")
            if "Gasto em" in df_despesas.columns:
                df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], errors="coerce")
            if "Recebido em" in df_dividendos.columns:
                df_dividendos["Recebido em"] = pd.to_datetime(df_dividendos["Recebido em"], errors="coerce")
                
            return df_receitas, df_despesas, df_dividendos
        db_conn.close()
    except Exception as e:
        logger.error(f"Erro ao ler Orçamento do SQLite local: {e}. Caindo de volta para o Google Sheets.")
        
    # Fallback para o Sheets se o banco estiver vazio
    budget_id = os.getenv("SPREADSHEET_BUDGET_ID")
    if not budget_id:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    logger.info("Banco SQLite vazio. Disparando sincronização inicial automática do Orçamento...")
    sync_google_sheets_to_sqlite()
    return get_budget_data(use_mock=False)


def get_orders_data(use_mock=False):
    """
    Carrega dados de ordens de investimento. Prioriza o banco SQLite local, 
    caindo de volta para o Google Sheets se estiver vazio.
    """
    load_dotenv(override=True)
    if use_mock:
        _, _, _, df_o = get_mock_data()
        return df_o
        
    import db_manager
    try:
        db_conn = db_manager.get_db_connection()
        c_ordens = pd.read_sql_query("SELECT count(*) as count FROM ordens", db_conn).iloc[0]["count"]
        
        if c_ordens > 0:
            logger.info("Carregando dados de Ordens diretamente do SQLite local.")
            df_orders = pd.read_sql_query("SELECT * FROM ordens", db_conn)
            db_conn.close()
            
            map_rev = {
                "data_envio": "data envio", "compra_venda": "Compra/Venda",
                "papel": "Papel", "qtd_executada": "Qtd Executada",
                "preco_medio": "Preço médio", "total_liquido": "Total líquido",
                "moeda": "Moeda", "tipo": "Tipo", "total": "Total",
                "corretagem": "Corretagem", "preco_medio_corretagem": "Preço médio + corretagem",
                "cod_cliente": "Cód. Cliente", "setor_economico": "Setor Econômico"
            }
            df_orders = df_orders.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            if "data envio" in df_orders.columns:
                df_orders["data envio"] = pd.to_datetime(df_orders["data envio"], errors="coerce")
            return df_orders
        db_conn.close()
    except Exception as e:
        logger.error(f"Erro ao ler Ordens do SQLite local: {e}. Caindo de volta para o Google Sheets.")
        
    logger.info("Banco SQLite vazio. Disparando sincronização inicial automática das Ordens...")
    sync_google_sheets_to_sqlite()
    return get_orders_data(use_mock=False)


def sync_google_sheets_to_sqlite():
    """
    Sincroniza todas as planilhas do Google Sheets para o SQLite local de forma incremental/delta.
    Para garantir a consistência absoluta (remocao de linhas e atualizacao de dados), as tabelas
    são limpas localmente imediatamente antes de receberem o lote completo normalizado do Sheets.
    """
    import db_manager
    logger.info("Iniciando sincronização incremental do Google Sheets para o SQLite local...")
    
    # 1. Sincroniza Ordens
    orders_id = os.getenv("SPREADSHEET_ORDERS_ID")
    if orders_id:
        try:
            logger.info("Buscando ordens novas do Google Sheets...")
            df_orders = load_sheet_data(orders_id, "Ordens")
            if df_orders.empty:
                client = get_gspread_client()
                spreadsheet = client.open_by_key(orders_id)
                first_worksheet = spreadsheet.get_worksheet(0)
                records = first_worksheet.get_all_records()
                if records:
                    df_orders = pd.DataFrame(records)
                    df_orders.columns = [col.strip() for col in df_orders.columns]
                else:
                    data = first_worksheet.get_all_values()
                    if len(data) > 1:
                        headers = [h.strip() for h in data[0]]
                        df_orders = pd.DataFrame(data[1:], columns=headers)
            
            if not df_orders.empty:
                df_orders = clean_and_normalize_orders(df_orders)
                db_manager.clear_table("ordens")
                db_manager.save_dataframe_delta("ordens", df_orders, None)
        except Exception as e:
            logger.error(f"Erro ao sincronizar aba Ordens: {e}")
            
    # 2. Sincroniza Orçamento (Receitas, Despesas, Dividendos)
    budget_id = os.getenv("SPREADSHEET_BUDGET_ID")
    if budget_id:
        try:
            logger.info("Buscando lançamentos orçamentários do Google Sheets...")
            
            # Receitas
            df_receitas = load_sheet_data(budget_id, "Receitas")
            if not df_receitas.empty:
                df_receitas["Nome"] = df_receitas["Nome"].astype(str).str.strip()
                df_receitas["Categoria"] = df_receitas["Categoria"].astype(str).str.strip()
                df_receitas["Valor"] = df_receitas["Valor"].apply(clean_currency)
                df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], format="%d/%m/%Y", errors="coerce")
                df_receitas["Dias até"] = df_receitas["Dias até"].apply(clean_int)
                db_manager.clear_table("receitas")
                db_manager.save_dataframe_delta("receitas", df_receitas, None)
                
            # Despesas
            df_despesas = load_sheet_data(budget_id, "Despesas")
            if not df_despesas.empty:
                df_despesas["Nome"] = df_despesas["Nome"].astype(str).str.strip()
                df_despesas["Categoria"] = df_despesas["Categoria"].astype(str).str.strip()
                if "Conta debitada" in df_despesas.columns:
                    df_despesas["Conta debitada"] = df_despesas["Conta debitada"].astype(str).str.strip()
                if "Tipo de Cobrança" in df_despesas.columns:
                    df_despesas["Tipo de Cobrança"] = df_despesas["Tipo de Cobrança"].astype(str).str.strip()
                
                # Normaliza colunas Fixo/Variável e Essencial/Não Essencial de forma robusta e flexível
                col_rename_despesas = {}
                for col in df_despesas.columns:
                    c_low = col.lower().strip()
                    if "fixo" in c_low and "vari" in c_low:
                        col_rename_despesas[col] = "Fixo vs. Variável"
                    elif "essencial" in c_low:
                        col_rename_despesas[col] = "Essencial vs. Não Essencial"
                if col_rename_despesas:
                    df_despesas = df_despesas.rename(columns=col_rename_despesas)
                    
                if "Fixo vs. Variável" in df_despesas.columns:
                    df_despesas["Fixo vs. Variável"] = df_despesas["Fixo vs. Variável"].astype(str).str.strip()
                if "Essencial vs. Não Essencial" in df_despesas.columns:
                    df_despesas["Essencial vs. Não Essencial"] = df_despesas["Essencial vs. Não Essencial"].astype(str).str.strip()
                    
                df_despesas["Valor"] = df_despesas["Valor"].apply(clean_currency)
                df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], format="%d/%m/%Y", errors="coerce")
                df_despesas["Dias até"] = df_despesas["Dias até"].apply(clean_int)
                db_manager.clear_table("despesas")
                db_manager.save_dataframe_delta("despesas", df_despesas, None)
                
            # Dividendos
            df_dividendos = load_sheet_data(budget_id, "Dividendos")
            if not df_dividendos.empty:
                col_mapping = {}
                for col in df_dividendos.columns:
                    if "recebido" in col.lower():
                        col_mapping[col] = "Recebido em"
                    elif "dias" in col.lower():
                        col_mapping[col] = "Dias até"
                if col_mapping:
                    df_dividendos = df_dividendos.rename(columns=col_mapping)
                    
                if "Nome" in df_dividendos.columns:
                    df_dividendos["Nome"] = df_dividendos["Nome"].astype(str).str.strip()
                if "Ativo" in df_dividendos.columns:
                    df_dividendos["Ativo"] = df_dividendos["Ativo"].astype(str).str.strip()
                if "Categoria" in df_dividendos.columns:
                    df_dividendos["Categoria"] = df_dividendos["Categoria"].astype(str).str.strip()
                if "Valor" in df_dividendos.columns:
                    df_dividendos["Valor"] = df_dividendos["Valor"].apply(clean_currency)
                    
                df_dividendos["Recebido em"] = pd.to_datetime(df_dividendos["Recebido em"], format="%d/%m/%Y", errors="coerce")
                if "Dias até" in df_dividendos.columns:
                    df_dividendos["Dias até"] = df_dividendos["Dias até"].apply(clean_int)
                db_manager.clear_table("dividendos")
                db_manager.save_dataframe_delta("dividendos", df_dividendos, None)
        except Exception as e:
            logger.error(f"Erro ao sincronizar aba Orçamento: {e}")
            
    db_manager.set_last_sync_time()
    logger.info("Sincronização delta incremental concluída com sucesso.")

# Dicionário de Tradução Contábil Inglês -> Português (PT-BR)
TERMOS_CONTABEIS = {
    # Income Statement (DRE)
    "Total Revenue": "Receita Líquida",
    "Operating Revenue": "Receita Operacional",
    "Cost Of Revenue": "Custos dos Serviços/Produtos",
    "Gross Profit": "Lucro Bruto",
    "Operating Expense": "Despesas Operacionais",
    "Research And Development": "Pesquisa e Desenvolvimento (P&D)",
    "Selling General And Administrative": "Despesas de Vendas, Gerais e Admin (SG&A)",
    "Selling General And Administration": "Despesas de Vendas, Gerais e Administrativas (SG&A)",
    "Selling And Marketing Expense": "Despesas de Vendas e Marketing",
    "General And Administrative Expense": "Despesas Gerais e Administrativas",
    "Amortization": "Amortização",
    "Depreciation And Amortization": "Depreciação e Amortização (D&A)",
    "Operating Income": "Resultado Operacional (EBIT)",
    "Net Non Operating Interest Income Expense": "Resultado Financeiro Líquido",
    "Interest Income": "Receitas Financeiras",
    "Interest Expense": "Despesas Financeiras",
    "Normalized Income": "Lucro Líquido Normalizado",
    "Pretax Income": "Lucro Antes de Impostos (LAIR)",
    "Tax Provision": "Impostos e Provisões",
    "Net Income": "Lucro Líquido",
    "Net Income Common Stockholders": "Lucro Líquido aos Acionistas",
    "EBITDA": "EBITDA",
    "EBIT": "EBIT",
    "Diluted Average Shares": "Média de Ações Diluídas",
    "Diluted EPS": "LPA Diluído (Lucro por Ação)",
    "Normalized EBITDA": "EBITDA Normalizado",
    "Net Income Including Noncontrolling Interests": "Lucro Líquido Incluindo Não Controladores",
    "Net Income From Continuing Operation Net Minority Interest": "Lucro Líquido de Operações Continuadas (Controladores)",
    "Net Income From Continuing And Discontinued Operation": "Lucro Líquido de Operações Continuadas e Descontinuadas",
    "Net Income Continuous Operations": "Lucro Líquido de Operações Continuadas",
    "Basic EPS": "LPA Básico (Lucro por Ação)",
    "Diluted NI Availto Com Stockholders": "Lucro Líquido Diluído Disponível aos Acionistas",
    "Other Income Expense": "Outras Receitas/Despesas Operacionais",
    "Reconciled Cost Of Revenue": "Custo da Receita Reconciliado",
    "Other Non Operating Income Expenses": "Outras Receitas/Despesas Não Operacionais",
    "Reconciled Depreciation": "Depreciação Reconciliada",
    "Tax Effect Of Unusual Items": "Efeito Fiscal de Itens Extraordinários",
    "Tax Rate For Calcs": "Alíquota de Imposto Efetiva",
    "Total Expenses": "Despesas Totais",
    "Basic Average Shares": "Média de Ações Básicas",
    "Total Operating Income As Reported": "Resultado Operacional Reportado",
    
    # Balance Sheet (Balanço Patrimonial)
    "Total Assets": "Ativo Total",
    "Current Assets": "Ativo Circulante",
    "Cash And Cash Equivalents": "Caixa e Equivalentes de Caixa",
    "Cash Cash Equivalents And Short Term Investments": "Caixa, Equivalentes e Aplicações",
    "Cash Equivalents": "Equivalentes de Caixa",
    "Cash Financial": "Caixa Financeiro",
    "Other Short Term Investments": "Aplicações Financeiras CP",
    "Receivables": "Contas a Receber",
    "Accounts Receivable": "Clientes / Contas a Receber",
    "Other Receivables": "Outros Contas a Receber",
    "Inventory": "Estoques",
    "Raw Materials": "Matéria-Prima",
    "Finished Goods": "Produtos Acabados",
    "Prepaid Assets": "Despesas Antecipadas",
    "Other Current Assets": "Outros Ativos Circulantes",
    "Non Current Assets": "Ativo Não Circulante",
    "Net PPE": "Imobilizado Líquido",
    "Gross PPE": "Ativo Imobilizado Bruto",
    "Accumulated Depreciation": "Depreciação Acumulada",
    "Properties": "Propriedades e Equipamentos",
    "Land And Improvements": "Terrenos e Benfeitorias",
    "Machinery Furniture Equipment": "Máquinas, Móveis e Equipamentos",
    "Leases": "Arrendamentos / Leasing",
    "Goodwill And Other Intangible Assets": "Ágio e Intangíveis",
    "Goodwill": "Ágio / Goodwill",
    "Intangible Assets": "Ativos Intangíveis",
    "Investments And Advances": "Investimentos e Adiantamentos",
    "Investmentsin Associatesand Jointventures": "Investimentos em Coligadas/Joint Ventures",
    "Investmentin Financial Assets": "Investimentos em Ativos Financeiros",
    "Non Current Deferred Assets": "Ativo Diferido (LP)",
    "Non Current Deferred Taxes Assets": "Ativos Fiscais Diferidos (LP)",
    "Other Non Current Assets": "Outros Ativos Não Circulantes",
    "Total Non Current Assets": "Ativo Não Circulante Total",
    
    "Total Liabilities Net Minority Interest": "Passivo Total + PL",
    "Total Liabilities": "Passivo Total",
    "Current Liabilities": "Passivo Circulante",
    "Payables": "Contas a Pagar",
    "Accounts Payable": "Fornecedores / Contas a Pagar",
    "Payables And Accrued Expenses": "Contas a Pagar e Despesas Apropriadas",
    "Tradeand Other Payables Non Current": "Outras Contas a Pagar LP",
    "Short Term Debt": "Empréstimos e Financiamentos CP",
    "Current Debt And Capital Lease Obligation": "Dívida de Curto Prazo",
    "Current Debt": "Dívida de Curto Prazo (CP)",
    "Commercial Paper": "Notas Comerciais",
    "Other Current Borrowings": "Outras Obrigações Financeiras CP",
    "Current Accrued Expenses": "Despesas Apropriadas a Pagar (CP)",
    "Current Deferred Liabilities": "Passivo Diferido (CP)",
    "Current Deferred Revenue": "Receita Diferida / Adiantamentos de Clientes",
    "Income Tax Payable": "Imposto de Renda a Pagar",
    "Total Tax Payable": "Total de Impostos a Pagar",
    "Other Current Liabilities": "Outros Passivos Circulantes",
    "Non Current Liabilities": "Passivo Não Circulante",
    "Long Term Debt": "Empréstimos e Financiamentos LP",
    "Long Term Debt And Capital Lease Obligation": "Dívida de Longo Prazo",
    "Other Non Current Liabilities": "Outros Passivos Não Circulantes",
    "Total Non Current Liabilities Net Minority Interest": "Passivo Não Circulante Total",
    
    "Stockholders Equity": "Patrimônio Líquido (PL)",
    "Common Stock Equity": "Patrimônio Líquido Ordinário",
    "Capital Stock": "Capital Social",
    "Common Stock": "Ações Ordinárias (Capital)",
    "Retained Earnings": "Lucros Acumulados",
    "Treasury Stock": "Ações em Tesouraria",
    "Other Equity Adjustments": "Outros Ajustes do Patrimônio Líquido",
    "Other Equity Interest": "Outros Itens do PL",
    "Gains Losses Not Affecting Retained Earnings": "Ajustes de Avaliação Patrimonial",
    "Total Equity Gross Minority Interest": "Patrimônio Líquido Total + Participação de Não Controladores",
    "Net Debt": "Dívida Líquida",
    "Total Debt": "Dívida Bruta",
    "Ordinary Shares Number": "Quantidade de Ações Ordinárias",
    "Share Issued": "Ações Emitidas",
    "Tangible Book Value": "Valor Patrimonial Tangível",
    "Net Tangible Assets": "Ativos Tangíveis Líquidos",
    "Invested Capital": "Capital Investido",
    "Total Capitalization": "Capitalização Total",
    "Working Capital": "Capital de Giro",
    "Available For Sale Securities": "Títulos Disponíveis para Venda",
    
    # Cash Flow (Fluxo de Caixa)
    "Operating Cash Flow": "Fluxo de Caixa Operacional (FCO)",
    "Investing Cash Flow": "Fluxo de Caixa de Investimentos (FCI)",
    "Capital Expenditure": "Investimento em Ativos (CapEx)",
    "Financing Cash Flow": "Fluxo de Caixa de Financiamentos (FCF)",
    "Net Income From Continuing Operations": "Lucro Líquido Operações Continuadas",
    "Free Cash Flow": "Fluxo de Caixa Livre (FCL)",
    "End Cash Position": "Saldo de Caixa Final",
    "Beginning Cash Position": "Saldo de Caixa Inicial",
    "Changes In Cash": "Variação Líquida de Caixa",
    "Repurchase Of Capital Stock": "Recompra de Ações",
    "Common Stock Dividend Paid": "Dividendos Pagos",
    "Change In Inventory": "Variação de Estoques",
    "Change In Other Current Assets": "Variação de Outros Ativos Circulantes",
    "Cash Flow From Continuing Investing Activities": "FCO - Atividades de Investimento",
    "Cash Flow From Continuing Operating Activities": "FCO - Atividades Operacionais",
    "Change In Payable": "Variação de Fornecedores / Contas a Pagar",
    "Cash Dividends Paid": "Dividendos em Dinheiro Pagos",
    "Changes In Account Receivables": "Variação de Contas a Receber",
    "Change In Working Capital": "Variação de Capital de Giro",
    "Change In Receivables": "Variação de Contas a Receber",
    "Change In Payables And Accrued Expense": "Variação de Contas a Pagar e Despesas Apropriadas",
    "Change In Other Current Liabilities": "Variação de Outros Passivos Circulantes",
    "Common Stock Payments": "Pagamento de Ações Ordinárias / Redução de Capital",
    "Depreciation Amortization Depletion": "Depreciação, Amortização e Exaustão",
    "Income Tax Paid Supplemental Data": "Imposto de Renda Pago (Dado Suplementar)",
    "Issuance Of Debt": "Emissão de Dívida / Captação de Recursos",
    "Long Term Debt Issuance": "Emissão de Dívida de Longo Prazo",
    "Long Term Debt Payments": "Pagamento de Dívida de Longo Prazo",
    "Net Common Stock Issuance": "Emissão Líquida de Ações",
    "Change In Account Payable": "Variação de Fornecedores / Contas a Pagar",
    "Cash Flow From Continuing Financing Activities": "FCO - Atividades de Financiamento",
    "Net Issuance Payments Of Debt": "Captação/Amortização Líquida de Dívida",
    "Net Investment Purchase And Sale": "Compra e Venda Líquida de Investimentos",
    "Net Other Investing Changes": "Outras Variações Líquidas de Investimento",
    "Net Long Term Debt Issuance": "Emissão/Amortização Líquida de Dívida LP",
    "Net PPE Purchase And Sale": "Compra e Venda Líquida de Imobilizado (CapEx Líquido)",
    "Net Short Term Debt Issuance": "Emissão/Amortização Líquida de Dívida CP",
    "Other Non Cash Items": "Outros Ajustes Sem Efeito de Caixa",
    "Net Other Financing Charges": "Outros Fluxos Líquidos de Financiamento",
    "Purchase Of Investment": "Compra de Investimentos",
    "Purchase Of PPE": "Aquisição de Imobilizado (CapEx)",
    "Repayment Of Debt": "Amortização de Dívidas",
    "Sale Of Investment": "Venda de Investimentos",
    "Short Term Debt Payments": "Pagamento de Dívida de Curto Prazo",
    "Stock Based Compensation": "Remuneração Baseada em Ações",
}

def sync_fundamental_data_from_yfinance(ticker_orig):
    """
    Busca os demonstrativos financeiros do yfinance e salva no SQLite local.
    """
    import yfinance as yf
    import db_manager
    from analytics import normalize_ticker, is_valid_yfinance_ticker
    
    ticker_norm = normalize_ticker(ticker_orig)
    if not is_valid_yfinance_ticker(ticker_orig):
        logger.warning(f"Ticker {ticker_orig} não é elegível para dados fundamentalistas.")
        return False
        
    logger.info(f"Iniciando sincronização de dados fundamentalistas para {ticker_norm}...")
    try:
        ticker_obj = yf.Ticker(ticker_norm)
        
        # Demonstrativos Anuais
        try:
            db_manager.save_fundamental_data(ticker_orig, "balanco", "anual", ticker_obj.balance_sheet)
        except Exception as e:
            logger.error(f"Erro ao salvar balanco anual para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "dre", "anual", ticker_obj.income_stmt)
        except Exception as e:
            logger.error(f"Erro ao salvar dre anual para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "fluxo", "anual", ticker_obj.cashflow)
        except Exception as e:
            logger.error(f"Erro ao salvar fluxo anual para {ticker_orig}: {e}")
            
        # Demonstrativos Trimestrais
        try:
            db_manager.save_fundamental_data(ticker_orig, "balanco", "trimestral", ticker_obj.quarterly_balance_sheet)
        except Exception as e:
            logger.error(f"Erro ao salvar balanco trimestral para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "dre", "trimestral", ticker_obj.quarterly_income_stmt)
        except Exception as e:
            logger.error(f"Erro ao salvar dre trimestral para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "fluxo", "trimestral", ticker_obj.quarterly_cashflow)
        except Exception as e:
            logger.error(f"Erro ao salvar fluxo trimestral para {ticker_orig}: {e}")
            
        return True
    except Exception as e:
        logger.error(f"Erro ao baixar dados fundamentalistas do yfinance para {ticker_orig}: {e}")
        return False
