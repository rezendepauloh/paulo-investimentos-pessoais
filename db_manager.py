import os
import sqlite3
import pandas as pd
import datetime
import logging

logger = logging.getLogger("DBManager")

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "investimentos.db")

def init_db():
    """
    Inicializa o banco de dados SQLite local, criando o diretório e as tabelas necessárias.
    """
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Tabela de Ordens
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_envio TEXT,
            compra_venda TEXT,
            papel TEXT,
            qtd_executada REAL,
            preco_medio REAL,
            total_liquido REAL,
            moeda TEXT,
            tipo TEXT,
            total REAL,
            corretagem REAL,
            preco_medio_corretagem REAL,
            cod_cliente TEXT,
            setor_economico TEXT,
            indexador TEXT,
            taxa_indexador REAL
        )
    """)
    try:
        cursor.execute("ALTER TABLE ordens ADD COLUMN setor_economico TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE ordens ADD COLUMN indexador TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE ordens ADD COLUMN taxa_indexador REAL")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ordens_delta ON ordens (data_envio, papel, compra_venda, qtd_executada, total_liquido)")
    
    # 2. Tabela de Receitas (Orçamento)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor REAL,
            categoria TEXT,
            recebido_em TEXT,
            dias_ate INTEGER
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_receitas_delta ON receitas (nome, valor, recebido_em)")
    
    # 3. Tabela de Despesas (Orçamento)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor REAL,
            categoria TEXT,
            conta_debitada TEXT,
            gasto_em TEXT,
            dias_ate INTEGER,
            tipo_cobranca TEXT,
            fixo_variavel TEXT,
            essencial_nao_essencial TEXT
        )
    """)
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN fixo_variavel TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN essencial_nao_essencial TEXT")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_despesas_delta ON despesas (nome, valor, gasto_em)")
    
    # 4. Tabela de Dividendos (Orçamento)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dividendos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor REAL,
            ativo TEXT,
            categoria TEXT,
            recebido_em TEXT,
            dias_ate INTEGER
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dividendos_delta ON dividendos (nome, valor, recebido_em, ativo)")
    
    # 5. Tabela de Metadados de Sincronização
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    
    # 6. Tabela de Preços Históricos (yfinance cache)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS precos_historicos (
            ticker TEXT,
            data TEXT,
            preco_fechamento REAL,
            PRIMARY KEY (ticker, data)
        )
    """)
    
    # 7. Tabela de tickers que falharam no yfinance (delisted)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failed_tickers (
            ticker TEXT PRIMARY KEY
        )
    """)
    
    # Limpa cotações de placeholder corrompidas de 0.01 criadas anteriormente
    cursor.execute("DELETE FROM precos_historicos WHERE preco_fechamento = 0.01")
    
    conn.commit()
    conn.close()
    logger.info("Banco de dados SQLite inicializado com sucesso em %s", DB_PATH)
 
def get_db_connection():
    """
    Retorna uma conexão ativa com o banco SQLite.
    """
    init_db()
    return sqlite3.connect(DB_PATH)
 
def set_last_sync_time():
    """
    Salva o timestamp da última sincronização bem sucedida com o Google Sheets.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cursor.execute("INSERT OR REPLACE INTO sync_metadata (chave, valor) VALUES ('last_sync', ?)", (now_str,))
    conn.commit()
    conn.close()
 
def get_last_sync_time():
    """
    Retorna o timestamp da última sincronização.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM sync_metadata WHERE chave = 'last_sync'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "Nunca sincronizado"
 
def save_dataframe_delta(table_name, df, unique_cols_mapping):
    """
    Salva dados de um DataFrame do Pandas na tabela local do SQLite utilizando lógica de Delta (incremental).
    Evita a inserção de registros duplicados com base nos índices únicos declarados.
    """
    if df.empty:
        return 0
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Mapeia colunas do DF para a tabela do SQLite (conversão de tipos e tratamento de datas)
    df_temp = df.copy()
    
    # Normaliza nomes de colunas do Pandas para casar com o banco SQLite
    cols_rename = {
        "Data envio": "data_envio",
        "data envio": "data_envio",
        "Compra/Venda": "compra_venda",
        "Papel": "papel",
        "Qtd Executada": "qtd_executada",
        "Preço médio": "preco_medio",
        "Total líquido": "total_liquido",
        "Moeda": "moeda",
        "Tipo": "tipo",
        "Total": "total",
        "Corretagem": "corretagem",
        "Preço médio + corretagem": "preco_medio_corretagem",
        "Cód. Cliente": "cod_cliente",
        "Nome": "nome",
        "Valor": "valor",
        "Categoria": "categoria",
        "Recebido em": "recebido_em",
        "Dias até": "dias_ate",
        "Conta debitada": "conta_debitada",
        "Gasto em": "gasto_em",
        "Indexador": "indexador",
        "Taxa Indexador": "taxa_indexador",
        "Taxa Index": "taxa_indexador",
        "Tipo de Cobrança": "tipo_cobranca",
        "Ativo": "ativo",
        "Fixo vs. Variável": "fixo_variavel",
        "Essencial vs. Não Essencial": "essencial_nao_essencial",
        "Setor Econômico": "setor_economico"
    }
    
    df_temp = df_temp.rename(columns=cols_rename)
    
    # Filtra apenas as colunas existentes na tabela destino
    cursor.execute(f"PRAGMA table_info({table_name})")
    db_cols = [row[1] for row in cursor.fetchall() if row[1] != 'id']
    
    df_temp = df_temp[[col for col in df_temp.columns if col in db_cols]]
    
    # Converte colunas de data/datetime para strings normais do SQLite
    for col in df_temp.columns:
        if pd.api.types.is_datetime64_any_dtype(df_temp[col]):
            df_temp[col] = df_temp[col].dt.strftime("%Y-%m-%d %H:%M:%S")
            
    # Executa a inserção em lote com 'INSERT OR IGNORE' (Delta Sincronização)
    cols_placeholder = ", ".join(["?"] * len(df_temp.columns))
    cols_str = ", ".join(df_temp.columns)
    sql = f"INSERT OR IGNORE INTO {table_name} ({cols_str}) VALUES ({cols_placeholder})"
    
    rows_inserted = 0
    records = [tuple(row) for row in df_temp.to_numpy()]
    
    try:
        cursor.executemany(sql, records)
        rows_inserted = cursor.rowcount
        conn.commit()
    except Exception as e:
        logger.error("Erro ao realizar sincronização delta na tabela %s: %s", table_name, e)
        conn.rollback()
    finally:
        conn.close()
        
    logger.info("Sincronização Delta concluída na tabela %s: %d novos registros adicionados.", table_name, max(0, rows_inserted))
    return max(0, rows_inserted)

def clear_table(table_name):
    """
    Limpa todos os dados de uma tabela específica (caso seja necessário resetar o cache).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table_name}")
    conn.commit()
    conn.close()

def save_historical_prices(prices_list):
    """
    Salva ou atualiza a lista de cotações históricas diárias no SQLite.
    Cada elemento da lista deve ser uma tupla/lista: (ticker, data_str, preco_fechamento)
    """
    if not prices_list:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "INSERT OR REPLACE INTO precos_historicos (ticker, data, preco_fechamento) VALUES (?, ?, ?)"
    rows_affected = 0
    try:
        cursor.executemany(sql, prices_list)
        rows_affected = cursor.rowcount
        conn.commit()
    except Exception as e:
        logger.error("Erro ao salvar preços históricos no SQLite: %s", e)
        conn.rollback()
    finally:
        conn.close()
    return max(0, rows_affected)
