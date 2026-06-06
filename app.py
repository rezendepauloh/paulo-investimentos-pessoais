import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()

# Importações internas
import db_manager
from data_loader import get_budget_data, get_orders_data, sync_google_sheets_to_sqlite, sync_fundamental_data_from_yfinance, TERMOS_CONTABEIS
from analytics import calculate_portfolio_holdings, get_historical_performance, get_usd_brl_rate
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
    
    /* Torna o cabeçalho padrão do Streamlit transparente para não cobrir as abas */
    header[data-testid="stHeader"], [data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Reduz drasticamente o padding superior e traz o conteúdo mais para cima */
    .block-container, div[data-testid="stMainBlockContainer"] {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
        position: relative !important;
    }
    
    /* Reposiciona apenas as abas de navegação (stRadio com key="navigation_tabs") no topo */
    .st-key-navigation_tabs div[data-testid="stRadio"] {
        position: absolute !important;
        top: -35px !important;
        left: 0px !important;
        z-index: 999999 !important;
        background-color: transparent !important;
        margin: 0 !important;
        padding: 0 !important;
        width: max-content !important;
    }
    
    /* Alinha opções do radio de navegação em linha horizontal compacta */
    .st-key-navigation_tabs div[data-testid="stRadio"] [role="radiogroup"] {
        flex-direction: row !important;
        gap: 8px !important;
    }
    
    /* Oculta a bolinha padrão do radio de navegação */
    .st-key-navigation_tabs div[data-testid="stRadio"] label > div:first-child {
        display: none !important;
    }
    
    /* Estiliza as abas de navegação de forma premium e elegante no cabeçalho */
    .st-key-navigation_tabs div[data-testid="stRadio"] label {
        background-color: #1e1f25 !important;
        border: 1px solid #343541 !important;
        padding: 6px 16px !important;
        border-radius: 6px !important;
        cursor: pointer !important;
        transition: all 0.2s ease-in-out !important;
        margin: 0 !important;
        white-space: nowrap !important;
        font-family: 'Outfit', sans-serif !important;
        color: #ffffff !important;
    }
    
    .st-key-navigation_tabs div[data-testid="stRadio"] label:hover {
        border-color: #00E676 !important;
        background-color: #2a2b36 !important;
        color: #00E676 !important;
    }
    
    /* Destaca a aba ativa de navegação com a cor verde tema do painel */
    .st-key-navigation_tabs div[data-testid="stRadio"] label:has(input:checked) {
        background-color: #00E676 !important;
        color: #121214 !important;
        border-color: #00E676 !important;
        font-weight: bold !important;
        box-shadow: 0 0 12px rgba(0, 230, 118, 0.4) !important;
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

# --- LAYOUT E NAVEGAÇÃO POR ABAS (Estilo dashboard.py com st.radio) ---
selected_tab = st.radio(
    "Navegação",
    [
        "📊 Visão Geral e Orçamento",
        "📈 Desempenho e Benchmarks",
        "📑 Extratos e Lançamentos",
        "🔍 Análise Fundamentalista",
        "🤖 Consultoria de Alocação com IA"
    ],
    horizontal=True,
    label_visibility="collapsed",
    key="navigation_tabs"
)

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
        st.subheader("🔄 Sincronização Local")
        
        last_sync = db_manager.get_last_sync_time()
        st.info(f"Última sincronização:\n**{last_sync}**")
        
        if st.button("🔄 Sincronizar Google Sheets", width='stretch', help="Baixa lançamentos e ordens mais recentes do Sheets de forma incremental e atualiza o SQLite local."):
            with st.spinner("Sincronizando dados incrementalmente..."):
                try:
                    sync_google_sheets_to_sqlite()
                    st.cache_data.clear()
                    st.success("✅ Sincronização delta realizada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro na sincronização: {e}")
                    
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

# --- CONTEÚDO DAS ABAS ---

# ================= TAB 1: VISÃO GERAL =================
if selected_tab == "📊 Visão Geral e Orçamento":
    if df_holdings.empty:
        st.warning("Nenhuma ordem ativa na carteira de investimentos.")
    else:
        # Função para filtrar lançamentos ocorridos (Dias até = Já creditado/debitado ou <= 0)
        def filter_realized(df_budget, col_dias):
            if df_budget.empty:
                return df_budget
            if col_dias not in df_budget.columns:
                return df_budget
            def check_realized(val):
                v_str = str(val).strip().upper()
                if "FALTAM" in v_str:
                    return False
                try:
                    if float(v_str.replace(",", ".")) > 0:
                        return False
                except ValueError:
                    pass
                return True
            return df_budget[df_budget[col_dias].apply(check_realized)]
            
        # Filtra lançamentos orçamentários efetivamente realizados
        df_receitas_realized = filter_realized(df_receitas, "Dias até")
        df_despesas_realized = filter_realized(df_despesas, "Dias até")

        # Métricas Globais
        total_market_val = df_holdings["valor_atual"].sum()
        
        # Calcula o Capital Investido líquido (Aportes - Resgates/Vendas)
        total_invested = 0.0
        if not df_orders.empty:
            usd_brl_rate = get_usd_brl_rate()
            for _, row in df_orders.iterrows():
                action = str(row.get("Compra/Venda", "")).strip().upper()
                val = float(row.get("Total líquido", 0))
                moeda = str(row.get("Moeda", "BRL")).strip().upper()
                qty = float(row.get("Qtd Executada", 0))
                
                # Conversão para BRL se for USD
                if moeda == "USD":
                    is_planilha_em_brl = False
                    if val >= 1000.0 or (qty > 0 and (val / qty) > 15.0):
                        is_planilha_em_brl = True
                    val_brl = val if is_planilha_em_brl else val * usd_brl_rate
                else:
                    val_brl = val
                    
                if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO"]):
                    total_invested += val_brl
                elif "VENDA" in action or action == "V":
                    total_invested -= val_brl
        else:
            total_invested = df_holdings["total_investido"].sum() if not df_holdings.empty else 0.0
        total_profit = total_market_val - total_invested
        total_return_pct = (total_profit / total_invested) * 100.0 if total_invested > 0 else 0.0
        
        # Identifica o mês de análise (o mês mais recente com lançamentos ocorridos ou o mês atual)
        target_year = pd.Timestamp.now().year
        target_month = pd.Timestamp.now().month
        
        all_dates = []
        if not df_receitas_realized.empty and "Recebido em" in df_receitas_realized.columns:
            all_dates.extend(df_receitas_realized["Recebido em"].dropna().tolist())
        if not df_despesas_realized.empty and "Gasto em" in df_despesas_realized.columns:
            all_dates.extend(df_despesas_realized["Gasto em"].dropna().tolist())
            
        if all_dates:
            latest_date = pd.to_datetime(all_dates).max()
            target_year = latest_date.year
            target_month = latest_date.month
            
        df_rec_curr_month = df_receitas_realized[
            (pd.to_datetime(df_receitas_realized["Recebido em"]).dt.year == target_year) & 
            (pd.to_datetime(df_receitas_realized["Recebido em"]).dt.month == target_month)
        ] if not df_receitas_realized.empty else pd.DataFrame()
        
        df_desp_curr_month = df_despesas_realized[
            (pd.to_datetime(df_despesas_realized["Gasto em"]).dt.year == target_year) & 
            (pd.to_datetime(df_despesas_realized["Gasto em"]).dt.month == target_month)
        ] if not df_despesas_realized.empty else pd.DataFrame()
        
        total_receitas_mes = df_rec_curr_month["Valor"].sum() if not df_rec_curr_month.empty else 0.0
        total_despesas_mes = df_desp_curr_month["Valor"].sum() if not df_desp_curr_month.empty else 0.0
        total_proventos = df_dividendos["Valor"].sum() if not df_dividendos.empty else 0.0
        
        saving_rate = total_receitas_mes - total_despesas_mes
        saving_pct = (saving_rate / total_receitas_mes * 100.0) if total_receitas_mes > 0 else 0.0
        
        months_names = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
            7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }
        mes_card_label = f"Poupança ({months_names.get(target_month, '')}/{target_year})"
        
        # Fluxo de caixa recente (apenas realizados, para o gráfico de fluxo de caixa global)
        total_receitas = df_receitas_realized["Valor"].sum() if not df_receitas_realized.empty else 0.0
        total_despesas = df_despesas_realized["Valor"].sum() if not df_despesas_realized.empty else 0.0
        
        # Formata os valores para exibição no estilo PT-BR
        total_market_val_formatted = format_number(total_market_val, is_currency=True, currency="BRL")
        total_invested_formatted = format_number(total_invested, is_currency=True, currency="BRL")
        total_profit_formatted = format_number(abs(total_profit), is_currency=True, currency="BRL")
        total_return_pct_formatted = format_number(abs(total_return_pct), decimals=2)
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
            saving_class = "metric-delta-positive" if saving_rate >= 0 else "metric-delta-negative"
            saving_prefix = "+" if saving_rate >= 0 else ""
            saving_text = "poupado" if saving_rate >= 0 else "de déficit"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{mes_card_label}</div>
                <div class="metric-value">{saving_rate_formatted}</div>
                <div class="{saving_class}">{saving_prefix}{saving_pct_formatted}% da receita {saving_text}</div>
            </div>
            """, unsafe_allow_html=True)

        # Gráficos da Distribuição da Carteira
        st.markdown("### 📊 Alocação de Recursos")
        
        exibicao_alocacao = st.radio(
            "Visualização da Carteira:",
            ["Hierárquica Integrada (Sunburst)", "Detalhada Lado a Lado (3 Gráficos)"],
            horizontal=True,
            index=0
        )
        
        if exibicao_alocacao == "Hierárquica Integrada (Sunburst)":
            st.subheader("Visão Hierárquica da Carteira (Classe > Setor > Ativo)")
            df_sunburst = df_holdings.copy()
            df_sunburst["setor_economico"] = df_sunburst["setor_economico"].fillna("Outros").replace("", "Outros")
            df_sunburst["ticker"] = df_sunburst["ticker"].fillna("Outros").replace("", "Outros")
            
            fig_sunburst = px.sunburst(
                df_sunburst,
                path=["tipo", "setor_economico", "ticker"],
                values="valor_atual",
                color_discrete_sequence=px.colors.qualitative.G10
            )
            fig_sunburst.update_traces(
                textinfo="label+percent parent",
                hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<br>Proporção (Pai): %{percentParent:.2%}<br>Proporção (Total): %{percentRoot:.2%}<extra></extra>"
            )
            fig_sunburst.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ffffff",
                margin=dict(t=20, b=20, l=20, r=20),
                separators=",."
            )
            st.plotly_chart(fig_sunburst, width='stretch')
            
        else:
            col_g1, col_g2, col_g3 = st.columns(3)
            
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
                st.subheader("Distribuição por Setor Econômico")
                if "setor_economico" in df_holdings.columns:
                    df_holdings["setor_economico"] = df_holdings["setor_economico"].fillna("Outros").replace("", "Outros")
                    fig_pie_sector = px.pie(
                        df_holdings,
                        names="setor_economico",
                        values="valor_atual",
                        hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Dark24
                    )
                    fig_pie_sector.update_traces(
                        textposition='inside', 
                        textinfo='percent+label',
                        hovertemplate="<b>Setor:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Proporção:</b> %{percent}<extra></extra>"
                    )
                    fig_pie_sector.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#ffffff",
                        showlegend=False,
                        margin=dict(t=10, b=10, l=10, r=10),
                        separators=",."
                    )
                    st.plotly_chart(fig_pie_sector, width='stretch')
                else:
                    st.info("Setor econômico não disponível nos dados.")
                
            with col_g3:
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

        # Gráficos de Categorias de Receitas e Despesas (Princípio da Competência Ocorrida)
        st.markdown("### 🏷️ Distribuição de Receitas e Despesas Realizadas")
        
        exibicao_receitas_despesas = st.radio(
            "Visualização de Receitas e Despesas:",
            ["Detalhada Lado a Lado (3 Gráficos)", "Hierárquica de Despesas (Sunburst)"],
            horizontal=True,
            index=0,
            key="rec_desp_view"
        )
        
        if exibicao_receitas_despesas == "Hierárquica de Despesas (Sunburst)":
            st.subheader("Visão Hierárquica de Gastos (Conta Debitada > Categoria)")
            if not df_despesas.empty and not df_despesas_realized.empty:
                df_desp_sunburst = df_despesas_realized.copy()
                df_desp_sunburst["Conta debitada"] = df_desp_sunburst["Conta debitada"].fillna("Não Informado").replace("", "Não Informado")
                df_desp_sunburst["Categoria"] = df_desp_sunburst["Categoria"].fillna("Outros").replace("", "Outros")
                
                fig_desp_sun = px.sunburst(
                    df_desp_sunburst,
                    path=["Conta debitada", "Categoria"],
                    values="Valor",
                    color_discrete_sequence=px.colors.qualitative.Safe
                )
                fig_desp_sun.update_traces(
                    textinfo="label+percent parent",
                    hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<br>Proporção (Pai): %{percentParent:.2%}<br>Proporção (Total): %{percentRoot:.2%}<extra></extra>"
                )
                fig_desp_sun.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#ffffff",
                    margin=dict(t=20, b=20, l=20, r=20),
                    separators=",."
                )
                st.plotly_chart(fig_desp_sun, width='stretch')
            else:
                st.info("Nenhuma despesa lançada para visualização hierárquica.")
        else:
            col_cat1, col_cat2, col_cat3 = st.columns(3)
            
            with col_cat1:
                st.subheader("Receitas por Categoria (Realizadas)")
                if not df_receitas.empty:
                    if not df_receitas_realized.empty:
                        df_rec_cat = df_receitas_realized.groupby("Categoria")["Valor"].sum().reset_index()
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
                        st.info("Nenhuma receita realizada até o momento.")
                else:
                    st.info("Nenhuma receita lançada para categorização.")
                    
            with col_cat2:
                st.subheader("Despesas por Categoria (Realizadas)")
                if not df_despesas.empty:
                    if not df_despesas_realized.empty:
                        df_desp_cat = df_despesas_realized.groupby("Categoria")["Valor"].sum().reset_index()
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
                        st.info("Nenhuma despesa realizada até o momento.")
                else:
                    st.info("Nenhuma despesa lançada para categorização.")
     
            with col_cat3:
                st.subheader("Despesas por Conta Debitada")
                if not df_despesas.empty:
                    if not df_despesas_realized.empty and "Conta debitada" in df_despesas_realized.columns:
                        # Copia para não alterar o DataFrame original
                        df_desp_acc_copy = df_despesas_realized.copy()
                        df_desp_acc_copy["Conta debitada"] = df_desp_acc_copy["Conta debitada"].fillna("Não Informado").replace("", "Não Informado")
                        df_desp_acc = df_desp_acc_copy.groupby("Conta debitada")["Valor"].sum().reset_index()
                        fig_desp_acc = px.pie(
                            df_desp_acc,
                            names="Conta debitada",
                            values="Valor",
                            hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Safe
                        )
                        fig_desp_acc.update_traces(
                            textposition='inside', 
                            textinfo='percent+label',
                            hovertemplate="<b>Conta:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Proporção:</b> %{percent}<extra></extra>"
                        )
                        fig_desp_acc.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="#ffffff",
                            showlegend=False,
                            margin=dict(t=10, b=10, l=10, r=10),
                            separators=",."
                        )
                        st.plotly_chart(fig_desp_acc, width='stretch')
                    else:
                        st.info("Nenhuma despesa com conta debitada realizada.")
                else:
                    st.info("Nenhuma despesa lançada para categorização por conta.")

        # Novo bloco: Análise de Custo de Vida e Saúde Financeira
        if not df_despesas.empty and not df_despesas_realized.empty:
            has_fixo = "Fixo vs. Variável" in df_despesas_realized.columns
            has_essencial = "Essencial vs. Não Essencial" in df_despesas_realized.columns
            
            if has_fixo or has_essencial:
                st.markdown("### 🏷️ Custo de Vida e Saúde Financeira (Realizado)")
                
                exibicao_custo_vida = st.radio(
                    "Visualização do Custo de Vida:",
                    ["Hierárquica Integrada (Sunburst)", "Detalhada Lado a Lado (2 Gráficos)"],
                    horizontal=True,
                    index=0,
                    key="custo_vida_view"
                )
                
                if exibicao_custo_vida == "Hierárquica Integrada (Sunburst)":
                    st.subheader("Visão Hierárquica de Despesas (Custo de Vida > Saúde > Categoria)")
                    df_cv_sunburst = df_despesas_realized.copy()
                    df_cv_sunburst["Fixo vs. Variável"] = df_cv_sunburst["Fixo vs. Variável"].fillna("Não Definido").replace("", "Não Definido")
                    df_cv_sunburst["Essencial vs. Não Essencial"] = df_cv_sunburst["Essencial vs. Não Essencial"].fillna("Não Definido").replace("", "Não Definido")
                    df_cv_sunburst["Categoria"] = df_cv_sunburst["Categoria"].fillna("Outros").replace("", "Outros")
                    
                    fig_cv_sunburst = px.sunburst(
                        df_cv_sunburst,
                        path=["Fixo vs. Variável", "Essencial vs. Não Essencial", "Categoria"],
                        values="Valor",
                        color="Fixo vs. Variável",
                        color_discrete_map={"Fixo": "#FF5252", "Variável": "#FFC107", "Não Definido": "#88888b"}
                    )
                    fig_cv_sunburst.update_traces(
                        textinfo="label+percent parent",
                        hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<br>Proporção (Pai): %{percentParent:.2%}<br>Proporção (Total): %{percentRoot:.2%}<extra></extra>"
                    )
                    fig_cv_sunburst.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#ffffff",
                        margin=dict(t=20, b=20, l=20, r=20),
                        separators=",."
                    )
                    st.plotly_chart(fig_cv_sunburst, width='stretch')
                    
                    # Métricas resumidas abaixo do Sunburst
                    custo_vida_minimo = df_despesas_realized[df_despesas_realized["Fixo vs. Variável"].str.upper() == "FIXO"]["Valor"].sum()
                    custo_vida_minimo_fmt = format_number(custo_vida_minimo, is_currency=True, currency="BRL")
                    
                    total_desp_real = df_despesas_realized["Valor"].sum()
                    essencial_val = df_despesas_realized[df_despesas_realized["Essencial vs. Não Essencial"].str.upper() == "ESSENCIAL"]["Valor"].sum()
                    pct_ess = (essencial_val / total_desp_real * 100.0) if total_desp_real > 0 else 0.0
                    
                    st.markdown(f"**Custo de Vida Mínimo Previsível (Fixo):** `{custo_vida_minimo_fmt}` | **Proporção de Gastos Essenciais:** `{pct_ess:.1f}%` (Ideal: ~50% pela regra 50/30/20)")
                else:
                    col_cf1, col_cf2 = st.columns(2)
                    
                    with col_cf1:
                        st.subheader("Custo de Vida: Fixo vs. Variável")
                        if has_fixo:
                            df_despesas_realized["Fixo vs. Variável"] = df_despesas_realized["Fixo vs. Variável"].fillna("Não Definido").replace("", "Não Definido")
                            df_fixo = df_despesas_realized.groupby("Fixo vs. Variável")["Valor"].sum().reset_index()
                            
                            # Destaca o custo fixo como custo de vida mínimo previsível
                            custo_vida_minimo = df_despesas_realized[df_despesas_realized["Fixo vs. Variável"].str.upper() == "FIXO"]["Valor"].sum()
                            custo_vida_minimo_fmt = format_number(custo_vida_minimo, is_currency=True, currency="BRL")
                            
                            fig_fixo = px.pie(
                                df_fixo,
                                names="Fixo vs. Variável",
                                values="Valor",
                                hole=0.45,
                                color="Fixo vs. Variável",
                                color_discrete_map={"Fixo": "#FF5252", "Variável": "#FFC107", "Não Definido": "#88888b"}
                            )
                            fig_fixo.update_traces(
                                textposition='inside', 
                                textinfo='percent+label',
                                hovertemplate="<b>Tipo:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<extra></extra>"
                            )
                            fig_fixo.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="#ffffff",
                                showlegend=False,
                                margin=dict(t=10, b=10, l=10, r=10),
                                separators=",."
                            )
                            st.plotly_chart(fig_fixo, width='stretch')
                            st.markdown(f"**Custo de Vida Mínimo Previsível (Fixo):** `{custo_vida_minimo_fmt}`")
                        else:
                            st.info("Coluna 'Fixo vs. Variável' não preenchida.")
                            
                    with col_cf2:
                        st.subheader("Saúde Financeira: Essencial vs. Não Essencial")
                        if has_essencial:
                            df_despesas_realized["Essencial vs. Não Essencial"] = df_despesas_realized["Essencial vs. Não Essencial"].fillna("Não Definido").replace("", "Não Definido")
                            df_ess = df_despesas_realized.groupby("Essencial vs. Não Essencial")["Valor"].sum().reset_index()
                            
                            fig_ess = px.pie(
                                df_ess,
                                names="Essencial vs. Não Essencial",
                                values="Valor",
                                hole=0.45,
                                color="Essencial vs. Não Essencial",
                                color_discrete_map={"Essencial": "#2979FF", "Não essencial": "#E040FB", "Não Definido": "#88888b"}
                            )
                            fig_ess.update_traces(
                                textposition='inside', 
                                textinfo='percent+label',
                                hovertemplate="<b>Tipo:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<extra></extra>"
                            )
                            fig_ess.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="#ffffff",
                                showlegend=False,
                                margin=dict(t=10, b=10, l=10, r=10),
                                separators=",."
                            )
                            st.plotly_chart(fig_ess, width='stretch')
                            
                            # Explica a regra 50/30/20
                            total_desp_real = df_despesas_realized["Valor"].sum()
                            essencial_val = df_despesas_realized[df_despesas_realized["Essencial vs. Não Essencial"].str.upper() == "ESSENCIAL"]["Valor"].sum()
                            pct_ess = (essencial_val / total_desp_real * 100.0) if total_desp_real > 0 else 0.0
                            st.markdown(f"**Proporção de Gastos Essenciais:** `{pct_ess:.1f}%` (Ideal: ~50% pela regra 50/30/20)")
                        else:
                            st.info("Coluna 'Essencial vs. Não Essencial' não preenchida.")

        # Novo bloco: Histórico Mensal de Receitas, Despesas e Dividendos (Sem filtros de creditado/debitado)
        st.markdown("### 📊 Evolução Mensal de Receitas, Despesas e Dividendos")
        
        # Cria cópias dos dados para manipulação
        df_rec_m = df_receitas.copy() if not df_receitas.empty else pd.DataFrame()
        df_desp_m = df_despesas.copy() if not df_despesas.empty else pd.DataFrame()
        df_div_m = df_dividendos.copy() if not df_dividendos.empty else pd.DataFrame()
        
        monthly_data = []
        
        # Processa receitas por mês
        if not df_rec_m.empty and "Recebido em" in df_rec_m.columns:
            df_rec_m["Mes"] = pd.to_datetime(df_rec_m["Recebido em"]).dt.strftime("%Y-%m")
            df_grouped_rec = df_rec_m.groupby("Mes")["Valor"].sum().reset_index()
            for _, r in df_grouped_rec.iterrows():
                monthly_data.append({"Mês": r["Mes"], "Tipo": "Receitas", "Valor": r["Valor"]})
                
        # Processa despesas por mês
        if not df_desp_m.empty and "Gasto em" in df_desp_m.columns:
            df_desp_m["Mes"] = pd.to_datetime(df_desp_m["Gasto em"]).dt.strftime("%Y-%m")
            df_grouped_desp = df_desp_m.groupby("Mes")["Valor"].sum().reset_index()
            for _, r in df_grouped_desp.iterrows():
                monthly_data.append({"Mês": r["Mes"], "Tipo": "Despesas", "Valor": r["Valor"]})
                
        # Processa dividendos por mês
        if not df_div_m.empty and "Recebido em" in df_div_m.columns:
            df_div_m["Mes"] = pd.to_datetime(df_div_m["Recebido em"]).dt.strftime("%Y-%m")
            df_grouped_div = df_div_m.groupby("Mes")["Valor"].sum().reset_index()
            for _, r in df_grouped_div.iterrows():
                monthly_data.append({"Mês": r["Mes"], "Tipo": "Dividendos", "Valor": r["Valor"]})
                
        if monthly_data:
            df_monthly = pd.DataFrame(monthly_data)
            # Ordena de forma cronológica antes da formatação de strings
            df_monthly = df_monthly.sort_values("Mês")
            
            # Mapeamento e formatação elegante para português (ex: "Jan/26")
            months_pt = {
                "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr", "05": "Mai", "06": "Jun",
                "07": "Jul", "08": "Ago", "09": "Set", "10": "Out", "11": "Nov", "12": "Dez"
            }
            def format_month_pt(yr_mo_str):
                try:
                    yr, mo = yr_mo_str.split("-")
                    return f"{months_pt.get(mo, mo)}/{yr[2:]}"
                except Exception:
                    return yr_mo_str
                    
            df_monthly["Mês Exibição"] = df_monthly["Mês"].apply(format_month_pt)
            
            # Gráfico de barras agrupado por mês
            fig_monthly_bar = px.bar(
                df_monthly,
                x="Mês Exibição",
                y="Valor",
                color="Tipo",
                barmode="group",
                color_discrete_map={"Receitas": "#00E676", "Despesas": "#FF5252", "Dividendos": "#FFC107"}
            )
            fig_monthly_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ffffff",
                xaxis_title="Mês",
                yaxis_title="Valor (R$)",
                legend_title="Tipo",
                separators=",."
            )
            # Garante que o Plotly trate o eixo como categoria discreta e exiba 100% dos meses listados
            fig_monthly_bar.update_xaxes(type='category')
            fig_monthly_bar.update_traces(
                hovertemplate="<b>Mês:</b> %{x}<br><b>Valor:</b> R$ %{y:,.2f}<extra></extra>"
            )
            st.plotly_chart(fig_monthly_bar, width='stretch')
        else:
            st.info("Sem dados de receitas, despesas ou dividendos para agrupar por mês.")

# ================= TAB 2: HISTÓRICO E BENCHMARKS =================
elif selected_tab == "📈 Desempenho e Benchmarks":
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
            "IPCA + 6% Acumulado (%) Ajustado": {"label": "IPCA + 6%", "color": "#E91E63", "width": 2},
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
elif selected_tab == "📑 Extratos e Lançamentos":
    st.subheader("📑 Visualização dos Lançamentos e Histórico de Transações")
    
    sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs(["Receitas", "Despesas", "Dividendos", "Ordens de Compra/Venda"])
    
    with sub_tab1:
        st.markdown("### 🪙 Receitas")
        if df_receitas.empty:
            st.info("Nenhuma receita cadastrada.")
        else:
            # Filtros por Nome, Categoria e Mês/Ano de Receitas em colunas
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                nomes_receitas = ["Todos"] + sorted(df_receitas["Nome"].dropna().unique().tolist())
                nome_receita_sel = st.selectbox("Filtrar por Descrição:", nomes_receitas, key="filter_rec_nome")
            with col_r2:
                categorias_receitas = ["Todas"] + sorted(df_receitas["Categoria"].dropna().unique().tolist())
                cat_receita_sel = st.selectbox("Filtrar por Categoria (Receitas):", categorias_receitas, key="filter_rec_cat")
            with col_r3:
                df_temp = df_receitas.copy()
                df_temp["Recebido em_dt"] = pd.to_datetime(df_temp["Recebido em"], errors='coerce')
                df_temp["Mes_Ano"] = df_temp["Recebido em_dt"].dt.strftime("%m/%Y")
                unique_months = df_temp["Mes_Ano"].dropna().unique().tolist()
                unique_months_sorted = sorted(unique_months, key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
                meses_anos = ["Todos"] + unique_months_sorted
                mes_ano_rec_sel = st.selectbox("Filtrar por Mês/Ano:", meses_anos, key="filter_rec_mes_ano")
            
            df_receitas_filtered = df_receitas.copy()
            if nome_receita_sel != "Todos":
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Nome"] == nome_receita_sel]
            if cat_receita_sel != "Todas":
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Categoria"] == cat_receita_sel]
            if mes_ano_rec_sel != "Todos":
                df_receitas_filtered = df_receitas_filtered[pd.to_datetime(df_receitas_filtered["Recebido em"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_rec_sel]
                
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
            st.dataframe(
                df_receitas_display,
                column_config={
                    "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                    "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
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
        st.markdown("### 🪙 Despesas")
        if df_despesas.empty:
            st.info("Nenhuma despesa cadastrada.")
        else:
            # Filtros para Despesas
            col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)
            with col_filter1:
                categorias_despesas = ["Todas"] + sorted(df_despesas["Categoria"].dropna().unique().tolist())
                cat_despesa_sel = st.selectbox("Filtrar por Categoria (Despesas):", categorias_despesas, key="filter_des_cat")
            with col_filter2:
                fixo_opcoes = ["Todos"]
                if "Fixo vs. Variável" in df_despesas.columns:
                    fixo_opcoes += sorted(df_despesas["Fixo vs. Variável"].dropna().unique().tolist())
                fixo_sel = st.selectbox("Fixo vs. Variável:", fixo_opcoes, key="filter_des_fixo")
            with col_filter3:
                essencial_opcoes = ["Todos"]
                if "Essencial vs. Não Essencial" in df_despesas.columns:
                    essencial_opcoes += sorted(df_despesas["Essencial vs. Não Essencial"].dropna().unique().tolist())
                essencial_sel = st.selectbox("Essencial vs. Não Essencial:", essencial_opcoes, key="filter_des_essencial")
            with col_filter4:
                df_temp = df_despesas.copy()
                df_temp["Gasto em_dt"] = pd.to_datetime(df_temp["Gasto em"], errors='coerce')
                df_temp["Mes_Ano"] = df_temp["Gasto em_dt"].dt.strftime("%m/%Y")
                unique_months = df_temp["Mes_Ano"].dropna().unique().tolist()
                unique_months_sorted = sorted(unique_months, key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
                meses_anos = ["Todos"] + unique_months_sorted
                mes_ano_desp_sel = st.selectbox("Filtrar por Mês/Ano:", meses_anos, key="filter_des_mes_ano")
            
            df_despesas_filtered = df_despesas.copy()
            if cat_despesa_sel != "Todas":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Categoria"] == cat_despesa_sel]
            if "Fixo vs. Variável" in df_despesas_filtered.columns and fixo_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Fixo vs. Variável"] == fixo_sel]
            if "Essencial vs. Não Essencial" in df_despesas_filtered.columns and essencial_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Essencial vs. Não Essencial"] == essencial_sel]
            if mes_ano_desp_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[pd.to_datetime(df_despesas_filtered["Gasto em"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_desp_sel]
                
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
            st.dataframe(
                df_despesas_display,
                column_config={
                    "Gasto em": st.column_config.DateColumn("Gasto Em", format="DD/MM/YYYY"),
                    "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
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
        st.markdown("### 🪙 Dividendos recebidos")
        if df_dividendos.empty:
            st.info("Nenhum dividendo passivo lançado.")
        else:
            # Filtros por Ativo, Categoria e Mês/Ano de Dividendos em colunas
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                ativos_dividendos = ["Todos"] + sorted(df_dividendos["Ativo"].dropna().unique().tolist())
                ativo_div_sel = st.selectbox("Filtrar por Ativo (Dividendos):", ativos_dividendos, key="filter_div_ativo")
            with col_d2:
                categorias_dividendos = ["Todas"] + sorted(df_dividendos["Categoria"].dropna().unique().tolist())
                cat_div_sel = st.selectbox("Filtrar por Categoria (Dividendos):", categorias_dividendos, key="filter_div_cat")
            with col_d3:
                df_temp = df_dividendos.copy()
                df_temp["Recebido em_dt"] = pd.to_datetime(df_temp["Recebido em"], errors='coerce')
                df_temp["Mes_Ano"] = df_temp["Recebido em_dt"].dt.strftime("%m/%Y")
                unique_months = df_temp["Mes_Ano"].dropna().unique().tolist()
                unique_months_sorted = sorted(unique_months, key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
                meses_anos = ["Todos"] + unique_months_sorted
                mes_ano_div_sel = st.selectbox("Filtrar por Mês/Ano:", meses_anos, key="filter_div_mes_ano")
            
            df_dividendos_filtered = df_dividendos.copy()
            if ativo_div_sel != "Todos":
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered["Ativo"] == ativo_div_sel]
            if cat_div_sel != "Todas":
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered["Categoria"] == cat_div_sel]
            if mes_ano_div_sel != "Todos":
                df_dividendos_filtered = df_dividendos_filtered[pd.to_datetime(df_dividendos_filtered["Recebido em"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_div_sel]
                
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
            st.dataframe(
                df_dividendos_display,
                column_config={
                    "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                    "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
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
            
    with sub_tab4:
        st.markdown("### 🪙 Histórico de Ordens de Compra e Venda")
        if df_orders.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
            # Filtros interativos para as Ordens
            col_o1, col_o2, col_o3, col_o4, col_o5 = st.columns(5)
            with col_o1:
                ativos_unicos = ["Todos"] + sorted(df_orders["Papel"].dropna().unique().tolist())
                ativo_selecionado = st.selectbox("Filtrar por Ativo:", ativos_unicos, key="filter_orders_ativo")
            with col_o2:
                acoes_unicas = ["Todos"] + sorted(df_orders["Compra/Venda"].dropna().unique().tolist())
                acao_selecionada = st.selectbox("Compra/Venda:", acoes_unicas, key="filter_orders_acao")
            with col_o3:
                tipos_unicos = ["Todos"] + sorted(df_orders["Tipo"].dropna().unique().tolist())
                tipo_selecionado = st.selectbox("Tipo:", tipos_unicos, key="filter_orders_tipo")
            with col_o4:
                setores_unicos = ["Todos"]
                if "Setor Econômico" in df_orders.columns:
                    setores_unicos += sorted(df_orders["Setor Econômico"].dropna().unique().tolist())
                setor_selecionado = st.selectbox("Setor Econômico:", setores_unicos, key="filter_orders_setor")
            with col_o5:
                df_temp = df_orders.copy()
                df_temp["data envio_dt"] = pd.to_datetime(df_temp["data envio"], errors='coerce')
                df_temp["Mes_Ano"] = df_temp["data envio_dt"].dt.strftime("%m/%Y")
                unique_months = df_temp["Mes_Ano"].dropna().unique().tolist()
                unique_months_sorted = sorted(unique_months, key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
                meses_anos = ["Todos"] + unique_months_sorted
                mes_ano_ord_sel = st.selectbox("Filtrar por Mês/Ano:", meses_anos, key="filter_orders_mes_ano")
            
            df_orders_filtered = df_orders.copy()
            if ativo_selecionado != "Todos":
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Papel"] == ativo_selecionado]
            if acao_selecionada != "Todos":
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Compra/Venda"] == acao_selecionada]
            if tipo_selecionado != "Todos":
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Tipo"] == tipo_selecionado]
            if "Setor Econômico" in df_orders_filtered.columns and setor_selecionado != "Todos":
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Setor Econômico"] == setor_selecionado]
            if mes_ano_ord_sel != "Todos":
                df_orders_filtered = df_orders_filtered[pd.to_datetime(df_orders_filtered["data envio"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_ord_sel]
                
            df_orders_display = df_orders_filtered.sort_values("data envio", ascending=False).copy()
            # Mantém valores como numéricos para permitir ordenação correta, formatando pelo st.column_config
            moedas_filtradas = df_orders_filtered["Moeda"].unique()
            prefixo_moeda = "R$" if (len(moedas_filtradas) == 1 and moedas_filtradas[0] == "BRL") else ("$" if (len(moedas_filtradas) == 1 and moedas_filtradas[0] == "USD") else "")
            format_str = f"{prefixo_moeda} %.2f" if prefixo_moeda else "%.2f"
            
            st.dataframe(
                df_orders_display,
                column_config={
                    "data envio": st.column_config.DatetimeColumn("Data Envio", format="DD/MM/YYYY HH:mm"),
                    "Total líquido": st.column_config.NumberColumn("Total líquido", format=format_str),
                    "Preço médio + corretagem": st.column_config.NumberColumn("Preço médio + corretagem", format=format_str),
                    "Preço médio": st.column_config.NumberColumn("Preço médio", format=format_str),
                    "Total": st.column_config.NumberColumn("Total", format=format_str),
                    "Corretagem": st.column_config.NumberColumn("Corretagem", format=format_str),
                    "Qtd Executada": st.column_config.NumberColumn("Qtd Executada", format="%.4f"),
                },
                width='stretch'
            )
            
            # Soma totalizadora dinâmica (Compra - Venda)
            def calc_net_order_value(row):
                action = str(row.get("Compra/Venda", "")).strip().upper()
                val = float(row.get("Total líquido", 0))
                if "VENDA" in action or action == "V":
                    return -val
                return val
                
            net_values = df_orders_filtered.apply(calc_net_order_value, axis=1)
            
            moedas_filtradas = df_orders_filtered["Moeda"].unique()
            if len(moedas_filtradas) == 1:
                moeda_display = moedas_filtradas[0]
                total_soma_ordens = net_values.sum()
            else:
                # Caso misto (exibe o consolidado total líquido em BRL)
                total_soma_ordens = net_values.sum()
                moeda_display = "BRL"
                
            total_soma_formatted = format_number(total_soma_ordens, is_currency=True, currency=moeda_display)
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total Líquido (Filtro Ativo)</span>
                <span style="font-weight: 700; color: #2979FF; font-size: 20px;">{total_soma_formatted}</span>
            </div>
            """, unsafe_allow_html=True)

# ================= TAB 4: ANÁLISE FUNDAMENTALISTA =================
elif selected_tab == "🔍 Análise Fundamentalista":
    st.subheader("🔍 Análise Fundamentalista Histórica")
    st.markdown("Consulte os demonstrativos financeiros históricos (Balanço Patrimonial, DRE e Fluxo de Caixa) das empresas que você possui em carteira.")
    
    if df_holdings.empty:
        st.info("Nenhum ativo em carteira para realizar a análise fundamentalista.")
    else:
        # Filtra apenas ativos elegíveis
        from analytics import is_valid_yfinance_ticker
        ativos_elegiveis = []
        for ticker in sorted(df_holdings["ticker"].unique()):
            tipo_ativo = df_holdings[df_holdings["ticker"] == ticker]["tipo"].iloc[0]
            if is_valid_yfinance_ticker(ticker, tipo_ativo):
                ativos_elegiveis.append(ticker)
                
        if not ativos_elegiveis:
            st.info("Nenhum ativo elegível para análise fundamentalista em carteira.")
        else:
            col_f1, col_f2 = st.columns([1, 1])
            with col_f1:
                ativo_sel = st.selectbox("Escolha um Ativo da sua Carteira:", ativos_elegiveis)
            with col_f2:
                periodo_sel = st.radio("Período dos Demonstrativos:", ["Anual", "Trimestral"], horizontal=True)
                
            # Identifica tipo de ativo e moeda
            tipo_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["tipo"].iloc[0]
            moeda_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["moeda"].iloc[0]
            is_fii = (tipo_ativo_sel == "FIIs" or "FII" in str(ativo_sel).upper())
            
            # Botão de Sincronização
            col_btn_sync, col_status_sync = st.columns([1, 2])
            with col_btn_sync:
                if st.button("🔄 Atualizar Dados do Ativo", help="Busca os demonstrativos mais recentes do Yahoo Finance e atualiza o cache no SQLite."):
                    with st.spinner("Atualizando dados..."):
                        success = sync_fundamental_data_from_yfinance(ativo_sel)
                        if success:
                            st.success("✅ Dados atualizados com sucesso!")
                            st.rerun()
                        else:
                            st.error("❌ Falha ao atualizar dados.")
                            
            st.markdown("---")
            
            if is_fii:
                # Painel Customizado para FIIs
                st.markdown(f"### 🏢 Análise de FII: **{ativo_sel}**")
                st.info("FIIs (Fundos Imobiliários) não possuem demonstrativos contábeis convencionais (DRE e Balanço) públicos estruturados no padrão corporativo convencional. A análise de FIIs é voltada para a distribuição de proventos e indicadores patrimoniais.")
                
                # Exibe proventos recebidos pelo usuário desse FII
                total_recebido = 0.0
                if not df_dividendos.empty and "Ativo" in df_dividendos.columns:
                    prov_fii = df_dividendos[df_dividendos["Ativo"] == ativo_sel]
                    total_recebido = prov_fii["Valor"].sum() if not prov_fii.empty else 0.0
                    
                col_met1, col_met2 = st.columns(2)
                with col_met1:
                    st.metric("Total de Proventos Recebidos por Você", format_number(total_recebido, is_currency=True, currency="BRL"))
                with col_met2:
                    # Posição atual
                    posicao_fii = df_holdings[df_holdings["ticker"] == ativo_sel]
                    if not posicao_fii.empty:
                        qtd_fii = posicao_fii["quantidade"].iloc[0]
                        st.metric("Sua Quantidade Atual", format_number(qtd_fii, decimals=0))
                    else:
                        st.metric("Sua Quantidade Atual", "0")
                
                if not df_dividendos.empty and "Ativo" in df_dividendos.columns:
                    prov_fii = df_dividendos[df_dividendos["Ativo"] == ativo_sel]
                    if not prov_fii.empty:
                        st.markdown("#### 🪙 Histórico de Proventos Recebidos na Planilha")
                        prov_fii_display = prov_fii.sort_values("Recebido em", ascending=False).copy()
                        prov_fii_display["Valor"] = prov_fii_display["Valor"].apply(lambda v: format_number(v, is_currency=True, currency="BRL"))
                        st.dataframe(
                            prov_fii_display[["Recebido em", "Valor"]].rename(columns={"Recebido em": "Data de Recebimento", "Valor": "Valor Pago"}),
                            width='stretch'
                        )
            else:
                # Ações e REITs - Demonstrativos Contábeis
                demo_sel = st.radio(
                    "Demonstrativo para Análise:",
                    ["Balanço Patrimonial", "DRE (Demonstrativo do Resultado)", "Fluxo de Caixa"],
                    horizontal=True
                )
                
                demonstrativo_map = {
                    "Balanço Patrimonial": "balanco",
                    "DRE (Demonstrativo do Resultado)": "dre",
                    "Fluxo de Caixa": "fluxo"
                }
                
                demo_key = demonstrativo_map[demo_sel]
                periodo_key = periodo_sel.lower()
                
                # Busca do banco local SQLite
                df_fundamental = db_manager.get_fundamental_data(ativo_sel, demo_key, periodo_key)
                
                if df_fundamental.empty:
                    st.warning("⚠️ Nenhum dado contábil local encontrado para este ativo. Clique em **Atualizar Dados do Ativo** acima para carregar as informações históricas do Yahoo Finance.")
                else:
                    # Aplica a tradução das contas contábeis
                    df_translated = df_fundamental.copy()
                    df_translated.index = [TERMOS_CONTABEIS.get(str(x), str(x)) for x in df_translated.index]
                    
                    # Remove duplicidades no índice traduzido, se houver
                    df_translated = df_translated[~df_translated.index.duplicated(keep='first')]
                    
                    # Define a ordenação lógica contábil
                    ORDEM_BALANCO = [
                        "Ativo Total", "Ativo Circulante", "Caixa e Equivalentes de Caixa", "Caixa, Equivalentes e Aplicações",
                        "Equivalentes de Caixa", "Caixa Financeiro", "Aplicações Financeiras CP", "Clientes / Contas a Receber",
                        "Contas a Receber", "Outros Contas a Receber", "Estoques", "Matéria-Prima", "Produtos Acabados",
                        "Despesas Antecipadas", "Outros Ativos Circulantes", "Ativo Não Circulante Total", "Ativo Não Circulante",
                        "Imobilizado Líquido", "Ativo Imobilizado Bruto", "Depreciação Acumulada", "Propriedades e Equipamentos",
                        "Terrenos e Benfeitorias", "Máquinas, Móveis e Equipamentos", "Arrendamentos / Leasing",
                        "Ágio e Intangíveis", "Ágio / Goodwill", "Ativos Intangíveis", "Investimentos e Adiantamentos",
                        "Investimentos em Coligadas/Joint Ventures", "Investimentos em Ativos Financeiros",
                        "Ativo Diferido (LP)", "Ativos Fiscais Diferidos (LP)", "Outros Ativos Não Circulantes",
                        "Passivo Total + PL", "Passivo Total", "Passivo Circulante", "Fornecedores / Contas a Pagar",
                        "Contas a Pagar e Despesas Apropriadas", "Outras Contas a Pagar LP", "Dívida de Curto Prazo (CP)",
                        "Empréstimos e Financiamentos CP", "Dívida de Curto Prazo", "Notas Comerciais",
                        "Outras Obrigações Financeiras CP", "Despesas Apropriadas a Pagar (CP)", "Passivo Diferido (CP)",
                        "Receita Diferida / Adiantamentos de Clientes", "Imposto de Renda a Pagar", "Total de Impostos a Pagar",
                        "Outros Passivos Circulantes", "Passivo Não Circulante", "Dívida de Longo Prazo",
                        "Empréstimos e Financiamentos LP", "Outros Passivos Não Circulantes", "Patrimônio Líquido (PL)",
                        "Patrimônio Líquido Ordinário", "Capital Social", "Ações Ordinárias (Capital)", "Lucros Acumulados",
                        "Ações em Tesouraria", "Outros Ajustes do Patrimônio Líquido", "Outros Itens do PL",
                        "Ajustes de Avaliação Patrimonial", "Patrimônio Líquido Total + Participação de Não Controladores"
                    ]
                    
                    ORDEM_DRE = [
                        "Receita Líquida", "Receita Operacional", "Custo da Receita Reconciliado", "Custos dos Serviços/Produtos", "Lucro Bruto",
                        "Despesas Operacionais", "Despesas de Vendas, Gerais e Admin (SG&A)", "Despesas de Vendas, Gerais e Administrativas (SG&A)", "Despesas de Vendas e Marketing",
                        "Despesas Gerais e Administrativas", "Pesquisa e Desenvolvimento (P&D)", "Depreciação e Amortização (D&A)",
                        "Amortização", "Depreciação Reconciliada", "Resultado Operacional (EBIT)", "Resultado Operacional Reportado", "EBITDA", "EBITDA Normalizado", "EBIT", "Resultado Financeiro Líquido",
                        "Receitas Financeiras", "Despesas Financeiras", "Outras Receitas/Despesas Operacionais", "Outras Receitas/Despesas Não Operacionais", "Lucro Antes de Impostos (LAIR)", "Efeito Fiscal de Itens Extraordinários", "Alíquota de Imposto Efetiva", "Impostos e Provisões",
                        "Despesas Totais", "Lucro Líquido Incluindo Não Controladores", "Lucro Líquido", "Lucro Líquido aos Acionistas", "Lucro Líquido Diluído Disponível aos Acionistas", "Lucro Líquido Normalizado", "Lucro Líquido de Operações Continuadas (Controladores)", "Lucro Líquido de Operações Continuadas e Descontinuadas", "Lucro Líquido de Operações Continuadas",
                        "LPA Básico (Lucro por Ação)", "LPA Diluído (Lucro por Ação)", "Média de Ações Básicas", "Média de Ações Diluídas"
                    ]
                    
                    ORDEM_FLUXO = [
                        "Lucro Líquido", "Depreciação, Amortização e Exaustão", "Remuneração Baseada em Ações", "Outros Ajustes Sem Efeito de Caixa", "Variação de Estoques",
                        "Variação de Contas a Receber", "Variação de Fornecedores / Contas a Pagar", "Variação de Contas a Pagar e Despesas Apropriadas", "Variação de Outros Ativos Circulantes", "Variação de Outros Passivos Circulantes",
                        "Variação de Capital de Giro", "Fluxo de Caixa Operacional (FCO)", "FCO - Atividades Operacionais", "Aquisição de Imobilizado (CapEx)", "Compra de Investimentos", "Venda de Investimentos",
                        "Compra e Venda Líquida de Investimentos", "Compra e Venda Líquida de Imobilizado (CapEx Líquido)", "Outras Variações Líquidas de Investimento", "Fluxo de Caixa de Investimentos (FCI)", "FCO - Atividades de Investimento",
                        "Emissão Líquida de Ações", "Pagamento de Ações Ordinárias / Redução de Capital", "Emissão de Dívida / Captação de Recursos", "Amortização de Dívidas", "Emissão de Dívida de Longo Prazo", "Pagamento de Dívida de Longo Prazo", "Pagamento de Dívida de Curto Prazo",
                        "Emissão/Amortização Líquida de Dívida LP", "Emissão/Amortização Líquida de Dívida CP", "Captação/Amortização Líquida de Dívida", "Dividendos em Dinheiro Pagos", "Outros Fluxos Líquidos de Financiamento", "Fluxo de Caixa de Financiamentos (FCF)", "FCO - Atividades de Financiamento",
                        "Imposto de Renda Pago (Dado Suplementar)", "Saldo de Caixa Inicial", "Variação Líquida de Caixa", "Saldo de Caixa Final"
                    ]
                    
                    # Determina a lista de ordenação
                    if demo_key == "balanco":
                        ordem_lista = ORDEM_BALANCO
                    elif demo_key == "dre":
                        ordem_lista = ORDEM_DRE
                    else:
                        ordem_lista = ORDEM_FLUXO
                        
                    # Função para obter a ordem do item
                    def get_sort_index(conta_traduzida):
                        try:
                            return ordem_lista.index(conta_traduzida)
                        except ValueError:
                            return 999
                            
                    # Ordena o DataFrame baseado na lógica contábil
                    df_translated["sort_idx"] = [get_sort_index(idx) for idx in df_translated.index]
                    df_translated = df_translated.sort_values("sort_idx").drop(columns=["sort_idx"])
                    
                    # Formata cada célula numericamente para moeda do ativo
                    for col_date in df_translated.columns:
                        df_translated[col_date] = df_translated[col_date].apply(
                            lambda val: format_number(val, is_currency=True, currency=moeda_ativo_sel, decimals=0)
                        )
                        
                    # Renomeia as colunas de data para visualização limpa (ex: "2025" ou "12/25")
                    new_cols = []
                    for col_date in df_translated.columns:
                        try:
                            yr, mo, dy = col_date.split("-")
                            if periodo_key == "anual":
                                new_cols.append(yr)
                            else:
                                new_cols.append(f"{mo}/{yr[2:]}")
                        except Exception:
                            new_cols.append(str(col_date))
                    df_translated.columns = new_cols
                    
                    st.markdown(f"### 📑 {demo_sel} - {ativo_sel} ({periodo_sel})")
                    
                    if demo_key == "balanco":
                        # Contas do Ativo para divisão das colunas
                        contas_ativo = [
                            "Ativo Total", "Ativo Circulante", "Caixa e Equivalentes de Caixa", "Caixa, Equivalentes e Aplicações",
                            "Equivalentes de Caixa", "Caixa Financeiro", "Aplicações Financeiras CP", "Clientes / Contas a Receber",
                            "Contas a Receber", "Outros Contas a Receber", "Estoques", "Matéria-Prima", "Produtos Acabados",
                            "Despesas Antecipadas", "Outros Ativos Circulantes", "Ativo Não Circulante Total", "Ativo Não Circulante",
                            "Imobilizado Líquido", "Ativo Imobilizado Bruto", "Depreciação Acumulada", "Propriedades e Equipamentos",
                            "Terrenos e Benfeitorias", "Máquinas, Móveis e Equipamentos", "Arrendamentos / Leasing",
                            "Ágio e Intangíveis", "Ágio / Goodwill", "Ativos Intangíveis", "Investimentos e Adiantamentos",
                            "Investimentos em Coligadas/Joint Ventures", "Investimentos em Ativos Financeiros",
                            "Ativo Diferido (LP)", "Ativos Fiscais Diferidos (LP)", "Outros Ativos Não Circulantes"
                        ]
                        
                        df_ativos = df_translated[df_translated.index.isin(contas_ativo)]
                        df_passivos_pl = df_translated[~df_translated.index.isin(contas_ativo)]
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown("#### 🟢 Ativos (Liquidez Decrescente)")
                            st.dataframe(df_ativos, width='stretch')
                        with col_b:
                            st.markdown("#### 🔴 Passivo & PL (Exigibilidade Decrescente)")
                            st.dataframe(df_passivos_pl, width='stretch')
                    else:
                        # Exibe tabela única ordenada para DRE e Fluxo de Caixa
                        st.dataframe(df_translated, width='stretch')

# ================= TAB 5: CONSULTORIA COM IA =================
elif selected_tab == "🤖 Consultoria de Alocação com IA":
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
            relatorio = generate_allocation_tips(df_holdings, df_receitas, df_despesas, df_dividendos, df_orders=df_orders)
            
            st.markdown("---")
            st.markdown("### 📋 Diagnóstico Personalizado do Gemini")
            st.markdown(relatorio)
            st.markdown("---")
