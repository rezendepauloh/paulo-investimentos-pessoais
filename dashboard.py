import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from src.utils.logger import get_logger

logger = get_logger("app", "dashboard")
logger.info("🚀 Inicializando painel Paulo - Finanças & Investimentos...")


# Carrega variáveis de ambiente
load_dotenv()

# Configuração da página Streamlit
st.set_page_config(
    page_title="Paulo - Finanças & Investimentos",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Carregamento de CSS customizado modular
def load_css():
    css_file = os.path.join(os.path.dirname(__file__), "assets", "css", "styles.css")
    if os.path.exists(css_file):
        with open(css_file, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# Importações de componentes e abas modulares
from src.components import render_header, render_sidebar
from src.tabs import (
    render_tab_visao_geral,
    render_tab_desempenho,
    render_tab_extratos,
    render_tab_fundamentalista,
    render_tab_consultoria_ia,
    render_tab_importar_gastos,
    render_tab_editor_planilhas,
    render_tab_configuracoes
)
from src.services import (
    get_budget_data,
    get_orders_data,
    calculate_portfolio_holdings,
    get_historical_performance
)

# Renderiza Header e obtém página ativa
current_page = render_header()

# Inicializa estado de dados mock se ainda não configurado
if "use_mock" not in st.session_state:
    st.session_state.use_mock = False

use_mock = st.session_state.use_mock

# Carga de Dados (com fallback inteligente)
if use_mock:
    df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=True)
    df_orders = get_orders_data(use_mock=True)
else:
    try:
        df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=False)
        df_orders = get_orders_data(use_mock=False)
        
        if df_receitas.empty and df_despesas.empty and df_orders.empty:
            st.info("ℹ️ Nenhuma planilha foi carregada. Verifique o `.env` e credenciais. Carregando modo de demonstração como fallback...")
            df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=True)
            df_orders = get_orders_data(use_mock=True)
            use_mock = True
    except Exception as e:
        st.error(f"Erro ao conectar com as planilhas reais: {e}")
        st.info("Carregando modo de demonstração como fallback para testes...")
        df_receitas, df_despesas, df_dividendos = get_budget_data(use_mock=True)
        df_orders = get_orders_data(use_mock=True)
        use_mock = True

# -----------------------------------------------------------------------------
# CÁLCULO DE CARTEIRA E PERFORMANCE (ASSÍNCRONO & SOB DEMANDA)
# -----------------------------------------------------------------------------
df_holdings = pd.DataFrame()
df_perf = pd.DataFrame()

if not df_orders.empty:
    # 1. Holdings da Carteira (em session_state para não recalcular a cada troca de aba ou filtro)
    if "df_holdings" in st.session_state and not st.session_state["df_holdings"].empty:
        df_holdings = st.session_state["df_holdings"]
    else:
        try:
            df_holdings = calculate_portfolio_holdings(df_orders)
            st.session_state["df_holdings"] = df_holdings
        except Exception as e:
            logger.error(f"Erro ao calcular posições da carteira: {e}")
            df_holdings = pd.DataFrame()

    # 2. Performance Histórica (TWR diário + benchmarks BCB/Yahoo):
    # Se o usuário estiver na aba Desempenho ou ela já estiver em cache, calcula/recupera;
    # Caso contrário, dispara em background thread para não travar a abertura inicial do painel.
    is_desempenho_page = (current_page in ["desempenho", "📈 Desempenho e Benchmarks"])
    
    from src.services.async_tasks import (
        start_background_task,
        is_task_running,
        get_task_result
    )

    perf_result = get_task_result("calculo_performance")
    if perf_result is not None and not perf_result.empty:
        df_perf = perf_result
    elif is_desempenho_page:
        # Se o usuário estiver na própria aba de desempenho, executa e armazena
        with st.spinner("Reconstruindo série histórica de rentabilidade diária (TWR)..."):
            try:
                df_perf = get_historical_performance(df_orders)
            except Exception as e:
                logger.error(f"Erro ao calcular performance: {e}")
                df_perf = pd.DataFrame()
    else:
        # Pré-carrega em background thread sem bloquear a navegação
        start_background_task(
            "calculo_performance",
            get_historical_performance,
            args=(df_orders,),
            task_label="Cálculo da Série Temporal e Benchmarks"
        )

# Renderiza Accordion de Tarefas Assíncronas se houver processamento em segundo plano
from src.components.status_banner import render_async_task_expander
render_async_task_expander(
    "calculo_performance",
    title="🤖 Reconstrução de Rentabilidade & Benchmarks em Segundo Plano",
    info_text="O cálculo da série histórica de 10 anos e consulta ao Banco Central está rodando em segundo plano. Você pode continuar usando o painel livremente!"
)
render_async_task_expander(
    "sync_sheets_background",
    title="🔄 Sincronização do Google Sheets em Segundo Plano",
    info_text="Os dados das planilhas estão sendo atualizados no SQLite em segundo plano. O painel permanece desbloqueado!"
)

# Renderiza Sidebar Contextual da Página Ativa
render_sidebar(
    current_page,
    df_holdings=df_holdings,
    df_orders=df_orders,
    df_perf=df_perf,
    df_receitas=df_receitas,
    df_despesas=df_despesas,
    df_dividendos=df_dividendos
)


# Roteamento modular das Abas/Páginas
if current_page == "visao_geral" or current_page == "📊 Visão Geral e Orçamento":
    render_tab_visao_geral(df_holdings, df_orders, df_receitas, df_despesas, df_dividendos)
elif current_page == "desempenho" or current_page == "📈 Desempenho e Benchmarks":
    render_tab_desempenho(df_perf)
elif current_page == "extratos" or current_page == "📑 Extratos e Lançamentos":
    render_tab_extratos(df_receitas, df_despesas, df_dividendos, df_orders)
elif current_page == "fundamentalista" or current_page == "🔍 Análise Fundamentalista":
    render_tab_fundamentalista(df_holdings, df_dividendos)
elif current_page == "consultoria_ia" or current_page == "🤖 Consultoria de Alocação com IA":
    render_tab_consultoria_ia(df_holdings, df_receitas, df_despesas, df_dividendos, df_orders)
elif current_page == "importar_gastos" or current_page == "📥 Importação de Dados para GSheets":
    render_tab_importar_gastos(df_receitas, df_despesas)
elif current_page == "editor_planilhas" or current_page == "📝 Editor de Planilhas":
    render_tab_editor_planilhas()
elif current_page == "configuracoes" or current_page == "⚙️ Configurações do Sistema":
    render_tab_configuracoes()

