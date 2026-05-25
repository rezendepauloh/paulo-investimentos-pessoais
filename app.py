import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()

# Importações internas
from data_loader import get_budget_data, get_orders_data
from analytics import calculate_portfolio_holdings, get_historical_performance
from ai_allocator import generate_allocation_tips

def format_number(val, is_currency=False, currency="BRL", decimals=2):
    if pd.isna(val) or val is None:
        return ""
    try:
        val_float = float(val)
        # Formata o número com o número especificado de casas decimais
        fmt_str = f"{{:,.{decimals}f}}"
        formatted = fmt_str.format(val_float)
        
        # Inverte os separadores: ',' vira temporariamente 'X', '.' vira ',', e 'X' vira '.'
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        
        if is_currency:
            if currency == "USD":
                return f"US$ {formatted}"
            return f"R$ {formatted}"
            
        return formatted
    except Exception:
        return str(val)


# Configuração da página Streamlit
st.set_page_config(
    page_title="Paulo - Finanças & Investimentos",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS moderno e premium para embelezação do Streamlit
st.markdown("""
<style>
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Customização dos Cards de Métricas */
    .metric-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.1);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        margin-bottom: 20px;
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(128, 128, 128, 0.4);
    }
    
    .metric-label {
        font-size: 14px;
        color: #88888b;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 8px;
    }
    
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: var(--text-color);
    }
    
    .metric-delta-positive {
        color: #00E676;
        font-size: 14px;
        font-weight: 600;
        margin-top: 4px;
    }
    
    .metric-delta-negative {
        color: #FF5252;
        font-size: 14px;
        font-weight: 600;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)

# Título principal e barra lateral
st.title("📈 Gestão Patrimonial Inteligente")
st.caption("Consolidação automática de investimentos, fluxo de caixa e consultoria personalizada por Inteligência Artificial.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configurações de Conexão")
    
    # Seletor de Modo de Dados
    data_mode = st.radio(
        "Fonte de Dados:",
        ["Modo Demonstração (Dados Simulados)", "Dados Reais (Google Sheets)"],
        index=1,
        help="Alterne entre dados de teste e a integração em tempo real com suas planilhas do Google Sheets."
    )
    
    use_mock = (data_mode == "Modo Demonstração (Dados Simulados)")
    # Campo manual de Chave de API do Gemini para facilidade do usuário
    st.markdown("---")
    st.header("🤖 Inteligência Artificial")
    user_gemini_key = st.text_input(
        "Chave Gemini API (opcional):",
        type="password",
        help="Caso não configure no arquivo .env, cole sua chave do Google AI Studio aqui."
    )
    if user_gemini_key:
        os.environ["GEMINI_API_KEY"] = user_gemini_key
        
    # Instruções de Setup para a Conta de Serviço (apenas se selecionar Dados Reais)
    if not use_mock:
        st.markdown("---")
        st.subheader("🔑 Configuração da Conta de Serviço")
        
        # Verifica se o arquivo de credenciais existe
        creds_exists = os.path.exists("credentials.json")
        if creds_exists:
            st.success("✅ `credentials.json` carregado com sucesso!")
        else:
            st.warning("⚠️ `credentials.json` não encontrado na raiz!")
            
            with st.expander("Como criar e usar seu arquivo JSON?", expanded=True):
                st.markdown("""
                Siga estes passos rápidos:
                
                1. Vá até o [Google Cloud Console](https://console.cloud.google.com/).
                2. Crie um novo projeto (ex: `MeuInvestimentoApp`).
                3. Pesquise por **Google Sheets API** e ative-a.
                4. Pesquise por **Google Drive API** e ative-a.
                5. Vá para **APIs e Serviços** > **Credenciais**.
                6. Clique em **+ Criar Credenciais** > **Conta de Serviço**.
                7. Insira um nome e clique em **Criar e Continuar**.
                8. Acesse a conta de serviço recém-criada, clique na aba **Chaves** (Keys).
                9. Clique em **Adicionar Chave** > **Criar Nova Chave** > selecione **JSON** e salve-a na raiz deste projeto com o nome de `credentials.json`.
                10. **IMPORTANTE:** Abra o arquivo JSON baixado, copie o e-mail da conta de serviço (`client_email`) e compartilhe as suas duas planilhas com esse e-mail dando permissão de **Leitor**!
                """)

# --- CARGA DOS DADOS ---
if use_mock:
    df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=True)
    df_orders = get_orders_data(use_mock=True)
else:
    # Caso real
    try:
        df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=False)
        df_orders = get_orders_data(use_mock=False)
        
        if df_receitas.empty and df_despesas.empty and df_orders.empty:
            st.info("ℹ️ Nenhuma planilha foi carregada. Certifique-se de configurar o arquivo `.env` e compartilhar as planilhas com a Conta de Serviço. Carregando modo de demonstração como fallback...")
            df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=True)
            df_orders = get_orders_data(use_mock=True)
            use_mock = True
    except Exception as e:
        st.error(f"Erro ao conectar com as planilhas reais: {e}")
        st.info("Carregando modo de demonstração como fallback para testes...")
        df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=True)
        df_orders = get_orders_data(use_mock=True)
        use_mock = True

# --- CÁLCULO DE CARTEIRA E PERFORMANCE ---
df_holdings = pd.DataFrame()
df_perf = pd.DataFrame()

if not df_orders.empty:
    with st.spinner("Calculando posições em tempo real..."):
        df_holdings = calculate_portfolio_holdings(df_orders)
        df_perf = get_historical_performance(df_orders)

# --- LAYOUT E NAVEGAÇÃO POR ABAS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Visão Geral e Orçamento",
    "📈 Desempenho e Benchmarks",
    "📑 Extratos e Lançamentos",
    "🤖 Consultoria de Alocação com IA"
])

# ================= TAB 1: VISÃO GERAL =================
with tab1:
    if df_holdings.empty:
        st.warning("Nenhuma ordem ativa na carteira de investimentos.")
    else:
        # Métricas Globais
        total_market_val = df_holdings["valor_atual"].sum()
        total_invested = df_holdings["total_investido"].sum()
        total_profit = total_market_val - total_invested
        total_return_pct = (total_profit / total_invested) * 100.0 if total_invested > 0 else 0.0
        
        # Fluxo de caixa recente
        total_receitas = df_receitas["Valor"].sum() if not df_receitas.empty else 0.0
        total_despesas = df_despesas["Valor"].sum() if not df_despesas.empty else 0.0
        total_proventos = df_dividendos["Valor"].sum() if not df_dividendos.empty else 0.0
        saving_rate = total_receitas - total_despesas
        saving_pct = (saving_rate / total_receitas * 100.0) if total_receitas > 0 else 0.0
        
        # Formata os valores para exibição no estilo PT-BR
        total_market_val_formatted = format_number(total_market_val, is_currency=True, currency="BRL")
        total_invested_formatted = format_number(total_invested, is_currency=True, currency="BRL")
        total_profit_formatted = format_number(abs(total_profit), is_currency=True, currency="BRL")
        total_return_pct_formatted = format_number(total_return_pct, decimals=2)
        saving_rate_formatted = format_number(saving_rate, is_currency=True, currency="BRL")
        saving_pct_formatted = format_number(saving_pct, decimals=1)
        
        # Seção de Métricas Premium (Cards HTML Customizados)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Patrimônio Atual</div>
                <div class="metric-value">{total_market_val_formatted}</div>
                <div class="metric-delta-positive">Posição em Tempo Real</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Capital Investido</div>
                <div class="metric-value">{total_invested_formatted}</div>
                <div class="metric-delta-positive">Aportes Acumulados</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            profit_class = "metric-delta-positive" if total_profit >= 0 else "metric-delta-negative"
            prefix = "+" if total_profit >= 0 else "-"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Lucro/Prejuízo Total</div>
                <div class="metric-value">{prefix}{total_profit_formatted}</div>
                <div class="{profit_class}">{prefix}{total_return_pct_formatted}% de Retorno</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Taxa de Poupança (Mês)</div>
                <div class="metric-value">{saving_rate_formatted}</div>
                <div class="metric-delta-positive">{saving_pct_formatted}% da receita poupado</div>
            </div>
            """, unsafe_allow_html=True)

        # Gráficos da Distribuição da Carteira
        st.markdown("### 📊 Alocação de Recursos")
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("Distribuição por Classe de Ativos")
            fig_pie_type = px.pie(
                df_holdings,
                names="tipo",
                values="valor_atual",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.G10
            )
            fig_pie_type.update_traces(
                textposition='inside', 
                textinfo='percent+label',
                hovertemplate="<b>Classe:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Proporção:</b> %{percent}<extra></extra>"
            )
            fig_pie_type.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ffffff",
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                separators=",."
            )
            st.plotly_chart(fig_pie_type, width='stretch')
            
        with col_g2:
            st.subheader("Distribuição por Ativo Específico")
            fig_pie_asset = px.pie(
                df_holdings,
                names="ticker",
                values="valor_atual",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie_asset.update_traces(
                textposition='inside', 
                textinfo='percent+label',
                hovertemplate="<b>Ativo:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Proporção:</b> %{percent}<extra></extra>"
            )
            fig_pie_asset.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ffffff",
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                separators=",."
            )
            st.plotly_chart(fig_pie_asset, width='stretch')

        # Gráfico Orçamentário e Proventos
        st.markdown("### 💵 Fluxo de Caixa e Proventos Passivos")
        col_budget_g1, col_budget_g2 = st.columns([2, 1])
        
        with col_budget_g1:
            st.subheader("Comparativo Mensal de Caixa")
            cash_flow_data = pd.DataFrame({
                "Fluxo": ["Receitas", "Despesas", "Dividendos Recebidos"],
                "Valor (R$)": [total_receitas, total_despesas, total_proventos],
                "Cor": ["Receitas", "Despesas", "Proventos"]
            })
            fig_flow = px.bar(
                cash_flow_data,
                x="Fluxo",
                y="Valor (R$)",
                color="Cor",
                color_discrete_map={"Receitas": "#00E676", "Despesas": "#FF5252", "Proventos": "#2979FF"}
            )
            fig_flow.update_traces(
                texttemplate="R$ %{y:,.2f}",
                textposition="outside",
                hovertemplate="<b>Fluxo:</b> %{x}<br><b>Total:</b> R$ %{y:,.2f}<extra></extra>"
            )
            fig_flow.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ffffff",
                showlegend=False,
                xaxis_title=None,
                separators=",."
            )
            st.plotly_chart(fig_flow, width='stretch')
            
        with col_budget_g2:
            st.subheader("Maiores Proventos por Ativo")
            if not df_dividendos.empty:
                divs_by_asset = df_dividendos.groupby("Ativo")["Valor"].sum().reset_index()
                fig_divs = px.bar(
                    divs_by_asset.sort_values("Valor", ascending=True),
                    y="Ativo",
                    x="Valor",
                    orientation="h",
                    color="Ativo",
                    color_discrete_sequence=px.colors.qualitative.Safe
                )
                fig_divs.update_traces(
                    texttemplate="R$ %{x:,.2f}",
                    textposition="outside",
                    hovertemplate="<b>Ativo:</b> %{y}<br><b>Total Recebido:</b> R$ %{x:,.2f}<extra></extra>"
                )
                fig_divs.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#ffffff",
                    showlegend=False,
                    xaxis_title="Proventos Acumulados (R$)",
                    yaxis_title=None,
                    separators=",."
                )
                st.plotly_chart(fig_divs, width='stretch')
            else:
                st.info("Nenhum dividendo lançado recentemente.")

        # Gráficos de Categorias de Receitas e Despesas
        st.markdown("### 🏷️ Categorias de Orçamento (Receitas e Despesas)")
        col_cat1, col_cat2 = st.columns(2)
        
        with col_cat1:
            st.subheader("Receitas por Categoria")
            if not df_receitas.empty:
                df_rec_cat = df_receitas.groupby("Categoria")["Valor"].sum().reset_index()
                fig_rec_cat = px.pie(
                    df_rec_cat,
                    names="Categoria",
                    values="Valor",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Prism
                )
                fig_rec_cat.update_traces(
                    textposition='inside', 
                    textinfo='percent+label',
                    hovertemplate="<b>Categoria:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Proporção:</b> %{percent}<extra></extra>"
                )
                fig_rec_cat.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#ffffff",
                    showlegend=False,
                    margin=dict(t=10, b=10, l=10, r=10),
                    separators=",."
                )
                st.plotly_chart(fig_rec_cat, width='stretch')
            else:
                st.info("Nenhuma receita lançada para categorização.")
                
        with col_cat2:
            st.subheader("Despesas por Categoria")
            if not df_despesas.empty:
                df_desp_cat = df_despesas.groupby("Categoria")["Valor"].sum().reset_index()
                fig_desp_cat = px.pie(
                    df_desp_cat,
                    names="Categoria",
                    values="Valor",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig_desp_cat.update_traces(
                    textposition='inside', 
                    textinfo='percent+label',
                    hovertemplate="<b>Categoria:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Proporção:</b> %{percent}<extra></extra>"
                )
                fig_desp_cat.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#ffffff",
                    showlegend=False,
                    margin=dict(t=10, b=10, l=10, r=10),
                    separators=",."
                )
                st.plotly_chart(fig_desp_cat, width='stretch')
            else:
                st.info("Nenhuma despesa lançada para categorização.")

# ================= TAB 2: HISTÓRICO E BENCHMARKS =================
with tab2:
    st.subheader("📈 Evolução da Rentabilidade Acumulada vs Benchmarks")
    st.markdown("Esta visualização reconstrói a valorização percentual da sua carteira dia a dia e a compara com o CDI, IPCA (Inflação), Ibovespa e S&P 500.")
    
    if df_perf.empty:
        st.info("Sem ordens no histórico para calcular performance.")
    else:
        # Seletor de período do gráfico
        col_sel1, col_sel2 = st.columns([1, 4])
        with col_sel1:
            days_option = st.selectbox(
                "Período de Análise:",
                options=["Desde o início", "Últimos 12 meses", "Últimos 6 meses", "Último mês"],
                index=0
            )
            
        # Filtra o DataFrame histórico de acordo com a opção selecionada
        df_chart = df_perf.copy()
        if not df_chart.empty:
            max_date = df_chart.index.max()
            if days_option == "Últimos 12 meses":
                df_chart = df_chart[df_chart.index >= max_date - pd.Timedelta(days=365)]
            elif days_option == "Últimos 6 meses":
                df_chart = df_chart[df_chart.index >= max_date - pd.Timedelta(days=180)]
            elif days_option == "Último mês":
                df_chart = df_chart[df_chart.index >= max_date - pd.Timedelta(days=30)]
            
        # Garante que os retornos comecem em 0% no período selecionado para fins de comparação justa de ganho relativo
        comparison_columns = [c for c in df_chart.columns if "Acumulado (%)" in c]
        for col in comparison_columns:
            base_val = df_chart[col].iloc[0]
            # Ajusta ganho relativo a partir da base do período
            df_chart[f"{col} Ajustado"] = df_chart[col] - base_val
            
        # Desenha gráfico de linhas com Plotly
        fig_perf = go.Figure()
        
        # Mapeamento elegante de cores para os ativos e índices
        colors_map = {
            "Retorno Carteira Acumulado (%) Ajustado": {"label": "Sua Carteira", "color": "#00E676", "width": 4},
            "CDI Acumulado (%) Ajustado": {"label": "CDI", "color": "#FFC107", "width": 2},
            "IPCA Acumulado (%) Ajustado": {"label": "IPCA (Inflação)", "color": "#FF5252", "width": 2},
            "Ibovespa Acumulado (%) Ajustado": {"label": "Ibovespa", "color": "#00E5FF", "width": 2},
            "S&P 500 Acumulado (%) Ajustado": {"label": "S&P 500", "color": "#E040FB", "width": 2}
        }
        
        for col, settings in colors_map.items():
            if col in df_chart.columns:
                fig_perf.add_trace(go.Scatter(
                    x=df_chart.index,
                    y=df_chart[col],
                    mode='lines',
                    name=settings["label"],
                    line=dict(color=settings["color"], width=settings["width"]),
                    hovertemplate="%{y:.2f}%"
                ))
                
        fig_perf.update_layout(
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#ffffff",
            xaxis_title="Data",
            yaxis_title="Ganho/Perda (%)",
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", ticksuffix="%"),
            separators=",."
        )
        
        st.plotly_chart(fig_perf, width='stretch')
        
        # Tabela resumo comparativa com os números mais recentes
        st.markdown("### 📋 Resumo Acumulado no Período Selecionado")
        resumo_dados = []
        for col, settings in colors_map.items():
            if col in df_chart.columns:
                ultimo_retorno = df_chart[col].iloc[-1]
                resumo_dados.append({
                    "Benchmark / Portfólio": settings["label"],
                    "Rentabilidade no Período (%)": f"{ultimo_retorno:+.2f}%"
                })
        st.table(pd.DataFrame(resumo_dados))

# ================= TAB 3: EXTRATOS E LANÇAMENTOS =================
with tab3:
    st.subheader("📑 Visualização dos Lançamentos e Histórico de Transações")
    
    st.markdown("### 🪙 Histórico de Ordens de Compra e Venda")
    if df_orders.empty:
        st.info("Nenhuma ordem cadastrada.")
    else:
        # Filtro interativo de ativos
        ativos_unicos = ["Todos"] + sorted(df_orders["Papel"].dropna().unique().tolist())
        ativo_selecionado = st.selectbox("Filtrar por Ativo:", ativos_unicos)
        
        df_orders_filtered = df_orders.copy()
        if ativo_selecionado != "Todos":
            df_orders_filtered = df_orders_filtered[df_orders_filtered["Papel"] == ativo_selecionado]
            
        df_orders_display = df_orders_filtered.sort_values("data envio", ascending=False).copy()
        # Formata colunas de valores e quantidades no padrão PT-BR
        df_orders_display["Total líquido"] = df_orders_display.apply(lambda r: format_number(r["Total líquido"], is_currency=True, currency=r["Moeda"]), axis=1)
        df_orders_display["Preço médio + corretagem"] = df_orders_display.apply(lambda r: format_number(r["Preço médio + corretagem"], is_currency=True, currency=r["Moeda"]), axis=1)
        df_orders_display["Preço médio"] = df_orders_display.apply(lambda r: format_number(r["Preço médio"], is_currency=True, currency=r["Moeda"]), axis=1)
        df_orders_display["Total"] = df_orders_display.apply(lambda r: format_number(r["Total"], is_currency=True, currency=r["Moeda"]), axis=1)
        df_orders_display["Corretagem"] = df_orders_display.apply(lambda r: format_number(r["Corretagem"], is_currency=True, currency=r["Moeda"]), axis=1)
        df_orders_display["Qtd Executada"] = df_orders_display["Qtd Executada"].apply(lambda v: format_number(v, decimals=4 if v % 1 != 0 else 0))
        
        st.dataframe(
            df_orders_display,
            column_config={
                "data envio": st.column_config.DatetimeColumn("Data Envio", format="DD/MM/YYYY HH:mm"),
            },
            width='stretch'
        )
        
        # Soma totalizadora dinâmica
        moedas_filtradas = df_orders_filtered["Moeda"].unique()
        if len(moedas_filtradas) == 1:
            moeda_display = moedas_filtradas[0]
            total_soma_ordens = df_orders_filtered["Total líquido"].sum()
        else:
            # Caso misto (exibe o consolidado total líquido em BRL)
            total_soma_ordens = df_orders_filtered["Total líquido"].sum()
            moeda_display = "BRL"
            
        total_soma_formatted = format_number(total_soma_ordens, is_currency=True, currency=moeda_display)
        st.markdown(f"""
        <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total Líquido (Filtro Ativo)</span>
            <span style="font-weight: 700; color: #2979FF; font-size: 20px;">{total_soma_formatted}</span>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    st.markdown("### 💰 Receitas, Despesas e Dividendos")
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["Receitas", "Despesas", "Dividendos"])
    
    with sub_tab1:
        if df_receitas.empty:
            st.info("Nenhuma receita cadastrada.")
        else:
            # Filtro por Categoria de Receitas
            categorias_receitas = ["Todas"] + sorted(df_receitas["Categoria"].dropna().unique().tolist())
            cat_receita_sel = st.selectbox("Filtrar por Categoria (Receitas):", categorias_receitas, key="filter_rec_cat")
            
            df_receitas_filtered = df_receitas.copy()
            if cat_receita_sel != "Todas":
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Categoria"] == cat_receita_sel]
                
            df_receitas_display = df_receitas_filtered.copy()
            
            # Calcula "Dias até" dinamicamente
            def calc_receitas_dias(date_val):
                if pd.isna(date_val):
                    return ""
                today = pd.Timestamp.now().normalize()
                date_val = pd.to_datetime(date_val).normalize()
                if date_val < today:
                    return "Já creditado"
                elif date_val == today:
                    return "Credita hoje!"
                else:
                    diff = (date_val - today).days
                    return f"Faltam {diff} dias"
                    
            df_receitas_display["Dias até"] = df_receitas_display["Recebido em"].apply(calc_receitas_dias)
            df_receitas_display["Valor"] = df_receitas_display["Valor"].apply(lambda v: format_number(v, is_currency=True, currency="BRL"))
            st.dataframe(
                df_receitas_display,
                column_config={
                    "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                },
                width='stretch'
            )
            
            # Soma totalizadora dinâmica
            total_rec_soma = df_receitas_filtered["Valor"].sum()
            total_rec_formatted = format_number(total_rec_soma, is_currency=True, currency="BRL")
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Receitas (Filtro)</span>
                <span style="font-weight: 700; color: #00E676; font-size: 20px;">{total_rec_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    with sub_tab2:
        if df_despesas.empty:
            st.info("Nenhuma despesa cadastrada.")
        else:
            # Filtro por Categoria de Despesas
            categorias_despesas = ["Todas"] + sorted(df_despesas["Categoria"].dropna().unique().tolist())
            cat_despesa_sel = st.selectbox("Filtrar por Categoria (Despesas):", categorias_despesas, key="filter_des_cat")
            
            df_despesas_filtered = df_despesas.copy()
            if cat_despesa_sel != "Todas":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Categoria"] == cat_despesa_sel]
                
            df_despesas_display = df_despesas_filtered.copy()
            
            # Calcula "Dias até" dinamicamente
            def calc_despesas_dias(date_val):
                if pd.isna(date_val):
                    return ""
                today = pd.Timestamp.now().normalize()
                date_val = pd.to_datetime(date_val).normalize()
                if date_val < today:
                    return "Já debitado"
                elif date_val == today:
                    return "Debita hoje!"
                else:
                    diff = (date_val - today).days
                    return f"Faltam {diff} dias"
                    
            df_despesas_display["Dias até"] = df_despesas_display["Gasto em"].apply(calc_despesas_dias)
            df_despesas_display["Valor"] = df_despesas_display["Valor"].apply(lambda v: format_number(v, is_currency=True, currency="BRL"))
            st.dataframe(
                df_despesas_display,
                column_config={
                    "Gasto em": st.column_config.DateColumn("Gasto Em", format="DD/MM/YYYY"),
                },
                width='stretch'
            )
            
            # Soma totalizadora dinâmica
            total_des_soma = df_despesas_filtered["Valor"].sum()
            total_des_formatted = format_number(total_des_soma, is_currency=True, currency="BRL")
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Despesas (Filtro)</span>
                <span style="font-weight: 700; color: #FF5252; font-size: 20px;">{total_des_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    with sub_tab3:
        if df_dividendos.empty:
            st.info("Nenhum dividendo passivo lançado.")
        else:
            # Filtro por Ativo de Dividendos
            ativos_dividendos = ["Todos"] + sorted(df_dividendos["Ativo"].dropna().unique().tolist())
            ativo_div_sel = st.selectbox("Filtrar por Ativo (Dividendos):", ativos_dividendos, key="filter_div_ativo")
            
            df_dividendos_filtered = df_dividendos.copy()
            if ativo_div_sel != "Todos":
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered["Ativo"] == ativo_div_sel]
                
            df_dividendos_display = df_dividendos_filtered.copy()
            
            # Calcula "Dias até" dinamicamente
            def calc_dividendos_dias(date_val):
                if pd.isna(date_val):
                    return ""
                today = pd.Timestamp.now().normalize()
                date_val = pd.to_datetime(date_val).normalize()
                if date_val < today:
                    return "Já creditado"
                elif date_val == today:
                    return "Credita hoje!"
                else:
                    diff = (date_val - today).days
                    return f"Faltam {diff} dias"
                    
            df_dividendos_display["Dias até"] = df_dividendos_display["Recebido em"].apply(calc_dividendos_dias)
            df_dividendos_display["Valor"] = df_dividendos_display["Valor"].apply(lambda v: format_number(v, is_currency=True, currency="BRL"))
            st.dataframe(
                df_dividendos_display,
                column_config={
                    "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                },
                width='stretch'
            )
            
            # Soma totalizadora dinâmica
            total_div_soma = df_dividendos_filtered["Valor"].sum()
            total_div_formatted = format_number(total_div_soma, is_currency=True, currency="BRL")
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Dividendos (Filtro)</span>
                <span style="font-weight: 700; color: #FFC107; font-size: 20px;">{total_div_formatted}</span>
            </div>
            """, unsafe_allow_html=True)

# ================= TAB 4: CONSULTORIA COM IA =================
with tab4:
    st.subheader("🤖 Consultoria Estratégica com Inteligência Artificial")
    st.markdown("""
    O assistente de inteligência artificial analisa em tempo real os ativos da sua carteira, o histórico de rentabilidade 
    e o fluxo de caixa do seu orçamento para gerar um diagnóstico completo e sugerir novos aportes com segurança e eficiência.
    """)
    
    # Exibe caixa de informações sobre a IA
    st.info("🧠 A IA do Gemini analisará sua relação Receitas vs Despesas, a taxa de poupança atual e a distribuição dos ativos para dar recomendações de alocação personalizadas baseadas no mercado financeiro brasileiro.")
    
    btn_analise = st.button("🚀 Solicitar Diagnóstico da Inteligência Artificial", key="gemini_btn")
    
    if btn_analise:
        with st.spinner("A Inteligência Artificial está analisando seus números... Isso pode levar alguns segundos."):
            relatorio = generate_allocation_tips(df_holdings, df_receitas, df_despesas, df_dividendos)
            
            st.markdown("---")
            st.markdown("### 📋 Diagnóstico Personalizado do Gemini")
            st.markdown(relatorio)
            st.markdown("---")
