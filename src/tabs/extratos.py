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
    
    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
    
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
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                nomes_receitas = ["Todos"] + sorted(df_receitas_puras["Nome"].dropna().unique().tolist())
                nome_receita_sel = st.selectbox("Filtrar por Descrição:", nomes_receitas, key="filter_rec_nome")
            with col_r2:
                categorias_receitas = ["Todas"] + sorted(df_receitas_puras["Categoria"].dropna().unique().tolist())
                cat_receita_sel = st.selectbox("Filtrar por Categoria (Receitas):", categorias_receitas, key="filter_rec_cat")
            with col_r3:
                df_temp = df_receitas_puras.copy()
                df_temp["Recebido em_dt"] = pd.to_datetime(df_temp["Recebido em"], errors='coerce')
                df_temp["Mes_Ano"] = df_temp["Recebido em_dt"].dt.strftime("%m/%Y")
                unique_months = df_temp["Mes_Ano"].dropna().unique().tolist()
                unique_months_sorted = sorted(unique_months, key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
                meses_anos = ["Todos"] + unique_months_sorted
                mes_ano_rec_sel = st.selectbox("Filtrar por Mês/Ano:", meses_anos, key="filter_rec_mes_ano")
            
            df_receitas_filtered = df_receitas_puras.copy()
            if nome_receita_sel != "Todos":
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Nome"] == nome_receita_sel]
            if cat_receita_sel != "Todas":
                df_receitas_filtered = df_receitas_filtered[df_receitas_filtered["Categoria"] == cat_receita_sel]
            if mes_ano_rec_sel != "Todos":
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
            st.dataframe(
                df_receitas_display,
                column_config={
                    "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                    "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                },
                width='stretch'
            )
            
            total_rec_soma = df_receitas_filtered["Valor"].sum()
            total_rec_formatted = format_number(total_rec_soma, is_currency=True, currency="BRL")
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Receitas (Filtro)</span>
                <span style="font-weight: 700; color: #00E676; font-size: 20px;">{total_rec_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    elif selected_slug == "despesas":
        st.markdown("### 🪙 Despesas")
        if df_despesas.empty:
            st.info("Nenhuma despesa cadastrada.")
        else:
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
            
            total_des_soma = df_despesas_filtered["Valor"].sum()
            total_des_formatted = format_number(total_des_soma, is_currency=True, currency="BRL")
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Despesas (Filtro)</span>
                <span style="font-weight: 700; color: #FF5252; font-size: 20px;">{total_des_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    elif selected_slug == "dividendos":
        st.markdown("### 🪙 Dividendos recebidos")
        
        # Isola os proventos a partir de df_receitas ou do df_dividendos derivado
        df_divs_base = pd.DataFrame()
        if df_dividendos is not None and not df_dividendos.empty:
            df_divs_base = df_dividendos.copy()
        elif df_receitas is not None and not df_receitas.empty and "Categoria" in df_receitas.columns:
            df_divs_base = df_receitas[df_receitas["Categoria"].isin(CATEGORIAS_PROVENTOS)].copy()

        if df_divs_base.empty:
            st.info("Nenhum dividendo ou provento passivo lançado.")
        else:
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                col_ativo_nome = "Ativo" if "Ativo" in df_divs_base.columns else "Nome"
                ativos_dividendos = ["Todos"] + sorted(df_divs_base[col_ativo_nome].dropna().unique().tolist())
                ativo_div_sel = st.selectbox("Filtrar por Ativo / Descrição:", ativos_dividendos, key="filter_div_ativo")
            with col_d2:
                categorias_dividendos = ["Todas"] + sorted(df_divs_base["Categoria"].dropna().unique().tolist())
                cat_div_sel = st.selectbox("Filtrar por Categoria (Dividendos):", categorias_dividendos, key="filter_div_cat")
            with col_d3:
                df_temp = df_divs_base.copy()
                df_temp["Recebido em_dt"] = pd.to_datetime(df_temp["Recebido em"], errors='coerce')
                df_temp["Mes_Ano"] = df_temp["Recebido em_dt"].dt.strftime("%m/%Y")
                unique_months = df_temp["Mes_Ano"].dropna().unique().tolist()
                unique_months_sorted = sorted(unique_months, key=lambda x: pd.to_datetime(x, format="%m/%Y"), reverse=True)
                meses_anos = ["Todos"] + unique_months_sorted
                mes_ano_div_sel = st.selectbox("Filtrar por Mês/Ano:", meses_anos, key="filter_div_mes_ano")
            
            df_dividendos_filtered = df_divs_base.copy()
            if ativo_div_sel != "Todos":
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered[col_ativo_nome] == ativo_div_sel]
            if cat_div_sel != "Todas":
                df_dividendos_filtered = df_dividendos_filtered[df_dividendos_filtered["Categoria"] == cat_div_sel]
            if mes_ano_div_sel != "Todos":
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
            st.dataframe(
                df_dividendos_display,
                column_config={
                    "Recebido em": st.column_config.DateColumn("Recebido Em", format="DD/MM/YYYY"),
                    "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                },
                width='stretch'
            )
            
            total_div_soma = df_dividendos_filtered["Valor"].sum()
            total_div_formatted = format_number(total_div_soma, is_currency=True, currency="BRL")
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total de Dividendos (Filtro)</span>
                <span style="font-weight: 700; color: #FFC107; font-size: 20px;">{total_div_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
            
    elif selected_slug == "ordens":
        st.markdown("### 🪙 Histórico de Ordens de Compra e Venda")
        if df_orders.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
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
                total_soma_ordens = net_values.sum()
                moeda_display = "BRL"
                
            total_soma_formatted = format_number(total_soma_ordens, is_currency=True, currency=moeda_display)
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 20px; border-radius: 12px; margin-top: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #88888b; font-size: 14px; text-transform: uppercase;">Total Líquido (Filtro Ativo)</span>
                <span style="font-weight: 700; color: #2979FF; font-size: 20px;">{total_soma_formatted}</span>
            </div>
            """, unsafe_allow_html=True)
