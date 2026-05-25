import datetime
import os
import json
import logging
from logging.handlers import RotatingFileHandler
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

# Cria a pasta de logs se não existir
os.makedirs("logs", exist_ok=True)

# Configuração do Logger Rotativo (máximo 3 arquivos de 3MB)
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = RotatingFileHandler("logs/app.log", maxBytes=3 * 1024 * 1024, backupCount=2, encoding="utf-8")
log_handler.setFormatter(log_formatter)

logger = logging.getLogger("Analytics")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

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
            
            return df["fator_acumulado"]
    except Exception as e:
        st.warning(f"Não foi possível obter os dados do CDI da API do Banco Central: {e}")
        
    # Fallback aproximado (11% ao ano constante de CDI caso a API falhe)
    dates = pd.date_range(start=start_date, end=end_date)
    daily_rate = (1.11) ** (1/252) - 1.0
    fator = (1.0 + daily_rate) ** np.arange(1, len(dates) + 1)
    return pd.Series(fator, index=dates)

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
            
            return df["fator_acumulado"]
    except Exception as e:
        st.warning(f"Não foi possível obter os dados do IPCA da API do Banco Central: {e}")
        
    # Fallback aproximado (4.5% ao ano constante de IPCA caso a API falhe)
    dates = pd.date_range(start=start_date, end=end_date)
    daily_rate = (1.045) ** (1/365) - 1.0
    fator = (1.0 + daily_rate) ** np.arange(1, len(dates) + 1)
    return pd.Series(fator, index=dates)

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
        st.warning(f"Erro ao buscar cotações em tempo real no Yahoo Finance: {e}")
        
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
        st.warning(f"Não foi possível obter a taxa de câmbio USD/BRL: {e}")
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
                "moeda": row.get("Moeda", "BRL")
            }
            
        h = holdings[ticker]
        
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
    # Ordena ordens cronologicamente, removendo linhas sem data válida
    df = df_orders.dropna(subset=["data envio"]).sort_values("data envio").copy()
    if df.empty:
        return pd.DataFrame()
        
    # Pré-calcula a quantidade consolidada de splits (desdobramentos e bonificações) por ativo
    df_splits_totais = df[df["Compra/Venda"].str.upper().str.contains("DESDOBRAMENTO|BONIFICACAO|BONIFICAÇÃO")]
    splits_por_ativo = df_splits_totais.groupby("Papel")["Qtd Executada"].sum().to_dict()
        
    min_date = df["data envio"].min()
    if pd.isna(min_date) or min_date is pd.NaT:
        return pd.DataFrame()
        
    start_date = min_date.date()
    end_date = datetime.date.today()
    
    # Criar um índice de datas completo do início ao fim
    date_range = pd.date_range(start=start_date, end=end_date)
    
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
            
    # Baixa histórico dos ativos em lote
    hist_prices = pd.DataFrame(index=date_range)
    if normalized_tickers:
        try:
            # Baixa preços de fechamento diários dos últimos anos
            data = yf.download(" ".join(normalized_tickers), start=start_date.strftime("%Y-%m-%d"), progress=False, timeout=15)
            if len(normalized_tickers) == 1:
                hist_prices[normalized_tickers[0]] = data["Close"]
            else:
                for nt in normalized_tickers:
                    if nt in data.columns.levels[1]:
                        hist_prices[nt] = data["Close"][nt]
        except Exception as e:
            st.warning(f"Erro ao baixar dados históricos de cotações: {e}")
            
    # Preenche feriados e fins de semana nas cotações históricas
    hist_prices = hist_prices.ffill().bfill()
    
    # Se a coluna do dólar existir, garante que não tenha NaNs
    if "USDBRL=X" in hist_prices.columns:
        hist_prices["USDBRL=X"] = hist_prices["USDBRL=X"].ffill().bfill().fillna(5.0)
    
    # Calcula cotações históricas dos índices benchmark
    benchmarks = {"^BVSP": "Ibovespa", "^GSPC": "S&P 500"}
    hist_bench = pd.DataFrame(index=date_range)
    for b_ticker, b_name in benchmarks.items():
        try:
            b_data = yf.download(b_ticker, start=start_date.strftime("%Y-%m-%d"), progress=False, timeout=10)
            hist_bench[b_name] = b_data["Close"]
        except Exception:
            pass
    hist_bench = hist_bench.ffill().bfill()
    
    # Normaliza Benchmarks de Mercado para iniciarem em 1.0 (100%) no primeiro dia
    for col in hist_bench.columns:
        first_val = hist_bench[col].dropna().iloc[0] if not hist_bench[col].dropna().empty else 1.0
        hist_bench[col] = hist_bench[col] / first_val
        
    # Obtém dados de CDI e IPCA acumulados
    cdi_factor = get_historical_cdi(start_date, end_date)
    ipca_factor = get_historical_ipca(start_date, end_date)
    
    # Junta os benchmarks de CDI e IPCA
    bench_df = hist_bench.copy()
    bench_df["CDI"] = cdi_factor
    bench_df["IPCA"] = ipca_factor
    # Normaliza CDI e IPCA para começarem em 1.0 no dia 1
    bench_df["CDI"] = bench_df["CDI"] / bench_df["CDI"].iloc[0]
    bench_df["IPCA"] = bench_df["IPCA"] / bench_df["IPCA"].iloc[0]
    
    # Agora calculamos o valor da carteira dia a dia
    portfolio_values = []
    invested_values = []
    cota_values = []
    cota_atual = 1.0
    valor_ontem = 0.0
    
    for date in date_range:
        # Filtra ordens até esta data
        ordens_ate_hoje = df[df["data envio"].dt.date <= date.date()]
        
        if ordens_ate_hoje.empty:
            portfolio_values.append(0.0)
            invested_values.append(0.0)
            cota_values.append(1.0)
            continue
            
        # Calcula a posição atualizada até esta data
        holdings = {}
        for _, row in ordens_ate_hoje.iterrows():
            action = str(row.get("Compra/Venda", "")).strip().upper()
            ticker = str(row.get("Papel", "")).strip().upper()
            qty = float(row.get("Qtd Executada", 0))
            total_spent = float(row.get("Total líquido", 0))
            price_avg_unit = float(row.get("Preço médio + corretagem", 0))
            moeda = str(row.get("Moeda", "BRL")).strip().upper()
            
            if ticker not in holdings:
                holdings[ticker] = {"qty": 0.0, "invested": 0.0, "avg_cost": 0.0, "moeda": moeda}
                
            h = holdings[ticker]
            if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO", "DESDOBRAMENTO", "BONIFICACAO", "BONIFICAÇÃO"]):
                new_qty = h["qty"] + qty
                new_invested = h["invested"] + total_spent
                h["avg_cost"] = new_invested / new_qty if new_qty > 0 else 0.0
                h["qty"] = new_qty
                h["invested"] = new_invested
            elif "VENDA" in action or action == "V":
                new_qty = max(0.0, h["qty"] - qty)
                h["qty"] = new_qty
                h["invested"] = new_qty * h["avg_cost"]
                
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
        
        splits_oficiais = {}
        splits_env = os.getenv("SPLITS_OFICIAIS", "{}")
        try:
            splits_dict = json.loads(splits_env)
            # Converte a chave "TICKER|DATA" para a tupla (TICKER, DATA)
            splits_oficiais = {tuple(k.split("|")): float(v) for k, v in splits_dict.items()}
        except Exception as e:
            logger.error(f"Erro ao carregar SPLITS_OFICIAIS do .env: {e}")
        
        for ticker, h in holdings.items():
            if h["qty"] <= 0:
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
        ordens_no_dia = df[df["data envio"].dt.date == date.date()]
        if not ordens_no_dia.empty:
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
                
        cota_values.append(cota_atual)
        valor_ontem = total_market_value

        portfolio_values.append(total_market_value)
        invested_values.append(total_invested_capital)
        
    perf_df = pd.DataFrame(index=date_range)
    perf_df["Valor de Mercado"] = portfolio_values
    perf_df["Capital Investido"] = invested_values
    perf_df["Lucro Bruto"] = perf_df["Valor de Mercado"] - perf_df["Capital Investido"]
    
    # Rentabilidade da carteira baseada no método de cotas acumuladas (TWR)
    perf_df["Retorno Carteira"] = cota_values
    perf_df["Retorno Carteira"] = perf_df["Retorno Carteira"].fillna(1.0)
    
    if not perf_df.empty:
        perf_df.loc[perf_df.index[0], "Retorno Carteira"] = 1.0
        
    perf_df = perf_df.join(bench_df)
    
    comparison_cols = ["Retorno Carteira", "CDI", "IPCA"]
    if "Ibovespa" in bench_df.columns:
        comparison_cols.append("Ibovespa")
    if "S&P 500" in bench_df.columns:
        comparison_cols.append("S&P 500")
        
    for col in comparison_cols:
        perf_df[f"{col} Acumulado (%)"] = (perf_df[col] - 1.0) * 100.0
        
    return perf_df
