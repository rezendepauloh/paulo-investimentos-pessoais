import streamlit as st

PAGES_CONFIG = [
    {"id": "visao_geral", "label": "📊 Visão Geral e Orçamento"},
    {"id": "desempenho", "label": "📈 Desempenho e Benchmarks"},
    {"id": "extratos", "label": "📑 Extratos e Lançamentos"},
    {"id": "fundamentalista", "label": "🔍 Análise Fundamentalista"},
    {"id": "consultoria_ia", "label": "🤖 Consultoria de Alocação com IA"}
]

def render_header():
    """
    Renderiza o cabeçalho superior com título e menu popover estilo drawer suspenso.
    Retorna o ID da página atualmente selecionada.
    """
    if "current_page" not in st.session_state:
        st.session_state.current_page = "visao_geral"

    header_col1, header_col2 = st.columns([8.2, 1.8], vertical_alignment="center")

    with header_col1:
        st.markdown("""
        <div class="dashboard-header-left">
            <h1 class="dashboard-title">📈 Gestão Patrimonial Inteligente</h1>
            <p class="dashboard-subtitle">Consolidação automática de investimentos, fluxo de caixa e consultoria personalizada por IA.</p>
        </div>
        """, unsafe_allow_html=True)

    with header_col2:
        with st.popover("☰ Menu", use_container_width=True):
            st.markdown('<div class="menu-popover-title">📌 Sistemas / Páginas</div>', unsafe_allow_html=True)
            for page in PAGES_CONFIG:
                is_active = (st.session_state.current_page == page["id"])
                btn_type = "primary" if is_active else "secondary"
                if st.button(page["label"], key=f"nav_btn_{page['id']}", use_container_width=True, type=btn_type):
                    st.session_state.current_page = page["id"]
                    st.rerun()

    st.markdown("<div class='header-divider'></div>", unsafe_allow_html=True)
    return st.session_state.current_page
