import os
import streamlit as st
import pandas as pd
from src.database import db_manager
from src.services import sync_google_sheets_to_sqlite, sync_fundamental_data_from_yfinance
from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("components", "sidebar")

def render_sidebar(current_page: str, df_holdings=None, df_orders=None, df_perf=None, df_receitas=None, df_despesas=None, df_dividendos=None):
    """
    Renderiza a barra lateral contextualizada especificamente para a página ativa.
    """
    with st.sidebar:
        if current_page == "visao_geral":
            _render_sidebar_visao_geral(df_holdings, df_orders, df_receitas, df_despesas, df_dividendos)
        elif current_page == "desempenho":
            _render_sidebar_desempenho(df_perf)
        elif current_page == "extratos":
            _render_sidebar_extratos(df_receitas, df_despesas, df_dividendos, df_orders)

        elif current_page == "fundamentalista":
            _render_sidebar_fundamentalista(df_holdings)
        elif current_page == "consultoria_ia":
            _render_sidebar_consultoria_ia()
        elif current_page == "importar_gastos":
            _render_sidebar_importar_gastos()
        elif current_page == "configuracoes":
            _render_sidebar_configuracoes()
        else:
            _render_sidebar_default()

def _render_sidebar_visao_geral(df_holdings, df_orders, df_receitas, df_despesas, df_dividendos):
    st.header("📊 Visão Geral")
    st.caption("Filtros interativos e resumo executivo do patrimônio.")

    # 1. Modo Privacidade (Olho Mágico)
    modo_privacidade = st.toggle(
        "👁️ Modo Privacidade",
        value=st.session_state.get("vg_modo_privacidade", False),
        help="Oculte valores em R$ da tela para gravações e apresentações.",
        key="vg_toggle_privacidade"
    )
    st.session_state["vg_modo_privacidade"] = modo_privacidade

    st.markdown("---")
    st.subheader("🎛️ Filtros da Página")

    # 2. Filtro de Mês/Ano (Competência Orçamentária)
    all_months = set()
    if df_receitas is not None and not df_receitas.empty and "Recebido em" in df_receitas.columns:
        dt_r = pd.to_datetime(df_receitas["Recebido em"], errors="coerce").dropna()
        all_months.update(dt_r.dt.strftime("%m/%Y").tolist())
    if df_despesas is not None and not df_despesas.empty and "Gasto em" in df_despesas.columns:
        dt_d = pd.to_datetime(df_despesas["Gasto em"], errors="coerce").dropna()
        all_months.update(dt_d.dt.strftime("%m/%Y").tolist())
    if df_dividendos is not None and not df_dividendos.empty and "Recebido em" in df_dividendos.columns:
        dt_div = pd.to_datetime(df_dividendos["Recebido em"], errors="coerce").dropna()
        all_months.update(dt_div.dt.strftime("%m/%Y").tolist())

    sorted_months = sorted(list(all_months), key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
    month_options = ["Mais Recente (Automático)"] + sorted_months

    selected_month = st.selectbox(
        "🗓️ Competência (Mês/Ano):",
        options=month_options,
        index=0,
        help="Selecione o mês para analisar a poupança e o fluxo de caixa.",
        key="vg_select_mes_ano"
    )
    st.session_state["vg_filtro_mes_ano"] = selected_month

    # 3. Filtro por Classe de Ativos
    classes_disponiveis = []
    if df_holdings is not None and not df_holdings.empty and "tipo" in df_holdings.columns:
        classes_disponiveis = sorted(df_holdings["tipo"].dropna().unique().tolist())

    if classes_disponiveis:
        selected_classes = st.multiselect(
            "📈 Classes de Ativos:",
            options=classes_disponiveis,
            default=classes_disponiveis,
            help="Filtre os ativos exibidos nos gráficos e totalizadores de custódia.",
            key="vg_multiselect_classes"
        )
        st.session_state["vg_classes_selecionadas"] = selected_classes
    else:
        st.session_state["vg_classes_selecionadas"] = []

    # 4. Filtro de Gastos Essenciais vs Não Essenciais
    filtro_essencial = st.selectbox(
        "🏷️ Essencialidade de Gastos:",
        options=["Todos os Gastos", "Apenas Essenciais", "Apenas Não Essenciais"],
        index=0,
        key="vg_select_essencial"
    )
    st.session_state["vg_essencial_filtro"] = filtro_essencial

    st.markdown("---")

    # Resumo Patrimonial na Sidebar (respeitando privacidade e classes)
    if df_holdings is not None and not df_holdings.empty:
        active_classes = st.session_state.get("vg_classes_selecionadas", classes_disponiveis)
        df_h_filtered = df_holdings[df_holdings["tipo"].isin(active_classes)] if active_classes else df_holdings

        total_market = df_h_filtered["valor_atual"].sum()
        total_investido = df_h_filtered["total_investido"].sum() if "total_investido" in df_h_filtered.columns else 0.0
        lucro = total_market - total_investido
        retorno_pct = (lucro / total_investido * 100.0) if total_investido > 0 else 0.0

        st.subheader("💼 Resumo da Carteira")
        st.metric("Patrimônio Filtrado", format_number(total_market, is_currency=True, currency="BRL", mask_privacy=modo_privacidade))
        st.metric(
            "Lucro / Prejuízo",
            format_number(lucro, is_currency=True, currency="BRL", mask_privacy=modo_privacidade),
            delta=f"{retorno_pct:.2f}%" if not modo_privacidade else "•••%"
        )
        st.metric("Ativos em Exibição", len(df_h_filtered))

    st.markdown("---")
    st.subheader("🔄 Sincronização Rápida")
    last_sync = db_manager.get_last_sync_time()
    st.caption(f"🕒 Última sinc: **{last_sync if last_sync else 'Nunca'}**")
    
    if st.button("🔄 Sincronizar Sheets", use_container_width=True, type="primary"):
        with st.spinner("Atualizando dados do Google Sheets..."):
            try:
                sync_google_sheets_to_sqlite()
                st.cache_data.clear()
                st.success("✅ Atualizado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")


def _render_sidebar_desempenho(df_perf):
    st.header("📈 Desempenho")
    st.caption("Filtros e métricas da curva de rentabilidade ponderada pelo tempo (TWR).")

    # 1. Seletor de Período Temporal
    periodos = ["Desde o início", "Últimos 12 meses", "Últimos 6 meses", "Último mês"]
    current_period = st.session_state.get("perf_periodo", "Desde o início")
    default_p_idx = periodos.index(current_period) if current_period in periodos else 0

    selected_period = st.selectbox(
        "🗓️ Período de Análise:",
        options=periodos,
        index=default_p_idx,
        help="Filtre a janela de tempo da evolução patrimonial.",
        key="perf_select_periodo"
    )
    st.session_state["perf_periodo"] = selected_period

    # 2. Seletor de Benchmarks para Comparar (Multi-select)
    benchmarks_disponiveis = [
        "CDI",
        "IPCA (Inflação)",
        "IPCA + 6%",
        "Ibovespa",
        "S&P 500"
    ]
    current_selected_bench = st.session_state.get("perf_benchmarks_selecionados", benchmarks_disponiveis)

    selected_benchmarks = st.multiselect(
        "📊 Benchmarks Visíveis:",
        options=benchmarks_disponiveis,
        default=current_selected_bench,
        help="Ligue ou desligue curvas de comparação específicas no gráfico.",
        key="perf_multiselect_benchmarks"
    )
    st.session_state["perf_benchmarks_selecionados"] = selected_benchmarks

    st.markdown("---")

    # 3. Monitoramento da API do Banco Central (BCB) com Alerta e Botão de Retry
    cdi_status = st.session_state.get("bcb_cdi_status", "OK")
    ipca_status = st.session_state.get("bcb_ipca_status", "OK")
    has_bcb_issue = ("TIMEOUT" in str(cdi_status) or "TIMEOUT" in str(ipca_status))

    st.subheader("🏦 API Banco Central (BCB)")
    if has_bcb_issue:
        st.warning("⚠️ **Aviso de Conexão:** A API do Banco Central sofreu timeout e está exibindo valores com taxa estimada. Clique abaixo para tentar novamente.")
    else:
        st.caption("🟢 Séries do SGS/BCB sincronizadas.")

    if st.button("🔄 Atualizar CDI/IPCA (BCB)", use_container_width=True, type="primary" if has_bcb_issue else "secondary"):
        with st.spinner("Limpando cache e consultando API do Banco Central..."):
            try:
                from src.services import clear_bcb_cache
                clear_bcb_cache()
                st.success("✅ Cache limpo! Recarregando dados oficiais...")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar: {e}")

    st.markdown("---")

    if df_perf is not None and not df_perf.empty:
        st.subheader("⚡ Resumo da Carteira")
        col_ret = [c for c in df_perf.columns if "Retorno Carteira" in c]
        if col_ret:
            ret_total = df_perf[col_ret[0]].iloc[-1]
            st.metric("Rentabilidade Histórica Acumulada", f"{ret_total:.2f}%")


def _render_sidebar_extratos(df_receitas, df_despesas, df_dividendos, df_orders):
    current_subtab = st.query_params.get("subtab", "receitas")
    
    st.header("📑 Extratos")
    
    # 1. Modo Privacidade para os Extratos
    modo_privacidade = st.toggle(
        "👁️ Modo Privacidade",
        value=st.session_state.get("ext_modo_privacidade", False),
        help="Oculte valores em R$ da tabela e dos totalizadores.",
        key="ext_toggle_privacidade"
    )
    st.session_state["ext_modo_privacidade"] = modo_privacidade
    st.markdown("---")

    # ==========================================
    # FILTROS PARA SUBABA: RECEITAS
    # ==========================================
    if current_subtab == "receitas":
        st.subheader("🪙 Filtros: Receitas")
        
        # Filtra para obter apenas receitas não-patrimoniais
        df_rec_base = df_receitas.copy() if df_receitas is not None else pd.DataFrame()
        if not df_rec_base.empty and "Categoria" in df_rec_base.columns:
            from src.tabs.extratos import CATEGORIAS_PROVENTOS
            df_rec_base = df_rec_base[~df_rec_base["Categoria"].isin(CATEGORIAS_PROVENTOS)]
            
        busca_rec = st.text_input("🔍 Buscar Lançamento:", value=st.session_state.get("ext_rec_busca", ""), key="ext_rec_input_busca")
        st.session_state["ext_rec_busca"] = busca_rec

        cat_opcoes = ["Todas"]
        if not df_rec_base.empty and "Categoria" in df_rec_base.columns:
            cat_opcoes += sorted(df_rec_base["Categoria"].dropna().unique().tolist())
        cat_sel = st.selectbox("🏷️ Categoria:", options=cat_opcoes, key="ext_rec_select_cat")
        st.session_state["ext_rec_cat"] = cat_sel

        mes_opcoes = ["Todos"]
        if not df_rec_base.empty and "Recebido em" in df_rec_base.columns:
            dt_r = pd.to_datetime(df_rec_base["Recebido em"], errors="coerce").dropna()
            m_sorted = sorted(dt_r.dt.strftime("%m/%Y").unique().tolist(), key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
            mes_opcoes += m_sorted
        mes_sel = st.selectbox("🗓️ Mês/Ano:", options=mes_opcoes, key="ext_rec_select_mes")
        st.session_state["ext_rec_mes"] = mes_sel

    # ==========================================
    # FILTROS PARA SUBABA: DESPESAS
    # ==========================================
    elif current_subtab == "despesas":
        st.subheader("💸 Filtros: Despesas")
        df_desp_base = df_despesas.copy() if df_despesas is not None else pd.DataFrame()

        busca_desp = st.text_input("🔍 Buscar Lançamento:", value=st.session_state.get("ext_desp_busca", ""), key="ext_desp_input_busca")
        st.session_state["ext_desp_busca"] = busca_desp

        cat_opcoes = ["Todas"]
        if not df_desp_base.empty and "Categoria" in df_desp_base.columns:
            cat_opcoes += sorted(df_desp_base["Categoria"].dropna().unique().tolist())
        cat_sel = st.selectbox("🏷️ Categoria:", options=cat_opcoes, key="ext_desp_select_cat")
        st.session_state["ext_desp_cat"] = cat_sel

        fixo_opcoes = ["Todos"]
        if not df_desp_base.empty and "Fixo vs. Variável" in df_desp_base.columns:
            fixo_opcoes += sorted(df_desp_base["Fixo vs. Variável"].dropna().unique().tolist())
        fixo_sel = st.selectbox("⚙️ Fixo vs. Variável:", options=fixo_opcoes, key="ext_desp_select_fixo")
        st.session_state["ext_desp_fixo"] = fixo_sel

        essencial_opcoes = ["Todos"]
        if not df_desp_base.empty and "Essencial vs. Não Essencial" in df_desp_base.columns:
            essencial_opcoes += sorted(df_desp_base["Essencial vs. Não Essencial"].dropna().unique().tolist())
        ess_sel = st.selectbox("🎯 Essencial vs. Não Essencial:", options=essencial_opcoes, key="ext_desp_select_ess")
        st.session_state["ext_desp_ess"] = ess_sel

        mes_opcoes = ["Todos"]
        if not df_desp_base.empty and "Gasto em" in df_desp_base.columns:
            dt_d = pd.to_datetime(df_desp_base["Gasto em"], errors="coerce").dropna()
            m_sorted = sorted(dt_d.dt.strftime("%m/%Y").unique().tolist(), key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
            mes_opcoes += m_sorted
        mes_sel = st.selectbox("🗓️ Mês/Ano:", options=mes_opcoes, key="ext_desp_select_mes")
        st.session_state["ext_desp_mes"] = mes_sel

    # ==========================================
    # FILTROS PARA SUBABA: DIVIDENDOS
    # ==========================================
    elif current_subtab == "dividendos":
        st.subheader("📈 Filtros: Proventos")
        df_div_base = df_dividendos.copy() if df_dividendos is not None else pd.DataFrame()
        col_ativo = "Ativo" if "Ativo" in df_div_base.columns else ("Nome" if "Nome" in df_div_base.columns else None)

        ativo_opcoes = ["Todos"]
        if not df_div_base.empty and col_ativo:
            ativo_opcoes += sorted(df_div_base[col_ativo].dropna().unique().tolist())
        ativo_sel = st.selectbox("🏢 Ativo / Ticker:", options=ativo_opcoes, key="ext_div_select_ativo")
        st.session_state["ext_div_ativo"] = ativo_sel

        cat_opcoes = ["Todas"]
        if not df_div_base.empty and "Categoria" in df_div_base.columns:
            cat_opcoes += sorted(df_div_base["Categoria"].dropna().unique().tolist())
        cat_sel = st.selectbox("🏷️ Tipo de Provento:", options=cat_opcoes, key="ext_div_select_cat")
        st.session_state["ext_div_cat"] = cat_sel

        mes_opcoes = ["Todos"]
        if not df_div_base.empty and "Recebido em" in df_div_base.columns:
            dt_div = pd.to_datetime(df_div_base["Recebido em"], errors="coerce").dropna()
            m_sorted = sorted(dt_div.dt.strftime("%m/%Y").unique().tolist(), key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
            mes_opcoes += m_sorted
        mes_sel = st.selectbox("🗓️ Mês/Ano:", options=mes_opcoes, key="ext_div_select_mes")
        st.session_state["ext_div_mes"] = mes_sel

    # ==========================================
    # FILTROS PARA SUBABA: ORDENS
    # ==========================================
    elif current_subtab == "ordens":
        st.subheader("📊 Filtros: Ordens")
        df_ord_base = df_orders.copy() if df_orders is not None else pd.DataFrame()

        ativo_opcoes = ["Todos"]
        if not df_ord_base.empty and "Papel" in df_ord_base.columns:
            ativo_opcoes += sorted(df_ord_base["Papel"].dropna().unique().tolist())
        ativo_sel = st.selectbox("🏢 Papel / Ticker:", options=ativo_opcoes, key="ext_ord_select_ativo")
        st.session_state["ext_ord_ativo"] = ativo_sel

        acao_opcoes = ["Todos"]
        if not df_ord_base.empty and "Compra/Venda" in df_ord_base.columns:
            acao_opcoes += sorted(df_ord_base["Compra/Venda"].dropna().unique().tolist())
        acao_sel = st.selectbox("🔄 Operação:", options=acao_opcoes, key="ext_ord_select_acao")
        st.session_state["ext_ord_acao"] = acao_sel

        tipo_opcoes = ["Todos"]
        if not df_ord_base.empty and "Tipo" in df_ord_base.columns:
            tipo_opcoes += sorted(df_ord_base["Tipo"].dropna().unique().tolist())
        tipo_sel = st.selectbox("📈 Tipo de Ativo:", options=tipo_opcoes, key="ext_ord_select_tipo")
        st.session_state["ext_ord_tipo"] = tipo_sel

        setor_opcoes = ["Todos"]
        if not df_ord_base.empty and "Setor Econômico" in df_ord_base.columns:
            setor_opcoes += sorted(df_ord_base["Setor Econômico"].dropna().unique().tolist())
        setor_sel = st.selectbox("🏭 Setor Econômico:", options=setor_opcoes, key="ext_ord_select_setor")
        st.session_state["ext_ord_setor"] = setor_sel

        mes_opcoes = ["Todos"]
        if not df_ord_base.empty and "data envio" in df_ord_base.columns:
            dt_ord = pd.to_datetime(df_ord_base["data envio"], errors="coerce").dropna()
            m_sorted = sorted(dt_ord.dt.strftime("%m/%Y").unique().tolist(), key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
            mes_opcoes += m_sorted
        mes_sel = st.selectbox("🗓️ Mês/Ano:", options=mes_opcoes, key="ext_ord_select_mes")
        st.session_state["ext_ord_mes"] = mes_sel


def _render_sidebar_fundamentalista(df_holdings):
    st.header("🔍 Fundamentalista")
    st.caption("Demonstrativos e indicadores das empresas da carteira.")

    if df_holdings is None or df_holdings.empty:
        st.info("Nenhum ativo em carteira.")
        return

    # Extrai ativos elegíveis para análise fundamentalista
    from src.services import is_valid_yfinance_ticker, sync_fundamental_data_from_yfinance
    ativos_elegiveis = []
    for ticker in sorted(df_holdings["ticker"].unique()):
        tipo_ativo = df_holdings[df_holdings["ticker"] == ticker]["tipo"].iloc[0]
        if is_valid_yfinance_ticker(ticker, tipo_ativo):
            ativos_elegiveis.append(ticker)

    if not ativos_elegiveis:
        st.info("Nenhum ativo elegível para análise contábil.")
        return

    st.subheader("🏢 Seleção de Ativo")
    current_ativo = st.session_state.get("fund_ativo_sel", ativos_elegiveis[0])
    default_ativo_idx = ativos_elegiveis.index(current_ativo) if current_ativo in ativos_elegiveis else 0

    ativo_sel = st.selectbox(
        "Escolha um Ativo da Carteira:",
        options=ativos_elegiveis,
        index=default_ativo_idx,
        key="fund_select_ativo"
    )
    st.session_state["fund_ativo_sel"] = ativo_sel

    tipo_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["tipo"].iloc[0]
    is_fii = (tipo_ativo_sel == "FIIs" or "FII" in str(ativo_sel).upper())

    if not is_fii:
        st.subheader("📅 Periodicidade")
        periodos = ["Anual", "Trimestral"]
        current_periodo = st.session_state.get("fund_periodo_sel", "Anual")
        default_per_idx = periodos.index(current_periodo) if current_periodo in periodos else 0

        periodo_sel = st.radio(
            "Período dos Demonstrativos:",
            options=periodos,
            index=default_per_idx,
            horizontal=True,
            key="fund_radio_periodo"
        )
        st.session_state["fund_periodo_sel"] = periodo_sel

    st.markdown("---")
    st.subheader("🔄 Atualização de Dados")

    if st.button(f"🔄 Atualizar {ativo_sel}", use_container_width=True, type="primary"):
        with st.spinner(f"Buscando demonstrativos mais recentes de {ativo_sel} no Yahoo Finance..."):
            try:
                success = sync_fundamental_data_from_yfinance(ativo_sel)
                if success:
                    st.success(f"✅ Dados de {ativo_sel} atualizados!")
                    st.rerun()
                else:
                    st.error("❌ Falha ao atualizar dados.")
            except Exception as e:
                st.error(f"Erro: {e}")

    if st.button("📊 Sincronizar Todos os Ativos", use_container_width=True):
        with st.spinner("Buscando dados contábeis em lote no Yahoo Finance..."):
            try:
                res = sync_fundamental_data_from_yfinance()
                if res:
                    st.success("✅ Demonstrativos atualizados!")
                    st.rerun()
                else:
                    st.warning("⚠️ Nenhum ticker elegível.")
            except Exception as e:
                st.error(f"Erro: {e}")


def _render_sidebar_consultoria_ia():
    st.header("🤖 Consultoria IA")
    st.caption("Recomendações e diagnósticos de alocação via Google Gemini.")

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        st.success("🟢 Gemini API Ativa")
    else:
        st.warning("🟡 Gemini API Não Configurada")
        st.caption("Configure sua chave em `⚙️ Configurações` ou no `.env`.")

    st.markdown("---")
    st.info("💡 **Como a IA analisa:** O modelo Gemini 1.5 Flash combina a posição atual de custódia com seu histórico orçamentário para sugerir aportes inteligentes.")

def _render_sidebar_importar_gastos():
    st.header("📥 Importação")
    st.caption("Ingestão de dados e conciliação inteligente.")

    # Exibe badge de itens em staging se houver
    df_staging = st.session_state.get("df_staging_transactions", pd.DataFrame())
    qtd_staging = len(df_staging) if df_staging is not None else 0

    if qtd_staging > 0:
        st.warning(f"⚠️ **{qtd_staging} transação(ões)** aguardando conciliação.")
        if st.button("🗑️ Descartar Fila de Revisão", use_container_width=True):
            st.session_state.df_staging_transactions = pd.DataFrame()
            st.success("Fila de revisão limpa!")
            st.rerun()
    else:
        st.info("✨ Nenhuma transação pendente na fila.")

    st.markdown("---")
    st.subheader("📌 Métodos Suportados")
    st.markdown("- 📸 OCR de Prints e Comprovantes (IA)\n- 📄 Extratos Bancários (.OFX / .CSV)\n- 🏦 Open Finance (Pluggy)")

def _render_sidebar_configuracoes():
    st.header("⚙️ Configurações")
    st.caption("Painel central de conexões, credenciais e integrações da aplicação.")
    st.markdown("---")
    st.markdown("Use esta página para alternar entre fontes de dados, atualizar chaves de API e testar a saúde da infraestrutura.")

def _render_sidebar_default():
    st.header("⚙️ Painel de Controle")
    st.caption("Paulo Investimentos Pessoais")
