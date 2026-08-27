import streamlit as st
from src.utils.logger import get_logger

logger = get_logger("components", "header")


PAGES_CONFIG = [
    {"id": "visao_geral", "label": "📊 Visão Geral e Orçamento"},
    {"id": "desempenho", "label": "📈 Desempenho e Benchmarks"},
    {"id": "extratos", "label": "📑 Extratos e Lançamentos"},
    {"id": "fundamentalista", "label": "🔍 Análise Fundamentalista"},
    {"id": "consultoria_ia", "label": "🤖 Consultoria de Alocação com IA"},
    {"id": "importar_gastos", "label": "📥 Importação de Dados para GSheets"},
    {"id": "configuracoes", "label": "⚙️ Configurações do Sistema"}
]

PAGE_TO_SLUG = {
    "visao_geral": "visao_geral",
    "desempenho": "desempenho",
    "extratos": "extratos",
    "fundamentalista": "fundamentalista",
    "consultoria_ia": "consultoria_ia",
    "importar_gastos": "importar_gastos",
    "configuracoes": "configuracoes"
}

PAGE_HEADER_INFO = {
    "visao_geral": {
        "title": "📊 Visão Geral do Patrimônio & Orçamento",
        "subtitle": "Consolidação automática de investimentos, patrimônio líquido, distribuição de ativos e fluxo de caixa mensal."
    },
    "desempenho": {
        "title": "📈 Desempenho Histórico & Benchmarks",
        "subtitle": "Evolução da rentabilidade ponderada no tempo (TWR) e comparação com CDI, IPCA, Ibovespa e S&P 500."
    },
    "extratos": {
        "title": "📑 Extratos Detalhados & Histórico de Ordens",
        "subtitle": "Consulta granular e filtragem avançada de receitas, despesas, dividendos e operações de compra e venda."
    },
    "fundamentalista": {
        "title": "🔍 Análise Fundamentalista & Demonstrativos",
        "subtitle": "Consulta histórica de Balanço Patrimonial, DRE e Fluxo de Caixa para ações e análise de proventos para FIIs."
    },
    "consultoria_ia": {
        "title": "🤖 Consultoria Estratégica com Inteligência Artificial",
        "subtitle": "Diagnóstico inteligente de risco, diversificação de carteira e sugestões de rebalanceamento por IA."
    },
    "importar_gastos": {
        "title": "📥 Ingestão Inteligente & Conciliação de Gastos",
        "subtitle": "Importação híbrida de comprovantes/faturas (OCR Gemini Vision), extratos (.OFX / .CSV) e Open Finance."
    },
    "configuracoes": {
        "title": "⚙️ Configurações do Sistema & Conexões",
        "subtitle": "Gerenciamento de credenciais, fontes de dados, sincronizações de planilhas e diagnósticos da aplicação."
    }
}

SLUG_TO_PAGE = {v: k for k, v in PAGE_TO_SLUG.items()}

def render_header():
    """
    Renderiza o cabeçalho superior com título dinâmico e menu popover estilo drawer suspenso.
    Sincroniza o estado da página ativa com os Query Parameters da URL (?tab=slug).
    Retorna o ID da página atualmente selecionada.
    """
    # 1. Sincroniza estado inicial a partir do GET parameter na URL (?tab=slug)
    url_tab = st.query_params.get("tab")
    if url_tab and url_tab in SLUG_TO_PAGE:
        st.session_state.current_page = SLUG_TO_PAGE[url_tab]
    elif "current_page" not in st.session_state:
        st.session_state.current_page = "visao_geral"

    # Garante que a URL reflita o slug da página atual
    current_slug = PAGE_TO_SLUG.get(st.session_state.current_page, "visao_geral")
    if st.query_params.get("tab") != current_slug:
        st.query_params["tab"] = current_slug

    def set_page(page_id: str):
        st.session_state.current_page = page_id
        st.query_params["tab"] = PAGE_TO_SLUG.get(page_id, "visao_geral")
        # Limpa subtab anterior ao trocar de página se não aplicável
        if "subtab" in st.query_params:
            del st.query_params["subtab"]
        logger.info(f"Navegação: Usuário acessou a página '{page_id}'")
        st.rerun()

    header_info = PAGE_HEADER_INFO.get(st.session_state.current_page, PAGE_HEADER_INFO["visao_geral"])

    header_col1, header_col2 = st.columns([8.2, 1.8], vertical_alignment="center")

    with header_col1:
        st.markdown(f"""
        <div class="dashboard-header-left">
            <h1 class="dashboard-title">{header_info['title']}</h1>
            <p class="dashboard-subtitle">{header_info['subtitle']}</p>
        </div>
        """, unsafe_allow_html=True)


    with header_col2:
        with st.popover("☰ Menu", use_container_width=True):
            st.markdown('<div class="menu-popover-title">📌 Sistemas / Páginas</div>', unsafe_allow_html=True)
            for page in PAGES_CONFIG:
                is_active = (st.session_state.current_page == page["id"])
                btn_type = "primary" if is_active else "secondary"
                if st.button(page["label"], key=f"nav_btn_{page['id']}", use_container_width=True, type=btn_type):
                    set_page(page["id"])

    st.markdown("<div class='header-divider'></div>", unsafe_allow_html=True)
    return st.session_state.current_page

