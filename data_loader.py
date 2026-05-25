import os
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import streamlit as st

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

def clean_int(val):
    """
    Converte valores inteiros de forma segura.
    """
    if pd.isna(val) or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    
    val_str = str(val).strip().replace(".", "")
    try:
        return int(val_str)
    except ValueError:
        try:
            return int(float(val_str))
        except ValueError:
            return 0

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
            # Caso esteja vazia ou get_all_records não capture cabeçalhos corretamente
            data = worksheet.get_all_values()
            if len(data) > 1:
                headers = [h.strip() for h in data[0]]
                rows = data[1:]
                df = pd.DataFrame(rows, columns=headers)
            else:
                return pd.DataFrame()
        else:
            df = pd.DataFrame(records)
            
        # Limpa espaços em branco dos nomes das colunas
        df.columns = [col.strip() for col in df.columns]
        return df
    except Exception as e:
        st.error(f"Erro ao carregar a aba '{sheet_name}' da planilha '{spreadsheet_id}': {e}")
        return pd.DataFrame()

def get_mock_data():
    """
    Gera dados simulados de alta qualidade para demonstração do aplicativo.
    """
    # 1. Receitas Simuladas
    receitas_data = [
        {"Nome": "Salário Principal", "Valor": 8500.0, "Categoria": "Trabalho", "Recebido em": "05/05/2026", "Dias até": 0},
        {"Nome": "Projeto Freelance", "Valor": 2200.0, "Categoria": "Renda Extra", "Recebido em": "12/05/2026", "Dias até": 0},
    ]
    df_receitas = pd.DataFrame(receitas_data)
    df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], format="%d/%m/%Y")
    df_receitas["Valor"] = df_receitas["Valor"].astype(float)
    df_receitas["Dias até"] = df_receitas["Dias até"].astype(int)

    # 2. Despesas Simuladas
    despesas_data = [
        {"Nome": "Aluguel & Condomínio", "Valor": 2800.0, "Categoria": "Moradia", "Conta debitada": "Itaú", "Gasto em": "02/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo"},
        {"Nome": "Supermercado", "Valor": 1100.0, "Categoria": "Alimentação", "Conta debitada": "Nubank", "Gasto em": "10/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável"},
        {"Nome": "Combustível", "Valor": 450.0, "Categoria": "Transporte", "Conta debitada": "Nubank", "Gasto em": "15/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável"},
        {"Nome": "Academia", "Valor": 150.0, "Categoria": "Saúde", "Conta debitada": "Nubank", "Gasto em": "05/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo"},
        {"Nome": "Streaming & Internet", "Valor": 180.0, "Categoria": "Lazer", "Conta debitada": "Itaú", "Gasto em": "08/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo"},
        {"Nome": "Jantar Fora", "Valor": 350.0, "Categoria": "Lazer", "Conta debitada": "Nubank", "Gasto em": "20/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável"},
    ]
    df_despesas = pd.DataFrame(despesas_data)
    df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], format="%d/%m/%Y")
    df_despesas["Valor"] = df_despesas["Valor"].astype(float)
    df_despesas["Dias até"] = df_despesas["Dias até"].astype(int)

    # 3. Dividendos Simulados
    dividendos_data = [
        {"Nome": "Rendimento HGLG11", "Valor": 110.0, "Ativo": "HGLG11", "Categoria": "FIIs", "Recebido em": "15/05/2026", "Dias até": 0},
        {"Nome": "Dividendos PETR4", "Valor": 320.0, "Ativo": "PETR4", "Categoria": "Ações", "Recebido em": "20/05/2026", "Dias até": 0},
        {"Nome": "Proventos WEGE3", "Valor": 45.0, "Ativo": "WEGE3", "Categoria": "Ações", "Recebido em": "22/05/2026", "Dias até": 0},
    ]
    df_dividendos = pd.DataFrame(dividendos_data)
    df_dividendos["Recebido em"] = pd.to_datetime(df_dividendos["Recebido em"], format="%d/%m/%Y")
    df_dividendos["Valor"] = df_dividendos["Valor"].astype(float)
    df_dividendos["Dias até"] = df_dividendos["Dias até"].astype(int)

    # 4. Ordens Simuladas (Para simular rentabilidade de 2025 até 2026)
    ordens_data = [
        # Compras Iniciais (Início de 2025)
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "WEGE3", "Qtd Executada": 100, "Preço médio": 35.0, "Total": 3500.0, "data envio": "15/01/2025 10:30:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 35.0, "Total líquido": 3500.0},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "PETR4", "Qtd Executada": 150, "Preço médio": 28.0, "Total": 4200.0, "data envio": "18/01/2025 11:15:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 28.0, "Total líquido": 4200.0},
        {"Compra/Venda": "Compra", "Tipo": "FIIs", "Moeda": "BRL", "Papel": "HGLG11", "Qtd Executada": 50, "Preço médio": 155.0, "Total": 7750.0, "data envio": "20/01/2025 14:00:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 155.0, "Total líquido": 7750.0},
        
        # Aportes adicionais (Meio de 2025)
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "VALE3", "Qtd Executada": 50, "Preço médio": 62.0, "Total": 3100.0, "data envio": "10/07/2025 10:45:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 62.0, "Total líquido": 3100.0},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "WEGE3", "Qtd Executada": 50, "Preço médio": 38.5, "Total": 1925.0, "data envio": "12/07/2025 15:20:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 38.5, "Total líquido": 1925.0},
        
        # Aportes Recentes (Início de 2026)
        {"Compra/Venda": "Compra", "Tipo": "Internacional", "Moeda": "USD", "Papel": "IVV", "Qtd Executada": 10, "Preço médio": 480.0, "Total": 4800.0, "data envio": "05/01/2026 16:00:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 480.0, "Total líquido": 24000.0}, # Total líquido convertido para BRL (aprox 5.0)
    ]
    df_ordens = pd.DataFrame(ordens_data)
    df_ordens["data envio"] = pd.to_datetime(df_ordens["data envio"], format="%d/%m/%Y %H:%M:%S")
    
    return df_receitas, df_despesas, df_dividendos, df_ordens

def get_budget_data(use_mock=False):
    """
    Carrega e limpa os dados da Planilha de Orçamento 2026 (Abas: Receitas, Despesas, Dividendos).
    """
    load_dotenv(override=True)
    if use_mock:
        df_r, df_d, df_div, _ = get_mock_data()
        return df_r, df_d, df_div
        
    budget_id = os.getenv("SPREADSHEET_BUDGET_ID")
    if not budget_id:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    # 1. Carrega Receitas
    df_receitas = load_sheet_data(budget_id, "Receitas")
    if not df_receitas.empty:
        # Garante conversão estrita para strings para evitar erros com o PyArrow do Streamlit
        df_receitas["Nome"] = df_receitas["Nome"].astype(str).str.strip()
        df_receitas["Categoria"] = df_receitas["Categoria"].astype(str).str.strip()
        df_receitas["Valor"] = df_receitas["Valor"].apply(clean_currency)
        df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], format="%d/%m/%Y", errors="coerce")
        df_receitas["Dias até"] = df_receitas["Dias até"].apply(clean_int)
        
    # 2. Carrega Despesas
    df_despesas = load_sheet_data(budget_id, "Despesas")
    if not df_despesas.empty:
        # Garante conversão estrita para strings para evitar erros com o PyArrow do Streamlit
        df_despesas["Nome"] = df_despesas["Nome"].astype(str).str.strip()
        df_despesas["Categoria"] = df_despesas["Categoria"].astype(str).str.strip()
        if "Conta debitada" in df_despesas.columns:
            df_despesas["Conta debitada"] = df_despesas["Conta debitada"].astype(str).str.strip()
        if "Tipo de Cobrança" in df_despesas.columns:
            df_despesas["Tipo de Cobrança"] = df_despesas["Tipo de Cobrança"].astype(str).str.strip()
            
        df_despesas["Valor"] = df_despesas["Valor"].apply(clean_currency)
        df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], format="%d/%m/%Y", errors="coerce")
        df_despesas["Dias até"] = df_despesas["Dias até"].apply(clean_int)
        
    # 3. Carrega Dividendos
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
            
    return df_receitas, df_despesas, df_dividendos

def get_orders_data(use_mock=False):
    """
    Carrega e limpa os dados da Planilha de Ordens.
    """
    load_dotenv(override=True)
    if use_mock:
        _, _, _, df_o = get_mock_data()
        return df_o
        
    orders_id = os.getenv("SPREADSHEET_ORDERS_ID")
    if not orders_id:
        return pd.DataFrame()
        
    df_orders = load_sheet_data(orders_id, "Ordens")
    
    if df_orders.empty:
        try:
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
        except Exception as e:
            st.error(f"Erro ao carregar a primeira aba da planilha de ordens: {e}")
            
    if not df_orders.empty:
        # Normalização case-insensitive e tolerante das colunas da Planilha de Ordens
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
                
        if col_mapping:
            df_orders = df_orders.rename(columns=col_mapping)
            
        # Fallbacks e segurança contra KeyErrors
        if "data envio" not in df_orders.columns:
            for col in df_orders.columns:
                if "data" in str(col).lower():
                    df_orders = df_orders.rename(columns={col: "data envio"})
                    break
            if "data envio" not in df_orders.columns:
                st.error(f"⚠️ A coluna com a Data de Envio não foi encontrada na Planilha de Ordens! Colunas detectadas: {list(df_orders.columns)}")
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
                    
        # Sanitização e tipos das colunas numéricas
        numeric_cols = ["Qtd Executada", "Preço médio", "Total", "Corretagem", "Preço médio + corretagem", "Total líquido"]
        for col in numeric_cols:
            if col in df_orders.columns:
                if col == "Qtd Executada":
                    df_orders[col] = df_orders[col].apply(clean_int)
                else:
                    df_orders[col] = df_orders[col].apply(clean_currency)
            else:
                # Preenche colunas ausentes com zeros
                df_orders[col] = 0.0
                    
        if "data envio" in df_orders.columns:
            # Copia os dados originais em string para evitar sobrescrita com NaT
            raw_dates = df_orders["data envio"].copy()
            # Converte as datas de forma robusta no padrão brasileiro (dia primeiro)
            df_orders["data envio"] = pd.to_datetime(raw_dates, dayfirst=True, errors="coerce")
                
        string_cols = ["Compra/Venda", "Tipo", "Moeda", "Papel"]
        for col in string_cols:
            if col in df_orders.columns:
                df_orders[col] = df_orders[col].astype(str).str.strip()
            else:
                df_orders[col] = ""
                
    return df_orders
