import streamlit as st
import pandas as pd
from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("tabs", "extratos")


SUBTABS_EXTRATOS = {
    "receitas": "🪙 Receitas",
    "despesas": "💸 Despesas",
    "dividendos": "📈 Dividendos",
    "ordens": "📊 Ordens de Compra/Venda"
}
SLUG_TO_LABEL_EXTRATOS = SUBTABS_EXTRATOS
LABEL_TO_SLUG_EXTRATOS = {v: k for k, v in SUBTABS_EXTRATOS.items()}

CATEGORIAS_PROVENTOS = [
    "Dividendo BR",
    "Dividendo EUA",
    "Rendimento FII",
    "Aluguel Ações BR",
    "Aluguel Ações EUA",
    "Juros sobre Capital Próprio",
    "Rendimento Renda Fixa",
    "Frações"
]

def render_tab_extratos(df_receitas, df_despesas, df_dividendos, df_orders):
    """
    Renderiza a aba de Extratos e Lançamentos detalhados (Receitas, Despesas, Dividendos e Ordens).
    """
    st.subheader("📑 Visualização dos Lançamentos e Histórico de Transações")
    
    # Sincroniza subtab com a URL (?subtab=slug)
    url_subtab = st.query_params.get("subtab", "receitas")
    if url_subtab not in SLUG_TO_LABEL_EXTRATOS:
        url_subtab = "receitas"
        
    current_label = SLUG_TO_LABEL_EXTRATOS[url_subtab]
    subtab_labels = list(SUBTABS_EXTRATOS.values())
    default_idx = subtab_labels.index(current_label)
    
    selected_label = st.radio(
        "Selecionar Extrato:",
        options=subtab_labels,
        index=default_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="extratos_subtab_radio"
    )
    
    selected_slug = LABEL_TO_SLUG_EXTRATOS[selected_label]
    if st.query_params.get("subtab") != selected_slug:
        st.query_params["subtab"] = selected_slug
        logger.info(f"Sub-navegação Extratos: {selected_slug}")
        st.rerun()
    
    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    
    modo_privacidade = st.session_state.get("ext_modo_privacidade", False)

    if selected_slug == "receitas":
        st.markdown("### 🪙 Receitas")
        
        # Filtra para exibir apenas receitas puras (não-patrimoniais)
        df_receitas_puras = pd.DataFrame()
        if df_receitas is not None and not df_receitas.empty:
            if "Categoria" in df_receitas.columns:
                df_receitas_puras = df_receitas[~df_receitas["Categoria"].isin(CATEGORIAS_PROVENTOS)].copy()
            else:
                df_receitas_puras = df_receitas.copy()

        if df_receitas_puras.empty:
            st.info("Nenhuma receita não-patrimonial cadastrada.")
        else:
            # Lê filtros definidos na sidebar
            busca_rec = st.session_state.get("ext_rec_busca", "").strip().lower()
            cat_receita_sel = st.session_state.get("ext_rec_cat", "Todas")
            mes_ano_rec_sel = st.session_state.get("ext_rec_mes", "Todos")
            
            df_receitas_filtered = df_receitas_puras.copy()
            if busca_rec and "Nome" in df_receitas_filtered.columns:
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Nome"].astype(str).str.lower().str.contains(busca_rec)]
            if cat_receita_sel != "Todas" and "Categoria" in df_receitas_filtered.columns:
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Categoria"] == cat_receita_sel]
            if mes_ano_rec_sel != "Todos" and "Recebido em" in df_receitas_filtered.columns:
                df_receitas_filtered = df_receitas_filtered[pd.to_datetime(df_receitas_filtered["Recebido em"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_rec_sel]
                
            df_receitas_display = df_receitas_filtered.copy()
            
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

            if modo_privacidade and "Valor" in df_receitas_display.columns:
                df_receitas_display["Valor"] = "R$ ••••••"
                st.dataframe(
                    df_receitas_display,
                    column_config={
                        "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                    },
                    width='stretch'
                )
            else:
                st.dataframe(
                    df_receitas_display,
                    column_config={
                        "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    },
                    width='stretch'
                )
            
            total_rec_soma = df_receitas_filtered["Valor"].sum() if "Valor" in df_receitas_filtered.columns else 0.0
            total_rec_formatted = format_number(total_rec_soma, is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Receitas ({len(df_receitas_filtered)} lançamentos)</span>
                <span style="font-weight: 700; color: #00E676; font-size: 20px;">{total_rec_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    elif selected_slug == "despesas":
        st.markdown("### 💸 Despesas")
        if df_despesas.empty:
            st.info("Nenhuma despesa cadastrada.")
        else:
            # Lê filtros definidos na sidebar
            busca_desp = st.session_state.get("ext_desp_busca", "").strip().lower()
            cat_despesa_sel = st.session_state.get("ext_desp_cat", "Todas")
            fixo_sel = st.session_state.get("ext_desp_fixo", "Todos")
            essencial_sel = st.session_state.get("ext_desp_ess", "Todos")
            mes_ano_desp_sel = st.session_state.get("ext_desp_mes", "Todos")
            
            df_despesas_filtered = df_despesas.copy()
            if busca_desp and "Nome" in df_despesas_filtered.columns:
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Nome"].astype(str).str.lower().str.contains(busca_desp)]
            if cat_despesa_sel != "Todas" and "Categoria" in df_despesas_filtered.columns:
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Categoria"] == cat_despesa_sel]
            if "Fixo vs. Variável" in df_despesas_filtered.columns and fixo_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Fixo vs. Variável"] == fixo_sel]
            if "Essencial vs. Não Essencial" in df_despesas_filtered.columns and essencial_sel != "Todos":
                df_despesas_filtered = df_despesas_filtered[df_despesas_filtered["Essencial vs. Não Essencial"] == essencial_sel]
            if mes_ano_desp_sel != "Todos" and "Gasto em" in df_despesas_filtered.columns:
                df_despesas_filtered = df_despesas_filtered[pd.to_datetime(df_despesas_filtered["Gasto em"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_desp_sel]
                
            df_despesas_display = df_despesas_filtered.copy()
            
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

            if modo_privacidade and "Valor" in df_despesas_display.columns:
                df_despesas_display["Valor"] = "R$ ••••••"
                st.dataframe(
                    df_despesas_display,
                    column_config={
                        "Gasto em": st.column_config.DateColumn("Gasto Em", format="DD/MM/YYYY"),
                    },
                    width='stretch'
                )
            else:
                st.dataframe(
                    df_despesas_display,
                    column_config={
                        "Gasto em": st.column_config.DateColumn("Gasto Em", format="DD/MM/YYYY"),
                        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    },
                    width='stretch'
                )
            
            total_des_soma = df_despesas_filtered["Valor"].sum() if "Valor" in df_despesas_filtered.columns else 0.0
            total_des_formatted = format_number(total_des_soma, is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Despesas ({len(df_despesas_filtered)} lançamentos)</span>
                <span style="font-weight: 700; color: #FF5252; font-size: 20px;">{total_des_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    elif selected_slug == "dividendos":
        st.markdown("### 📈 Dividendos Recebidos")
        
        # Isola os proventos a partir de df_receitas ou do df_dividendos derivado
        df_divs_base = pd.DataFrame()
        if df_dividendos is not None and not df_dividendos.empty:
            df_divs_base = df_dividendos.copy()
        elif df_receitas is not None and not df_receitas.empty and "Categoria" in df_receitas.columns:
            df_divs_base = df_receitas[df_receitas["Categoria"].isin(CATEGORIAS_PROVENTOS)].copy()

        if df_divs_base.empty:
            st.info("Nenhum dividendo ou provento passivo lançado.")
        else:
            col_ativo_nome = "Ativo" if "Ativo" in df_divs_base.columns else "Nome"
            ativo_div_sel = st.session_state.get("ext_div_ativo", "Todos")
            cat_div_sel = st.session_state.get("ext_div_cat", "Todas")
            mes_ano_div_sel = st.session_state.get("ext_div_mes", "Todos")
            
            df_dividendos_filtered = df_divs_base.copy()
            if ativo_div_sel != "Todos" and col_ativo_nome in df_dividendos_filtered.columns:
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered[col_ativo_nome] == ativo_div_sel]
            if cat_div_sel != "Todas" and "Categoria" in df_dividendos_filtered.columns:
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered["Categoria"] == cat_div_sel]
            if mes_ano_div_sel != "Todos" and "Recebido em" in df_dividendos_filtered.columns:
                df_dividendos_filtered = df_dividendos_filtered[pd.to_datetime(df_dividendos_filtered["Recebido em"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_div_sel]
                
            df_dividendos_display = df_dividendos_filtered.copy()
            
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

            if modo_privacidade and "Valor" in df_dividendos_display.columns:
                df_dividendos_display["Valor"] = "R$ ••••••"
                st.dataframe(
                    df_dividendos_display,
                    column_config={
                        "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                    },
                    width='stretch'
                )
            else:
                st.dataframe(
                    df_dividendos_display,
                    column_config={
                        "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    },
                    width='stretch'
                )
            
            total_div_soma = df_dividendos_filtered["Valor"].sum() if "Valor" in df_dividendos_filtered.columns else 0.0
            total_div_formatted = format_number(total_div_soma, is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Dividendos ({len(df_dividendos_filtered)} pagamentos)</span>
                <span style="font-weight: 700; color: #FFC107; font-size: 20px;">{total_div_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    elif selected_slug == "ordens":
        st.markdown("### 📊 Histórico de Ordens de Compra e Venda")
        if df_orders.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
            ativo_selecionado = st.session_state.get("ext_ord_ativo", "Todos")
            acao_selecionada = st.session_state.get("ext_ord_acao", "Todos")
            tipo_selecionado = st.session_state.get("ext_ord_tipo", "Todos")
            setor_selecionado = st.session_state.get("ext_ord_setor", "Todos")
            mes_ano_ord_sel = st.session_state.get("ext_ord_mes", "Todos")
            
            df_orders_filtered = df_orders.copy()
            if ativo_selecionado != "Todos" and "Papel" in df_orders_filtered.columns:
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Papel"] == ativo_selecionado]
            if acao_selecionada != "Todos" and "Compra/Venda" in df_orders_filtered.columns:
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Compra/Venda"] == acao_selecionada]
            if tipo_selecionado != "Todos" and "Tipo" in df_orders_filtered.columns:
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Tipo"] == tipo_selecionado]
            if "Setor Econômico" in df_orders_filtered.columns and setor_selecionado != "Todos":
                df_orders_filtered = df_orders_filtered[df_orders_filtered["Setor Econômico"] == setor_selecionado]
            if mes_ano_ord_sel != "Todos" and "data envio" in df_orders_filtered.columns:
                df_orders_filtered = df_orders_filtered[pd.to_datetime(df_orders_filtered["data envio"], errors='coerce').dt.strftime("%m/%Y") == mes_ano_ord_sel]
                
            df_orders_display = df_orders_filtered.sort_values("data envio", ascending=False).copy()
            moedas_filtradas = df_orders_filtered["Moeda"].unique() if "Moeda" in df_orders_filtered.columns else ["BRL"]
            prefixo_moeda = "R$" if (len(moedas_filtradas) == 1 and moedas_filtradas[0] == "BRL") else ("$" if (len(moedas_filtradas) == 1 and moedas_filtradas[0] == "USD") else "")
            format_str = f"{prefixo_moeda} %.2f" if prefixo_moeda else "%.2f"
            
            if modo_privacidade:
                for col_m in ["Total líquido", "Preço médio + corretagem", "Preço médio", "Total", "Corretagem"]:
                    if col_m in df_orders_display.columns:
                        df_orders_display[col_m] = "••••••"
                st.dataframe(
                    df_orders_display,
                    column_config={
                        "data envio": st.column_config.DatetimeColumn("Data Envio", format="DD/MM/YYYY HH:mm"),
                        "Qtd Executada": st.column_config.NumberColumn("Qtd Executada", format="%.4f"),
                    },
                    width='stretch'
                )
            else:
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
            
            def calc_net_order_value(row):
                action = str(row.get("Compra/Venda", "")).strip().upper()
                val = float(row.get("Total líquido", 0))
                if "VENDA" in action or action == "V":
                    return -val
                return val
                
            net_values = df_orders_filtered.apply(calc_net_order_value, axis=1) if not df_orders_filtered.empty else pd.Series(dtype=float)
            
            moedas_filtradas = df_orders_filtered["Moeda"].unique() if "Moeda" in df_orders_filtered.columns else ["BRL"]
            if len(moedas_filtradas) == 1:
                moeda_display = moedas_filtradas[0]
                total_soma_ordens = net_values.sum()
            else:
                total_soma_ordens = net_values.sum()
                moeda_display = "BRL"
                
            total_soma_formatted = format_number(total_soma_ordens, is_currency=True, currency=moeda_display, mask_privacy=modo_privacidade)
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total Líquido ({len(df_orders_filtered)} ordens)</span>
                <span style="font-weight: 700; color: #2979FF; font-size: 20px;">{total_soma_formatted}</span>
            </div>
            """, unsafe_allow_html=True)

