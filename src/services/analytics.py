import datetime
import os
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
from src.database import db_manager
from src.utils.logger import get_logger

logger = get_logger("services", "analytics")


@st.cache_data(ttl=86400)
def get_historical_cdi(start_date: datetime.date, end_date: datetime.date):
    """
    Busca a taxa CDI diária (Série 12 do SGS/BCB) no intervalo de datas,
    calcula o fator acumulado e retorna uma série temporal com o fator de retorno acumulado.
    """
    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")
    
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={start_str}&dataFinal={end_str}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if not data:
                return pd.Series(dtype=float)
            
            df = pd.DataFrame(data)
            df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
            df["valor"] = df["valor"].astype(float) / 100.0  # CDI é expresso em porcentagem diária (ex: 0.0412%)
            
            df = df.sort_values("data").reset_index(drop=True)
            # Fator de acumulação: prod(1 + cdi_diario)
            df["fator_acumulado"] = (1.0 + df["valor"]).cumprod()
            
            # Indexa por data e reamostra para ter todos os dias corridos preenchendo com ffill
            df.set_index("data", inplace=True)
            df = df.reindex(pd.date_range(start=start_date, end=end_date), method="ffill")
            # Caso os primeiros dias sejam NaN por falta de dados de feriado/fim de semana
            df["fator_acumulado"] = df["fator_acumulado"].ffill().bfill().fillna(1.0)
            
            st.session_state["bcb_cdi_status"] = "OK"
            return df["fator_acumulado"]
    except Exception as e:
        logger.warning(f"Não foi possível obter os dados do CDI da API do Banco Central: {e}")
        st.session_state["bcb_cdi_status"] = f"TIMEOUT: {e}"
        
    # Fallback aproximado (11% ao ano constante de CDI caso a API falhe)
    dates = pd.date_range(start=start_date, end=end_date)
    daily_rate = (1.11) ** (1/252) - 1.0
    fator = (1.0 + daily_rate) ** np.arange(1, len(dates) + 1)
    return pd.Series(fator, index=dates)

@st.cache_data(ttl=86400)
def get_historical_ipca(start_date: datetime.date, end_date: datetime.date):
    """
    Busca o IPCA mensal (Série 433 do SGS/BCB) no intervalo de datas,
    e retorna o fator acumulado diário aproximado por interpolação ou ffill.
    """
    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")
    
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial={start_str}&dataFinal={end_str}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if not data:
                return pd.Series(dtype=float)
                
            df = pd.DataFrame(data)
            df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
            df["valor"] = df["valor"].astype(float) / 100.0  # IPCA é variação percentual mensal
            
            df = df.sort_values("data").reset_index(drop=True)
            df["fator_acumulado"] = (1.0 + df["valor"]).cumprod()
            
            df.set_index("data", inplace=True)
            # Reamostra diariamente e preenche com ffill
            df = df.reindex(pd.date_range(start=start_date, end=end_date), method="ffill")
            df["fator_acumulado"] = df["fator_acumulado"].ffill().bfill().fillna(1.0)
            
            st.session_state["bcb_ipca_status"] = "OK"
            return df["fator_acumulado"]
    except Exception as e:
        logger.warning(f"Não foi possível obter os dados do IPCA da API do Banco Central: {e}")
        st.session_state["bcb_ipca_status"] = f"TIMEOUT: {e}"
        
    # Fallback aproximado (4.5% ao ano constante de IPCA caso a API falhe)
    dates = pd.date_range(start=start_date, end=end_date)
    daily_rate = (1.045) ** (1/365) - 1.0
    fator = (1.0 + daily_rate) ** np.arange(1, len(dates) + 1)
    return pd.Series(fator, index=dates)

def clear_bcb_cache():
    """
    Limpa os caches de dados macroeconômicos do Banco Central e histórico de performance.
    """
    get_historical_cdi.clear()
    get_historical_ipca.clear()
    get_historical_performance.clear()
    if "bcb_cdi_status" in st.session_state:
        del st.session_state["bcb_cdi_status"]
    if "bcb_ipca_status" in st.session_state:
        del st.session_state["bcb_ipca_status"]
    logger.info("Cache de CDI, IPCA e Performance limpos para re-tentativa.")


def is_valid_yfinance_ticker(ticker: str, asset_type: str = None) -> bool:
    """
    Verifica se um ticker é válido para consulta no Yahoo Finance.
    Retorna False para Renda Fixa, Contas, Dinheiro ou outros ativos não cotados publicamente.
    """
    t = str(ticker).strip().upper()
    if not t or t in ["CONTA", "CAPITAL", "CAIXA", "SALDO", "CDB", "LCI", "LCA", "TESOURO", "POUPANÇA", "POUPANCA"]:
        return False
        
    if asset_type:
        atype = str(asset_type).strip().upper()
        if atype in ["RENDA FIXA", "OUTROS", "CASH", "CONTA", "TESOURO DIRETO", "CDB", "POUPANÇA", "POUPANCA"]:
            return False
            
    # Se contiver espaços ou for excessivamente longo, não é um ticker de mercado
    if " " in t or len(t) > 10:
        return False
        
    return True

def normalize_ticker(ticker: str):
    """
    Normaliza os códigos dos papéis para o formato correto no Yahoo Finance.
    Adiciona .SA para ações brasileiras e FIIs, a menos que seja um índice global ou cripto.
    """
    t = str(ticker).strip().upper()
    if not t:
        return ""
    
    # Se já tiver .SA ou for índice internacional (^GSPC, ^BVSP), ou paridade de cripto
    if t.endswith(".SA") or t.startswith("^") or "-" in t or len(t) > 6:
        return t
        
    # Se for ativo brasileiro (Geralmente 4 letras e 1 ou 2 números, ex: PETR4, VALE3, HGLG11)
    if any(char.isdigit() for char in t):
        return f"{t}.SA"
        
    return t

@st.cache_data(ttl=3600)
def get_current_prices(tickers, ticker_types=None):
    """
    Obtém a cotação atual (tempo real) para uma lista de tickers usando yfinance.
    Retorna um dicionário {ticker_original: preco_atual}.
    """
    prices = {}
    if ticker_types is None:
        ticker_types = {}
        
    valid_tickers = []
    for t in tickers:
        if not t:
            continue
        asset_type = ticker_types.get(t, None)
        if is_valid_yfinance_ticker(t, asset_type):
            valid_tickers.append(t)
            
    normalized_map = {normalize_ticker(t): t for t in valid_tickers}
    
    if not normalized_map:
        return prices
        
    try:
        # Busca todas as cotações em lote
        tickers_str = " ".join(normalized_map.keys())
        data = yf.download(tickers_str, period="1d", group_by="ticker", progress=False, timeout=10)
        
        for norm_t, orig_t in normalized_map.items():
            try:
                if len(normalized_map) == 1:
                    # Se for apenas um ativo, a estrutura do yfinance é diferente
                    prices[orig_t] = float(data["Close"].iloc[-1])
                else:
                    if norm_t in data.columns.levels[0]:
                        prices[orig_t] = float(data[norm_t]["Close"].dropna().iloc[-1])
            except Exception:
                prices[orig_t] = None
    except Exception as e:
        logger.warning(f"Erro ao buscar cotações em tempo real no Yahoo Finance: {e}")
        
    return prices

@st.cache_data(ttl=3600)
def get_usd_brl_rate():
    """
    Obtém a taxa de câmbio atual de USD para BRL usando yfinance.
    """
    try:
        data = yf.download("USDBRL=X", period="1d", progress=False, timeout=10)
        if not data.empty:
            close_col = None
            if "Close" in data.columns:
                close_col = data["Close"]
            else:
                for col in data.columns:
                    if col == "Close" or (isinstance(col, tuple) and col[0] == "Close"):
                        close_col = data[col]
                        break
            
            if close_col is not None:
                val = close_col.iloc[-1]
                if isinstance(val, pd.Series):
                    val = val.iloc[0] if not val.empty else 5.0
                return float(val)
    except Exception as e:
        logger.warning(f"Não foi possível obter a taxa de câmbio USD/BRL: {e}")
    return 5.0  # Fallback razoável

@st.cache_data(ttl=600)
def calculate_portfolio_holdings(df_orders):
    """
    Calcula a carteira atualizada de investimentos com base no histórico de ordens.
    Implementa o cálculo correto de preço médio por FIFO/Média Ponderada.
    """
    if df_orders.empty:
        return pd.DataFrame()
        
    # Ordena ordens cronologicamente, removendo linhas sem data válida
    df = df_orders.dropna(subset=["data envio"]).sort_values("data envio").copy()
    if df.empty:
        return pd.DataFrame()
    
    holdings = {}
    
    for _, row in df.iterrows():
        action = str(row.get("Compra/Venda", "")).strip().upper()
        ticker = str(row.get("Papel", "")).strip().upper()
        if not ticker or ticker == "NAN":
            continue
            
        qty = float(row.get("Qtd Executada", 0))
        total_spent = float(row.get("Total líquido", 0)) # Contém corretagem embutida
        price_avg_unit = float(row.get("Preço médio + corretagem", 0))
        
        if qty <= 0:
            continue
            
        if ticker not in holdings:
            holdings[ticker] = {
                "ticker": ticker,
                "quantidade": 0.0,
                "preco_medio": 0.0,
                "total_investido": 0.0,
                "tipo": row.get("Tipo", "Ações"),
                "moeda": row.get("Moeda", "BRL"),
                "setor_economico": row.get("Setor Econômico", "Outros")
            }
            
        h = holdings[ticker]
        
        is_rf = str(row.get("Tipo", "")).strip().upper() in ["RENDA FIXA", "CAIXA", "CASH", "CONTA"]
        
        if is_rf:
            if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO", "DESDOBRAMENTO", "BONIFICACAO", "BONIFICAÇÃO"]):
                h["total_investido"] += total_spent
                h["quantidade"] = 1.0 if h["total_investido"] > 0 else 0.0
                h["preco_medio"] = h["total_investido"]
            elif "VENDA" in action or action == "V":
                h["total_investido"] = max(0.0, h["total_investido"] - total_spent)
                h["quantidade"] = 1.0 if h["total_investido"] > 0 else 0.0
                h["preco_medio"] = h["total_investido"]
        else:
            if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO", "DESDOBRAMENTO", "BONIFICACAO", "BONIFICAÇÃO"]):
                new_qty = h["quantidade"] + qty
                new_total = h["total_investido"] + total_spent
                h["preco_medio"] = new_total / new_qty if new_qty > 0 else 0.0
                h["quantidade"] = new_qty
                h["total_investido"] = new_total
            elif "VENDA" in action or action == "V":
                new_qty = max(0.0, h["quantidade"] - qty)
                h["quantidade"] = new_qty
                h["total_investido"] = new_qty * h["preco_medio"]
            
    # Filtra apenas ativos que ainda estão na carteira
    active_holdings = [h for h in holdings.values() if h["quantidade"] > 0]
    df_holdings = pd.DataFrame(active_holdings)
    
    if df_holdings.empty:
        return pd.DataFrame()
        
    # Busca taxa de câmbio USD/BRL
    usd_brl_rate = get_usd_brl_rate()
        
    # Busca preços de fechamento atuais
    tickers_list = df_holdings["ticker"].tolist()
    ticker_types = df_holdings.set_index("ticker")["tipo"].to_dict()
    current_prices = get_current_prices(tickers_list, ticker_types)
    
    # Adiciona colunas para controle de moedas e valorizações
    df_holdings["preco_atual_orig"] = df_holdings["ticker"].map(current_prices)
    
    # Para ativos sem cotação, usa preco_medio como fallback (que é em BRL se inserido em BRL, ou USD se USD)
    df_holdings["preco_atual_orig"] = df_holdings["preco_atual_orig"].fillna(df_holdings["preco_medio"])
    
    # Processa cada ativo para unificar em BRL
    total_investido_brl = []
    preco_medio_brl = []
    preco_atual_brl = []
    
    for _, row in df_holdings.iterrows():
        is_usd = (row["moeda"] == "USD")
        p_avg = row["preco_medio"]
        p_curr = row["preco_atual_orig"]
        
        if is_usd:
            # Heurística: se preco_medio for muito superior ao preço atual em USD,
            # significa que o usuário digitou o Total Líquido / Preço em BRL.
            if p_avg > p_curr * 2.5:
                # O usuário já digitou totais em BRL na planilha de ordens
                total_investido_brl.append(row["total_investido"])
                preco_medio_brl.append(p_avg)
            else:
                # O usuário digitou totais em USD na planilha de ordens
                total_investido_brl.append(row["total_investido"] * usd_brl_rate)
                preco_medio_brl.append(p_avg * usd_brl_rate)
                
            preco_atual_brl.append(p_curr * usd_brl_rate)
        else:
            # Ativos nacionais em BRL
            total_investido_brl.append(row["total_investido"])
            preco_medio_brl.append(p_avg)
            preco_atual_brl.append(p_curr)
            
    df_holdings["total_investido_brl"] = total_investido_brl
    df_holdings["preco_medio_brl"] = preco_medio_brl
    df_holdings["preco_atual_brl"] = preco_atual_brl
    
    df_holdings["valor_atual_brl"] = df_holdings["quantidade"] * df_holdings["preco_atual_brl"]
    df_holdings["lucro_prejuizo_brl"] = df_holdings["valor_atual_brl"] - df_holdings["total_investido_brl"]
    df_holdings["retorno_percentual"] = np.where(
        df_holdings["total_investido_brl"] > 0,
        (df_holdings["lucro_prejuizo_brl"] / df_holdings["total_investido_brl"]) * 100.0,
        0.0
    )
    
    # Sobrescreve as colunas padrão com os valores em BRL para garantir 100% de compatibilidade global
    df_holdings["total_investido"] = df_holdings["total_investido_brl"]
    df_holdings["preco_medio"] = df_holdings["preco_medio_brl"]
    df_holdings["preco_atual"] = df_holdings["preco_atual_brl"]
    df_holdings["valor_atual"] = df_holdings["valor_atual_brl"]
    df_holdings["lucro_prejuizo"] = df_holdings["lucro_prejuizo_brl"]
    
    return df_holdings

@st.cache_data(ttl=600)
def get_historical_performance(df_orders):
    """
    Reconstrói a série temporal da carteira dia a dia e calcula os retornos acumulados.
    Compara a carteira com CDI, IPCA, Ibovespa e S&P 500 desde a data do primeiro investimento.
    """
    import time
    t_start = time.time()
    logger.info("🏁 Iniciando get_historical_performance()...")
    
    # Ordena ordens cronologicamente, removendo linhas sem data válida
    df = df_orders.dropna(subset=["data envio"]).sort_values("data envio").copy()
    if df.empty:
        logger.info("get_historical_performance(): df_orders está vazio.")
        return pd.DataFrame()
        
    # Pré-calcula a quantidade consolidada de splits (desdobramentos e bonificações) por ativo
    df_splits_totais = df[df["Compra/Venda"].str.upper().str.contains("DESDOBRAMENTO|BONIFICACAO|BONIFICAÇÃO")]
    splits_por_ativo = df_splits_totais.groupby("Papel")["Qtd Executada"].sum().to_dict()
        
    min_date = df["data envio"].min()
    if pd.isna(min_date) or min_date is pd.NaT:
        logger.info("get_historical_performance(): min_date inválida.")
        return pd.DataFrame()
        
    start_date = min_date.date()
    end_date = datetime.date.today()
    
    # Criar um índice de datas completo do início ao fim
    date_range = pd.date_range(start=start_date, end=end_date)
    logger.info(f"📅 Período analisado: {start_date} até {end_date} ({len(date_range)} dias corridos)")
    
    # Busca cotações históricas de todos os ativos listados
    tickers = df["Papel"].unique()
    ticker_types = df.groupby("Papel")["Tipo"].first().to_dict()
    ticker_currencies = df.groupby("Papel")["Moeda"].first().to_dict()
    
    normalized_tickers = []
    has_usd_assets = False
    
    for t in tickers:
        if not t:
            continue
        asset_type = ticker_types.get(t, None)
        if is_valid_yfinance_ticker(t, asset_type):
            normalized_tickers.append(normalize_ticker(t))
            if ticker_currencies.get(t, "BRL") == "USD":
                has_usd_assets = True
                
    # Se houver ativos em USD, também baixa o histórico do câmbio USD/BRL
    if has_usd_assets:
        normalized_tickers.append("USDBRL=X")
            
    # Sincronização Delta e Ingestão Incremental no SQLite local
    tickers_para_cache = list(normalized_tickers)
    for b_tick in ["^BVSP", "^GSPC"]:
        if b_tick not in tickers_para_cache:
            tickers_para_cache.append(b_tick)
    if "USDBRL=X" not in tickers_para_cache:
        tickers_para_cache.append("USDBRL=X")
        
    db_conn = db_manager.get_db_connection()
    hoje = datetime.date.today()
    
    # Cooldown de 1 hora para sincronização automática de cotações para evitar sobrecarga de rede e CPU
    ignorar_download_por_cooldown = False
    try:
        cursor = db_conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS sync_metadata (chave TEXT PRIMARY KEY, valor TEXT)")
        db_conn.commit()
        
        cursor.execute("SELECT valor FROM sync_metadata WHERE chave = 'last_yfinance_sync'")
        row = cursor.fetchone()
        if row:
            last_yf_sync = datetime.datetime.strptime(row[0], "%d/%m/%Y %H:%M:%S")
            # Cooldown de 1 hora (3600 segundos)
            if (datetime.datetime.now() - last_yf_sync).total_seconds() < 3600:
                ignorar_download_por_cooldown = True
                logger.info("⏳ Cooldown do Yahoo Finance ativo (última sincronização há menos de 1 hora). Ignorando consultas externas e lendo cotações locais.")
    except Exception as e:
        logger.error(f"Erro ao verificar cooldown do Yahoo Finance: {e}")
        
    tickers_download_info = {}
    
    for t_symbol in tickers_para_cache:
        try:
            # Se o cooldown está ativo, não consultamos APIs externas no carregamento automático
            if ignorar_download_por_cooldown:
                continue
                
            # Verifica se o ticker está na lista de falhas definitivas (delisted) para evitar retentativas
            cursor = db_conn.cursor()
            cursor.execute("SELECT 1 FROM failed_tickers WHERE ticker = ?", (t_symbol,))
            if cursor.fetchone():
                continue
                
            # 1. Verifica cotações locais já existentes no SQLite
            df_local = pd.read_sql_query(
                "SELECT data, preco_fechamento FROM precos_historicos WHERE ticker = ? ORDER BY data",
                db_conn,
                params=(t_symbol,)
            )
            
            fazer_download = True
            download_start = start_date
            
            if not df_local.empty:
                df_local["data"] = pd.to_datetime(df_local["data"])
                max_data_local = df_local["data"].max().date()
                min_data_local = df_local["data"].min().date()
                
                # Se temos dados locais desde o start_date até ontem/hoje, pula o download
                ontem = hoje - datetime.timedelta(days=1)
                if min_data_local <= start_date and max_data_local >= ontem:
                    fazer_download = False
                else:
                    # Sincroniza apenas do dia seguinte ao último registro em diante
                    download_start = max_data_local + datetime.timedelta(days=1)
                    if download_start >= hoje:
                        fazer_download = False
                        
            if fazer_download:
                tickers_download_info[t_symbol] = download_start
        except Exception as ex:
            logger.error(f"Erro ao verificar cache local de {t_symbol}: {ex}")
            
    if tickers_download_info:
        # Tenta download em lote para máxima performance
        min_start = min(tickers_download_info.values())
        tickers_list = list(tickers_download_info.keys())
        
        logger.info(f"📥 Baixando cotações em lote para {len(tickers_list)} ativos de {min_start} até {hoje}...")
        
        try:
            df_batch = yf.download(tickers_list, start=min_start.strftime("%Y-%m-%d"), end=hoje.strftime("%Y-%m-%d"), progress=False, group_by="ticker", timeout=25)
            
            for t_symbol in list(tickers_download_info.keys()):
                try:
                    df_t = None
                    if len(tickers_list) == 1:
                        df_t = df_batch
                    elif t_symbol in df_batch.columns.levels[0]:
                        df_t = df_batch[t_symbol]
                        
                    if df_t is not None and not df_t.empty:
                        prices_list = []
                        close_col = None
                        if "Close" in df_t.columns:
                            close_col = df_t["Close"]
                        elif "close" in df_t.columns:
                            close_col = df_t["close"]
                            
                        if close_col is not None:
                            d_start = tickers_download_info[t_symbol]
                            for timestamp, price in close_col.items():
                                if pd.isna(price) or float(price) <= 0:
                                    continue
                                if timestamp.date() < d_start:
                                    continue
                                date_str = timestamp.strftime("%Y-%m-%d")
                                prices_list.append((t_symbol, date_str, float(price)))
                                
                            if prices_list:
                                rows_saved = db_manager.save_historical_prices(prices_list)
                                logger.info(f"✅ Salvas com sucesso {rows_saved} cotações para {t_symbol} no banco SQLite (lote).")
                                tickers_download_info.pop(t_symbol, None) # Removido com sucesso
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao processar ticker {t_symbol} no lote: {e}. Será tentado individualmente.")
        except Exception as e:
            logger.warning(f"⚠️ Falha no download em lote: {e}. Caindo de volta para downloads individuais.")
            
        # Fallback individual para qualquer ticker pendente
        for t_symbol, d_start in tickers_download_info.items():
            try:
                logger.info(f"📥 [Fallback] Baixando cotações delta de {t_symbol} ({d_start} até {hoje})...")
                df_new = yf.download(t_symbol, start=d_start.strftime("%Y-%m-%d"), end=hoje.strftime("%Y-%m-%d"), progress=False, timeout=15)
                
                if df_new.empty:
                    # Se o banco local estava vazio (d_start == start_date), significa que o ativo é delisted/inválido no yfinance
                    # Nós o registramos no failed_tickers para nunca mais tentar baixar o histórico de 10 anos
                    if d_start == start_date:
                        logger.warning(f"⚠️ [Fallback] Resposta do yfinance para {t_symbol} retornou vazia e sem dados locais. Registrando em failed_tickers (delisted).")
                        try:
                            cursor = db_conn.cursor()
                            cursor.execute("INSERT OR IGNORE INTO failed_tickers (ticker) VALUES (?)", (t_symbol,))
                            db_conn.commit()
                        except Exception as e:
                            logger.error(f"Erro ao registrar ticker falho no SQLite: {e}")
                    else:
                        logger.warning(f"⚠️ [Fallback] Resposta do yfinance para {t_symbol} retornou vazia (provável feriado/fim de semana). Ignorando sem corromper dados.")
                    continue
                    
                prices_list = []
                close_col = None
                if isinstance(df_new, pd.Series):
                    close_col = df_new
                elif isinstance(df_new, pd.DataFrame):
                    if isinstance(df_new.columns, pd.MultiIndex):
                        if 'Close' in df_new.columns.levels[0]:
                            close_col = df_new['Close']
                        elif 'close' in df_new.columns.levels[0]:
                            close_col = df_new['close']
                    else:
                        if "Close" in df_new.columns:
                            close_col = df_new["Close"]
                        elif "close" in df_new.columns:
                            close_col = df_new["close"]
                            
                if close_col is not None:
                    if isinstance(close_col, pd.DataFrame):
                        if t_symbol in close_col.columns:
                            close_col = close_col[t_symbol]
                        else:
                            close_col = close_col.iloc[:, 0]
                            
                    for timestamp, price in close_col.items():
                        if pd.isna(price) or float(price) <= 0:
                            continue
                        date_str = timestamp.strftime("%Y-%m-%d")
                        prices_list.append((t_symbol, date_str, float(price)))
                        
                    if prices_list:
                        rows_saved = db_manager.save_historical_prices(prices_list)
                        logger.info(f"✅ Salvas com sucesso {rows_saved} cotações para {t_symbol} no banco SQLite (individual).")
                    else:
                        if d_start == start_date:
                            try:
                                cursor = db_conn.cursor()
                                cursor.execute("INSERT OR IGNORE INTO failed_tickers (ticker) VALUES (?)", (t_symbol,))
                                db_conn.commit()
                            except Exception as e:
                                logger.error(f"Erro ao registrar ticker falho no SQLite: {e}")
            except Exception as ex:
                logger.error(f"Erro no fallback individual de {t_symbol}: {ex}")
        
        # Registra o sucesso do sync do yfinance para iniciar o cooldown de 1 hora
        try:
            cursor = db_conn.cursor()
            now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            cursor.execute("INSERT OR REPLACE INTO sync_metadata (chave, valor) VALUES ('last_yfinance_sync', ?)", (now_str,))
            db_conn.commit()
            logger.info("✅ Timestamp de sincronização de cotações salvo com sucesso. Cooldown de 1 hora ativado.")
        except Exception as e:
            logger.error(f"Erro ao salvar timestamp do sync do yfinance no banco: {e}")
            
    t_after_sync = time.time()
    logger.info(f"⚡ [TIMER] Sincronização Delta / Ingestão yfinance levou {t_after_sync - t_start:.2f} segundos.")
    
    # 2. Reconstrói hist_prices e hist_bench a partir do SQLite local
    hist_prices = pd.DataFrame(index=date_range)
    logger.info("🔍 Reconstruindo série temporal de preços a partir do SQLite local...")
    for nt in normalized_tickers:
        try:
            df_t = pd.read_sql_query(
                "SELECT data, preco_fechamento FROM precos_historicos WHERE ticker = ? ORDER BY data",
                db_conn,
                params=(nt,)
            )
            if not df_t.empty:
                df_t["data"] = pd.to_datetime(df_t["data"])
                df_t = df_t.set_index("data").reindex(date_range).ffill().bfill()
                hist_prices[nt] = df_t["preco_fechamento"]
                logger.info(f"   ➔ Ativo {nt}: {len(df_t)} cotações recuperadas do SQLite local.")
            else:
                logger.warning(f"   ➔ Ativo {nt}: NENHUMA cotação encontrada no SQLite local! Utilizará fallback.")
        except Exception as e:
            logger.error(f"Erro ao recuperar cotações de {nt} do SQLite: {e}")
            
    # Preenche feriados e fins de semana nas cotações históricas
    hist_prices = hist_prices.ffill().bfill()
    if "USDBRL=X" in hist_prices.columns:
        hist_prices["USDBRL=X"] = hist_prices["USDBRL=X"].ffill().bfill().fillna(5.0)
    else:
        try:
            df_usd = pd.read_sql_query("SELECT data, preco_fechamento FROM precos_historicos WHERE ticker = 'USDBRL=X' ORDER BY data", db_conn)
            if not df_usd.empty:
                df_usd["data"] = pd.to_datetime(df_usd["data"])
                df_usd = df_usd.set_index("data").reindex(date_range).ffill().bfill()
                hist_prices["USDBRL=X"] = df_usd["preco_fechamento"]
                logger.info(f"   ➔ Taxa USD/BRL recuperada com sucesso do SQLite.")
            else:
                hist_prices["USDBRL=X"] = 5.0
                logger.warning("   ➔ Taxa USD/BRL ausente no SQLite! Usando fallback fixo de 5.0.")
        except Exception:
            hist_prices["USDBRL=X"] = 5.0
            
    # Reconstrói benchmarks
    hist_bench = pd.DataFrame(index=date_range)
    benchmarks = {"^BVSP": "Ibovespa", "^GSPC": "S&P 500"}
    for b_ticker, b_name in benchmarks.items():
        try:
            df_b = pd.read_sql_query(
                "SELECT data, preco_fechamento FROM precos_historicos WHERE ticker = ? ORDER BY data",
                db_conn,
                params=(b_ticker,)
            )
            if not df_b.empty:
                df_b["data"] = pd.to_datetime(df_b["data"])
                df_b = df_b.set_index("data").reindex(date_range).ffill().bfill()
                hist_bench[b_name] = df_b["preco_fechamento"]
                logger.info(f"   ➔ Benchmark {b_name} ({b_ticker}): {len(df_b)} registros recuperados do SQLite.")
            else:
                logger.warning(f"   ➔ Benchmark {b_name} ({b_ticker}): NENHUM registro no SQLite!")
        except Exception as e:
            logger.error(f"Erro ao recuperar benchmark {b_name} do SQLite: {e}")
            
    db_conn.close()
    
    t_after_rebuild = time.time()
    logger.info(f"⚡ [TIMER] Reconstrução de série de preços/benchmarks do SQLite levou {t_after_rebuild - t_after_sync:.2f} segundos.")
    
    # Normaliza Benchmarks de Mercado para iniciarem em 1.0 (100%) no primeiro dia
    for col in hist_bench.columns:
        first_val = hist_bench[col].dropna().iloc[0] if not hist_bench[col].dropna().empty else 1.0
        hist_bench[col] = hist_bench[col] / first_val
        
    # Obtém dados de CDI e IPCA acumulados
    cdi_factor = get_historical_cdi(start_date, end_date)
    ipca_factor = get_historical_ipca(start_date, end_date)
    
    t_after_macro = time.time()
    logger.info(f"⚡ [TIMER] Obtendo CDI e IPCA do Banco Central/Cache levou {t_after_macro - t_after_rebuild:.2f} segundos.")
    
    # Junta os benchmarks de CDI e IPCA
    bench_df = hist_bench.copy()
    bench_df["CDI"] = cdi_factor
    bench_df["IPCA"] = ipca_factor
    # Normaliza CDI e IPCA para começarem em 1.0 no dia 1
    bench_df["CDI"] = bench_df["CDI"] / bench_df["CDI"].iloc[0]
    bench_df["IPCA"] = bench_df["IPCA"] / bench_df["IPCA"].iloc[0]
    
    # Calcula IPCA + 6% ao ano acumulado dia a dia
    # 6% ao ano composto equivale a um rendimento diário de (1.06) ** (1/365)
    fator_fixo_diario = (1.06) ** (1/365)
    dias_passados = np.arange(len(bench_df))
    bench_df["IPCA + 6%"] = bench_df["IPCA"] * (fator_fixo_diario ** dias_passados)
    
    # Salva IPCA + 6% no SQLite precos_historicos para auditoria e persistência local
    try:
        prices_list = []
        for timestamp, price in bench_df["IPCA + 6%"].items():
            date_str = timestamp.strftime("%Y-%m-%d")
            prices_list.append(("IPCA_6", date_str, float(price)))
        if prices_list:
            db_manager.save_historical_prices(prices_list)
    except Exception as ex:
        logger.error(f"Erro ao salvar IPCA + 6% no SQLite: {ex}")
    
    # Pré-carrega splits oficiais uma única vez antes do loop diário (Grande otimização!)
    splits_oficiais = {}
    splits_env = os.getenv("SPLITS_OFICIAIS", "{}")
    try:
        splits_dict = json.loads(splits_env)
        splits_oficiais = {tuple(k.split("|")): float(v) for k, v in splits_dict.items()}
        logger.info(f"⚙️ Carregados {len(splits_oficiais)} splits oficiais do .env para processamento.")
    except Exception as e:
        logger.error(f"Erro ao carregar SPLITS_OFICIAIS do .env: {e}")
        
    # Agora calculamos o valor da carteira dia a dia de forma incremental ultra-rápida (O(N + M))
    portfolio_values = []
    invested_values = []
    cota_values = []
    cota_atual = 1.0
    valor_ontem = 0.0
    total_invested_net_running = 0.0
    
    # Agrupa ordens por data para acesso instantâneo em O(1)
    df_date_grouped = df.groupby(df["data envio"].dt.date)
    
    logger.info("🔄 Iniciando loop diário de cálculo de rentabilidade incremental...")
    t_start_loop = time.time()
    
    holdings = {}
    has_any_orders = False
    
    for date in date_range:
        current_date_date = date.date()
        
        # Se houver ordens nesta data específica, atualiza o holdings incrementalmente
        if current_date_date in df_date_grouped.groups:
            has_any_orders = True
            ordens_no_dia = df_date_grouped.get_group(current_date_date)
            for _, row in ordens_no_dia.iterrows():
                action = str(row.get("Compra/Venda", "")).strip().upper()
                ticker = str(row.get("Papel", "")).strip().upper()
                qty = float(row.get("Qtd Executada", 0))
                total_spent = float(row.get("Total líquido", 0))
                price_avg_unit = float(row.get("Preço médio + corretagem", 0))
                moeda = str(row.get("Moeda", "BRL")).strip().upper()
                
                if ticker not in holdings:
                    holdings[ticker] = {
                        "qty": 0.0, 
                        "invested": 0.0, 
                        "avg_cost": 0.0, 
                        "moeda": moeda,
                        "tipo": row.get("Tipo", "Ações"),
                        "indexador": row.get("Indexador", ""),
                        "taxa_indexador": row.get("Taxa Indexador", 0.0),
                        "current_balance": 0.0
                    }
                    
                h = holdings[ticker]
                h["tipo"] = row.get("Tipo", "Ações")
                h["indexador"] = row.get("Indexador", h.get("indexador", ""))
                h["taxa_indexador"] = row.get("Taxa Indexador", h.get("taxa_indexador", 0.0))
                
                is_rf = str(row.get("Tipo", "")).strip().upper() in ["RENDA FIXA", "CAIXA", "CASH", "CONTA"]
                
                if is_rf:
                    if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO"]):
                        h["invested"] += total_spent
                        h["qty"] = 1.0 if h["invested"] > 0 else 0.0
                        h["avg_cost"] = h["invested"]
                        h["current_balance"] = h.get("current_balance", 0.0) + total_spent
                    elif "VENDA" in action or action == "V":
                        h["invested"] = max(0.0, h["invested"] - total_spent)
                        h["qty"] = 1.0 if h["invested"] > 0 else 0.0
                        h["avg_cost"] = h["invested"]
                        h["current_balance"] = max(0.0, h.get("current_balance", 0.0) - total_spent)
                else:
                    if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO", "DESDOBRAMENTO", "BONIFICACAO", "BONIFICAÇÃO"]):
                        new_qty = h["qty"] + qty
                        new_invested = h["invested"] + total_spent
                        h["avg_cost"] = new_invested / new_qty if new_qty > 0 else 0.0
                        h["qty"] = new_qty
                        h["invested"] = new_invested
                        h["current_balance"] = h.get("current_balance", 0.0) + total_spent
                    elif "VENDA" in action or action == "V":
                        new_qty = max(0.0, h["qty"] - qty)
                        h["qty"] = new_qty
                        h["current_balance"] = max(0.0, h.get("current_balance", 0.0) - total_spent)
                        h["invested"] = new_qty * h["avg_cost"]
                    
        if not has_any_orders:
            portfolio_values.append(0.0)
            invested_values.append(0.0)
            cota_values.append(1.0)
            continue
            
        # Variação diária do CDI (apenas dias úteis)
        cdi_rate_today = 0.0
        try:
            idx = cdi_factor.index.get_loc(date)
            if idx > 0:
                cdi_rate_today = (cdi_factor.iloc[idx] / cdi_factor.iloc[idx - 1]) - 1.0
        except Exception:
            pass
            
        # Variação diária do CDI com suporte a finais de semana e feriados (EXCLUSIVO para a conta do 99 Pay)
        cdi_rate_calendar_today = 0.0
        try:
            idx = cdi_factor.index.get_loc(date)
            if idx > 0:
                cdi_rate_calendar_today = (cdi_factor.iloc[idx] / cdi_factor.iloc[idx - 1]) - 1.0
                if cdi_rate_calendar_today == 0.0:
                    # Fallback para o último dia útil para simular rendimento corrido real no 99 Pay
                    for i in range(idx - 1, max(0, idx - 5), -1):
                        prev_rate = (cdi_factor.iloc[i] / cdi_factor.iloc[i - 1]) - 1.0
                        if prev_rate > 0.0:
                            cdi_rate_calendar_today = prev_rate
                            break
        except Exception:
            pass
            
        # Variação diária do IPCA
        ipca_rate_today = 0.0
        try:
            idx = ipca_factor.index.get_loc(date)
            if idx > 0:
                ipca_rate_today = (ipca_factor.iloc[idx] / ipca_factor.iloc[idx - 1]) - 1.0
        except Exception:
            pass
            
        # Calcula valor total e valor investido na data
        total_market_value = 0.0
        total_invested_capital = 0.0
        
        # Pega a taxa de câmbio histórica daquela data específica
        usd_rate_today = 5.0
        if "USDBRL=X" in hist_prices.columns:
            val = hist_prices.loc[date, "USDBRL=X"]
            if isinstance(val, pd.Series):
                val = val.iloc[0] if not val.empty else 5.0
            usd_rate_today = float(val)
            if pd.isna(usd_rate_today) or usd_rate_today <= 0:
                usd_rate_today = 5.0
        
        for ticker, h in holdings.items():
            if h["qty"] <= 0:
                continue
                
            tipo = str(h.get("tipo", "Ações")).upper()
            indexer = str(h.get("indexador", "")).upper().strip()
            taxa = float(h.get("taxa_indexador", 0.0))
            is_cash_reserve = ("CAIXA" in tipo or "RENDA FIXA" in tipo) and indexer
            
            if is_cash_reserve:
                # Simula a rentabilidade diária do caixa / renda fixa
                daily_yield_rate = 0.0
                
                if "99 PAY" in ticker.upper():
                    # Lógica 99 Pay (CDI corrido calendário): 110% do CDI até R$ 5.000,00 e 80% do CDI no que exceder
                    balance = h.get("current_balance", h["invested"])
                    if balance <= 5000.0:
                        daily_yield_rate = cdi_rate_calendar_today * 1.10
                    else:
                        weight_5k = 5000.0 / balance
                        weight_excess = (balance - 5000.0) / balance
                        daily_yield_rate = cdi_rate_calendar_today * (1.10 * weight_5k + 0.80 * weight_excess)
                elif "CDI" in indexer:
                    # Contas e CDBs normais: rendem apenas em dias úteis
                    daily_yield_rate = cdi_rate_today * taxa
                elif "IPCA" in indexer:
                    # Variação do IPCA + fração diária da taxa fixa pré
                    daily_pre_rate = (1.0 + taxa) ** (1/365) - 1.0
                    daily_yield_rate = ipca_rate_today + daily_pre_rate + (ipca_rate_today * daily_pre_rate)
                elif "PRÉ" in indexer or "PRE" in indexer:
                    daily_yield_rate = (1.0 + taxa) ** (1/365) - 1.0
                    
                h["current_balance"] = h.get("current_balance", h["invested"]) * (1.0 + daily_yield_rate)
                
                total_market_value += h["current_balance"]
                total_invested_capital += h["invested"]
                continue
                
            # Calcula o multiplicador de split acumulado futuro para esta data
            multiplicador_split = 1.0
            for (s_ticker, s_data_str), s_fator in splits_oficiais.items():
                if s_ticker == ticker:
                    s_date = datetime.datetime.strptime(s_data_str, "%Y-%m-%d").date()
                    # Se a data do loop for anterior à ocorrência do split, aplica o multiplicador retroativo
                    if date.date() < s_date:
                        multiplicador_split *= s_fator
                        
            qty_historica_ajustada = h["qty"] * multiplicador_split
                
            norm_t = normalize_ticker(ticker)
            is_usd = (h["moeda"] == "USD")
            
            # Preço unitário histórico
            price_unit = h["avg_cost"] # fallback: preço médio
            from_yfinance = False
            
            if norm_t in hist_prices.columns:
                p_val = hist_prices.loc[date, norm_t]
                if not pd.isna(p_val) and float(p_val) > 0.0:
                    price_unit = float(p_val)
                    from_yfinance = True
                    
            # Se for USD, precisamos lidar com a conversão para BRL
            if is_usd:
                # Compara o custo unitário na planilha com a cotação do yfinance (que é sempre em USD)
                # para detectar se os valores da planilha já estão em BRL ou se estão em USD.
                is_planilha_em_brl = False
                if from_yfinance and price_unit > 0:
                    if h["avg_cost"] > price_unit * 2.5:
                        is_planilha_em_brl = True
                else:
                    # Se não veio do yfinance (fallback), estimamos pelo valor nominal do avg_cost
                    if h["avg_cost"] >= 1000.0:
                        is_planilha_em_brl = True
                
                if is_planilha_em_brl:
                    # Custo investido já está em BRL na planilha
                    invested_brl = h["invested"]
                    # Cotação histórica em USD do yfinance convertida para BRL
                    price_brl = price_unit * usd_rate_today if from_yfinance else price_unit
                else:
                    # Custo investido está em USD e precisa ser convertido para BRL
                    invested_brl = h["invested"] * usd_rate_today
                    # Cotação histórica em USD convertida para BRL
                    price_brl = price_unit * usd_rate_today
            else:
                price_brl = price_unit
                invested_brl = h["invested"]
                
            total_market_value += qty_historica_ajustada * price_brl
            total_invested_capital += invested_brl
            
        # Detecção e logging de anomalias de rentabilidade histórica
        if total_invested_capital > 0:
            retorno_dia = (total_market_value / total_invested_capital - 1.0) * 100.0
            if retorno_dia > 200.0:  # Rentabilidade diária > 200% é sinal de erro contábil/anomalia
                logger.warning(f"⚠️ ANOMALIA em {date.strftime('%d/%m/%Y')}! Retorno: {retorno_dia:.2f}% | Mercado: R$ {total_market_value:,.2f} | Investido: R$ {total_invested_capital:,.2f}")
                # Lista os ativos do dia que estão compondo essa anomalia
                for t_name, h_info in holdings.items():
                    if h_info["qty"] <= 0:
                        continue
                    # Calcula o multiplicador de split para o log
                    m_split = 1.0
                    for (s_ticker, s_data_str), s_fator in splits_oficiais.items():
                        if s_ticker == t_name:
                            s_date = datetime.datetime.strptime(s_data_str, "%Y-%m-%d").date()
                            if date.date() < s_date:
                                m_split *= s_fator
                    q_ajust = h_info["qty"] * m_split
                    logger.warning(f"   ➔ Ativo: {t_name} | Qtd real: {h_info['qty']} | Qtd ajustada: {q_ajust} | Investido BRL: R$ {h_info['invested']:,.2f}")
                    
        # Calcula rentabilidade pelo método de Cotas (TWR)
        fluxo_hoje = 0.0
        if current_date_date in df_date_grouped.groups:
            ordens_no_dia = df_date_grouped.get_group(current_date_date)
            for _, row in ordens_no_dia.iterrows():
                action = str(row.get("Compra/Venda", "")).strip().upper()
                qty = float(row.get("Qtd Executada", 0))
                total_spent = float(row.get("Total líquido", 0))
                moeda = str(row.get("Moeda", "BRL")).strip().upper()
                
                # Taxa de câmbio para converter fluxos em USD
                usd_rate_today = 5.0
                if "USDBRL=X" in hist_prices.columns:
                    val = hist_prices.loc[date, "USDBRL=X"]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0] if not val.empty else 5.0
                    usd_rate_today = float(val)
                    if pd.isna(usd_rate_today) or usd_rate_today <= 0:
                        usd_rate_today = 5.0
                
                if moeda == "USD":
                    is_planilha_em_brl = False
                    if total_spent >= 1000.0 or (qty > 0 and (total_spent / qty) > 15.0):
                        is_planilha_em_brl = True
                    
                    if is_planilha_em_brl:
                        flow_brl = total_spent
                    else:
                        flow_brl = total_spent * usd_rate_today
                else:
                    flow_brl = total_spent
                    
                if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO"]):
                    fluxo_hoje += flow_brl
                elif "VENDA" in action or action == "V":
                    fluxo_hoje -= flow_brl

        if valor_ontem > 0.01:
            var_diaria = (total_market_value - fluxo_hoje) / valor_ontem - 1.0
            if var_diaria < -0.9:
                var_diaria = 0.0
            cota_atual = cota_atual * (1.0 + var_diaria)
        else:
            if total_market_value > 0.0:
                cota_atual = 1.0
                
            total_invested_net_running += fluxo_hoje

        cota_values.append(cota_atual)
        valor_ontem = total_market_value

        portfolio_values.append(total_market_value)
        invested_values.append(total_invested_net_running)
        
    perf_df = pd.DataFrame(index=date_range)
    perf_df["Valor de Mercado"] = portfolio_values
    perf_df["Capital Investido"] = invested_values
    perf_df["Lucro Bruto"] = perf_df["Valor de Mercado"] - perf_df["Capital Investido"]
    
    # Rentabilidade da carteira baseada no método de cotas acumuladas (TWR)
    perf_df["Retorno Carteira"] = cota_values
    perf_df["Retorno Carteira"] = perf_df["Retorno Carteira"].fillna(1.0)
    
    if not perf_df.empty:
        perf_df.loc[perf_df.index[0], "Retorno Carteira"] = 1.0
        
    t_after_loop = time.time()
    logger.info(f"⚡ [TIMER] Loop diário de cálculo de rentabilidade levou {t_after_loop - t_start_loop:.2f} segundos.")
    
    perf_df = perf_df.join(bench_df)
    
    comparison_cols = ["Retorno Carteira", "CDI", "IPCA", "IPCA + 6%"]
    if "Ibovespa" in bench_df.columns:
        comparison_cols.append("Ibovespa")
    if "S&P 500" in bench_df.columns:
        comparison_cols.append("S&P 500")
        
    for col in comparison_cols:
        perf_df[f"{col} Acumulado (%)"] = (perf_df[col] - 1.0) * 100.0
        
    logger.info(f"🏁 Fim de get_historical_performance(). Tempo Total: {time.time() - t_start:.2f} segundos.")
    return perf_df
