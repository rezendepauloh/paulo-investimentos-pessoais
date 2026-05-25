import datetime
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

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
def get_current_prices(tickers):
    """
    Obtém a cotação atual (tempo real) para uma lista de tickers usando yfinance.
    Retorna um dicionário {ticker_original: preco_atual}.
    """
    prices = {}
    normalized_map = {normalize_ticker(t): t for t in tickers if t}
    
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
            
        qty = int(row.get("Qtd Executada", 0))
        total_spent = float(row.get("Total líquido", 0)) # Contém corretagem embutida
        price_avg_unit = float(row.get("Preço médio + corretagem", 0))
        
        if qty <= 0:
            continue
            
        if ticker not in holdings:
            holdings[ticker] = {
                "ticker": ticker,
                "quantidade": 0,
                "preco_medio": 0.0,
                "total_investido": 0.0,
                "tipo": row.get("Tipo", "Ações"),
                "moeda": row.get("Moeda", "BRL")
            }
            
        h = holdings[ticker]
        
        if "COMPRA" in action or action == "C":
            new_qty = h["quantidade"] + qty
            new_total = h["total_investido"] + total_spent
            h["preco_medio"] = new_total / new_qty if new_qty > 0 else 0.0
            h["quantidade"] = new_qty
            h["total_investido"] = new_total
        elif "VENDA" in action or action == "V":
            # Na venda, o preço médio se mantém igual, apenas reduzimos a quantidade
            new_qty = max(0, h["quantidade"] - qty)
            h["quantidade"] = new_qty
            h["total_investido"] = new_qty * h["preco_medio"]
            
    # Filtra apenas ativos que ainda estão na carteira
    active_holdings = [h for h in holdings.values() if h["quantidade"] > 0]
    df_holdings = pd.DataFrame(active_holdings)
    
    if df_holdings.empty:
        return pd.DataFrame()
        
    # Busca preços de fechamento atuais
    tickers_list = df_holdings["ticker"].tolist()
    current_prices = get_current_prices(tickers_list)
    
    # Adiciona colunas de valorização atual
    df_holdings["preco_atual"] = df_holdings["ticker"].map(current_prices)
    # Se yfinance falhar para algum ativo (ex: Renda Fixa ou ativo sem cotação), usa preco_medio como fallback
    df_holdings["preco_atual"] = df_holdings["preco_atual"].fillna(df_holdings["preco_medio"])
    
    df_holdings["valor_atual"] = df_holdings["quantidade"] * df_holdings["preco_atual"]
    df_holdings["lucro_prejuizo"] = df_holdings["valor_atual"] - df_holdings["total_investido"]
    df_holdings["retorno_percentual"] = (df_holdings["lucro_prejuizo"] / df_holdings["total_investido"]) * 100.0
    
    return df_holdings

def get_historical_performance(df_orders):
    """
    Reconstrói a série temporal da carteira dia a dia e calcula os retornos acumulados.
    Compara a carteira com CDI, IPCA, Ibovespa e S&P 500 desde a data do primeiro investimento.
    """
    # Ordena ordens cronologicamente, removendo linhas sem data válida
    df = df_orders.dropna(subset=["data envio"]).sort_values("data envio").copy()
    if df.empty:
        return pd.DataFrame()
        
    min_date = df["data envio"].min()
    if pd.isna(min_date) or min_date is pd.NaT:
        return pd.DataFrame()
        
    start_date = min_date.date()
    end_date = datetime.date.today()
    
    # Criar um índice de datas completo do início ao fim
    date_range = pd.date_range(start=start_date, end=end_date)
    
    # Busca cotações históricas de todos os ativos listados
    tickers = df["Papel"].unique()
    normalized_tickers = [normalize_ticker(t) for t in tickers if t]
    
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
    
    for date in date_range:
        # Filtra ordens até esta data
        ordens_ate_hoje = df[df["data envio"].dt.date <= date.date()]
        
        if ordens_ate_hoje.empty:
            portfolio_values.append(0.0)
            invested_values.append(0.0)
            continue
            
        # Calcula a posição atualizada até esta data
        holdings = {}
        for _, row in ordens_ate_hoje.iterrows():
            action = str(row.get("Compra/Venda", "")).strip().upper()
            ticker = str(row.get("Papel", "")).strip().upper()
            qty = int(row.get("Qtd Executada", 0))
            total_spent = float(row.get("Total líquido", 0))
            price_avg_unit = float(row.get("Preço médio + corretagem", 0))
            
            if ticker not in holdings:
                holdings[ticker] = {"qty": 0, "invested": 0.0, "avg_cost": 0.0}
                
            h = holdings[ticker]
            if "COMPRA" in action or action == "C":
                new_qty = h["qty"] + qty
                new_invested = h["invested"] + total_spent
                h["avg_cost"] = new_invested / new_qty if new_qty > 0 else 0.0
                h["qty"] = new_qty
                h["invested"] = new_invested
            elif "VENDA" in action or action == "V":
                new_qty = max(0, h["qty"] - qty)
                h["qty"] = new_qty
                h["invested"] = new_qty * h["avg_cost"]
                
        # Calcula valor total e valor investido na data
        total_market_value = 0.0
        total_invested_capital = 0.0
        
        for ticker, h in holdings.items():
            if h["qty"] <= 0:
                continue
                
            norm_t = normalize_ticker(ticker)
            # Busca preço histórico do ativo na data específica
            price = h["avg_cost"] # fallback: preço médio
            if norm_t in hist_prices.columns:
                p_val = hist_prices.loc[date, norm_t]
                if not pd.isna(p_val):
                    price = float(p_val)
                    
            total_market_value += h["qty"] * price
            total_invested_capital += h["invested"]
            
        portfolio_values.append(total_market_value)
        invested_values.append(total_invested_capital)
        
    perf_df = pd.DataFrame(index=date_range)
    perf_df["Valor de Mercado"] = portfolio_values
    perf_df["Capital Investido"] = invested_values
    perf_df["Lucro Bruto"] = perf_df["Valor de Mercado"] - perf_df["Capital Investido"]
    
    # Rentabilidade da carteira baseada no valor acumulado
    # Tratamento para evitar divisão por zero se a carteira começar zerada
    perf_df["Retorno Carteira"] = (perf_df["Valor de Mercado"] / perf_df["Capital Investido"])
    perf_df["Retorno Carteira"] = perf_df["Retorno Carteira"].fillna(1.0)
    # Garante que comece em 1.0
    if not perf_df.empty:
        perf_df.loc[perf_df.index[0], "Retorno Carteira"] = 1.0
        
    # Junta os benchmarks
    perf_df = perf_df.join(bench_df)
    
    # Transforma em formato percentual (-1 e * 100)
    comparison_cols = ["Retorno Carteira", "CDI", "IPCA"]
    if "Ibovespa" in bench_df.columns:
        comparison_cols.append("Ibovespa")
    if "S&P 500" in bench_df.columns:
        comparison_cols.append("S&P 500")
        
    for col in comparison_cols:
        perf_df[f"{col} Acumulado (%)"] = (perf_df[col] - 1.0) * 100.0
        
    return perf_df
