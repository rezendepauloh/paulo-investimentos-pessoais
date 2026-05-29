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
from data_loader import get_budget_data, get_orders_data, sync_google_sheets_to_sqlite
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
        st.subheader("🔄 Sincronização Local")
        
        last_sync = db_manager.get_last_sync_time()
        st.info(f"Última sincronização:\n**{last_sync}**")
        
        if st.button("🔄 Sincronizar Google Sheets", use_container_width=True, help="Baixa lançamentos e ordens mais recentes do Sheets de forma incremental e atualiza o SQLite local."):
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
        total_invested = df_holdings["total_investido"].sum()
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
            st.plotly_chart(fig_sunburst, use_container_width=True)
            
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
                st.plotly_chart(fig_desp_sun, use_container_width=True)
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
                    st.plotly_chart(fig_cv_sunburst, use_container_width=True)
                    
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
            # Filtros para Despesas
            col_filter1, col_filter2, col_filter3 = st.columns(3)
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
            
            df_despesas_filtered = df_despesas.copy()
            if cat_despesa_sel != "Todas":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Categoria"] == cat_despesa_sel]
            if "Fixo vs. Variável" in df_despesas_filtered.columns and fixo_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Fixo vs. Variável"] == fixo_sel]
            if "Essencial vs. Não Essencial" in df_despesas_filtered.columns and essencial_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Essencial vs. Não Essencial"] == essencial_sel]
                
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
