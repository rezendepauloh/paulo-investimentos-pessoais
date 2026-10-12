# -*- coding: utf-8 -*-
"""
Aba: Controle de Parcelas & Cartão de Crédito
Apresenta o fluxo futuro de parcelas vincendas, estimativa de fatura mês a mês,
alívio orçamentário por parcelas que estão acabando e tabela detalhada de compras ativas.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.services.credit_card_projection import calculate_credit_card_projections
from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("tabs", "cartao_credito")

SUBTABS_CARTAO = {
    "visao_geral": "📊 Projeção & Visão Geral",
    "compras_ativas": "🛒 Compras Parceladas Ativas",
    "detalhes_mensais": "📅 Cronograma Mensal Futuro",
    "historico_quitadas": "🏁 Histórico de Compras Quitadas"
}
SLUG_TO_LABEL_CARTAO = SUBTABS_CARTAO
LABEL_TO_SLUG_CARTAO = {v: k for k, v in SUBTABS_CARTAO.items()}

def render_tab_cartao_credito(df_despesas: pd.DataFrame):
    """
    Renderiza a interface analítica e preditiva de parcelas futuras do cartão de crédito.
    """
    st.subheader("💳 Controle de Parcelas & Previsão de Cartão de Crédito")
    st.caption("Acompanhe o saldo residual devedor, previsão de faturas futuras e término de parcelamentos.")

    # Filtros globais lidos da sidebar
    modo_privacidade = st.session_state.get("cartao_modo_privacidade", False)
    filtro_categoria = st.session_state.get("cartao_filtro_categoria", "Todas as Categorias")
    termo_busca = st.session_state.get("cartao_busca", "").strip().lower()

    # Executa cálculo de projeção
    projections = calculate_credit_card_projections(df_despesas)
    df_ativas = projections["compras_ativas"]
    df_quitadas = projections["compras_quitadas"]
    df_proj_mensal = projections["projecao_mensal"]
    df_detalhes = projections["detalhes_futuros"]
    resumo = projections["resumo"]

    if df_ativas.empty and df_quitadas.empty:
        st.info("ℹ️ Nenhuma compra parcelada foi identificada na base de despesas. Ao importar faturas ou registrar compras com formato '1/X', as projeções serão geradas automaticamente aqui.")
        return

    # Aplicação de filtros contextuais
    if filtro_categoria != "Todas as Categorias":
        if not df_ativas.empty:
            df_ativas = df_ativas[df_ativas["categoria"] == filtro_categoria]
        if not df_quitadas.empty:
            df_quitadas = df_quitadas[df_quitadas["categoria"] == filtro_categoria]
        if not df_detalhes.empty:
            df_detalhes = df_detalhes[df_detalhes["categoria"] == filtro_categoria]

    if termo_busca:
        if not df_ativas.empty:
            df_ativas = df_ativas[
                df_ativas["nome_base"].str.lower().str.contains(termo_busca) |
                df_ativas["ultima_descricao"].str.lower().str.contains(termo_busca)
            ]
        if not df_quitadas.empty:
            df_quitadas = df_quitadas[
                df_quitadas["nome_base"].str.lower().str.contains(termo_busca) |
                df_quitadas["ultima_descricao"].str.lower().str.contains(termo_busca)
            ]
        if not df_detalhes.empty:
            df_detalhes = df_detalhes[df_detalhes["nome_base"].str.lower().str.contains(termo_busca)]

    # Recalcula totais com base nos filtros
    tot_comprometido_filtrado = float(df_ativas["valor_restante"].sum()) if not df_ativas.empty else 0.0
    qtd_ativas_filtradas = len(df_ativas)

    # -------------------------------------------------------------------------
    # CARDS DE MÉTRICAS EXECUTIVAS
    # -------------------------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        v_str = "R$ ••••••" if modo_privacidade else f"R$ {tot_comprometido_filtrado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric(
            "💳 Total Comprometido Futuro",
            v_str,
            help="Soma total de todas as parcelas que ainda restam a pagar nos cartões."
        )

    with col2:
        media_val = resumo["media_mensal"]
        v_media = "R$ ••••••" if modo_privacidade else f"R$ {media_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric(
            "⏳ Média Mensal Estimada",
            v_media,
            help="Média do valor comprometido por mês nos próximos períodos."
        )

    with col3:
        st.metric(
            "🛒 Compras Parceladas Ativas",
            f"{qtd_ativas_filtradas}",
            help="Quantidade de produtos ou serviços com parcelas ainda em andamento."
        )

    with col4:
        encerrando = resumo.get("encerrando_destaque", 0)
        mes_destaque = resumo.get("mes_destaque_encerramento", resumo.get("proximo_mes", ""))
        st.metric(
            f"🏁 Finalizam em {mes_destaque}" if mes_destaque else "🏁 Finalizam em Breve",
            f"{encerrando} compras",
            help=f"Quantidade de compras parceladas que completam sua última parcela em {mes_destaque}, liberando limite e aliviando a fatura seguinte."
        )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # SUB-NAVEGAÇÃO POR ABAS INTERNAS
    # -------------------------------------------------------------------------
    url_subtab = st.query_params.get("subtab_cartao", "visao_geral")
    if url_subtab not in SLUG_TO_LABEL_CARTAO:
        url_subtab = "visao_geral"

    current_label = SLUG_TO_LABEL_CARTAO[url_subtab]
    subtab_labels = list(SUBTABS_CARTAO.values())
    default_idx = subtab_labels.index(current_label)

    selected_label = st.radio(
        "Selecionar Visualização:",
        options=subtab_labels,
        index=default_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="cartao_subtab_radio"
    )

    selected_slug = LABEL_TO_SLUG_CARTAO[selected_label]
    if st.query_params.get("subtab_cartao") != selected_slug:
        st.query_params["subtab_cartao"] = selected_slug
        st.rerun()

    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # SUBABA 1: VISÃO GERAL & EVOLUÇÃO TEMPORAL
    # =========================================================================
    if selected_slug == "visao_geral":
        st.markdown("#### 📈 Curva de Decaimento da Fatura & Alívio Orçamentário")
        st.write("Veja como as parcelas do cartão vão reduzindo progressivamente ao longo dos próximos meses conforme as compras vão sendo quitadas.")

        if not df_proj_mensal.empty:
            fig = go.Figure()

            # Barras do valor mensal estimado
            fig.add_trace(go.Bar(
                x=df_proj_mensal["mes_ano"],
                y=df_proj_mensal["total_mes"],
                name="Fatura Estimada (R$)",
                marker_color="#3B82F6",
                text=[f"R$ {v:,.0f}".replace(",", ".") if not modo_privacidade else "••••" for v in df_proj_mensal["total_mes"]],
                textposition="auto"
            ))

            # Linha de quantidade de parcelas ativas no mês
            fig.add_trace(go.Scatter(
                x=df_proj_mensal["mes_ano"],
                y=df_proj_mensal["qtd_parcelas"],
                name="Qtd. Parcelas Ativas",
                yaxis="y2",
                mode="lines+markers",
                line=dict(color="#10B981", width=3),
                marker=dict(size=7)
            ))

            fig.update_layout(
                title="Evolução do Comprometimento Futuro por Mês",
                xaxis_title="Mês da Fatura",
                yaxis=dict(
                    title="Valor Estimado (R$)",
                    side="left"
                ),
                yaxis2=dict(
                    title="Quantidade de Parcelas",
                    side="right",
                    overlaying="y",
                    showgrid=False
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                template="plotly_white",
                height=420,
                margin=dict(l=20, r=20, t=50, b=30)
            )

            st.plotly_chart(fig, use_container_width=True)

            # Destaques em colunas
            c_left, c_right = st.columns([1, 1])

            with c_left:
                st.markdown("##### 🏁 Compras que Terminam nos Próximos Meses")
                proximas_terminar = df_ativas.sort_values(by="parcelas_restantes").head(8)
                if not proximas_terminar.empty:
                    termino_display = []
                    for _, r in proximas_terminar.iterrows():
                        v_parc_str = "R$ ••••••" if modo_privacidade else f"R$ {r['valor_parcela']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        termino_display.append({
                            "Item / Estabelecimento": r["nome_base"],
                            "Faltam": f"{r['parcelas_restantes']}x de {v_parc_str}",
                            "Término Previsto": r["mes_termino"]
                        })
                    st.dataframe(pd.DataFrame(termino_display), use_container_width=True, hide_index=True)
                else:
                    st.caption("Nenhuma compra ativa no momento.")

            with c_right:
                st.markdown("##### 🏷️ Distribuição por Categoria de Gasto")
                if not df_ativas.empty and "categoria" in df_ativas.columns:
                    cat_summary = df_ativas.groupby("categoria")["valor_restante"].sum().reset_index()
                    cat_summary = cat_summary.sort_values("valor_restante", ascending=False)
                    fig_pie = px.pie(
                        cat_summary,
                        names="categoria",
                        values="valor_restante",
                        hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig_pie.update_layout(
                        margin=dict(l=10, r=10, t=20, b=20),
                        height=280,
                        showlegend=True
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

        else:
            st.info("Nenhuma projeção mensal disponível com os filtros atuais.")

    # =========================================================================
    # SUBABA 2: COMPRAS PARCELADAS ATIVAS
    # =========================================================================
    elif selected_slug == "compras_ativas":
        st.markdown(f"#### 🛒 Compras Parceladas em Andamento ({len(df_ativas)} ativas)")
        st.write("Acompanhe cada compra, quantas parcelas já foram pagas, quantas faltam e o saldo pendente.")

        if not df_ativas.empty:
            df_disp_ativas = df_ativas.copy()

            # Formatações amigáveis
            df_disp_ativas["Progresso"] = df_disp_ativas.apply(
                lambda r: f"{r['parcela_atual']}/{r['total_parcelas']} ({int((r['parcela_atual']/r['total_parcelas'])*100)}%)",
                axis=1
            )

            col_ordem = [
                "nome_base", "categoria", "Progresso", "parcelas_restantes",
                "valor_parcela", "valor_restante", "mes_termino", "conta"
            ]
            df_table = df_disp_ativas[col_ordem].rename(columns={
                "nome_base": "Estabelecimento / Compra",
                "categoria": "Categoria",
                "Progresso": "Parcelas Pagas",
                "parcelas_restantes": "Faltam",
                "valor_parcela": "Parcela (R$)",
                "valor_restante": "Saldo Devedor (R$)",
                "mes_termino": "Mês de Término",
                "conta": "Conta / Cartão"
            })

            if modo_privacidade:
                df_table["Parcela (R$)"] = "R$ ••••••"
                df_table["Saldo Devedor (R$)"] = "R$ ••••••"
                st.dataframe(df_table, use_container_width=True, hide_index=True)
            else:
                st.dataframe(
                    df_table,
                    column_config={
                        "Parcela (R$)": st.column_config.NumberColumn("Parcela (R$)", format="R$ %.2f"),
                        "Saldo Devedor (R$)": st.column_config.NumberColumn("Saldo Devedor (R$)", format="R$ %.2f"),
                        "Faltam": st.column_config.NumberColumn("Faltam", format="%d"),
                    },
                    use_container_width=True,
                    hide_index=True
                )

            # Exportação CSV
            csv_data = df_table.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar Lista de Compras Ativas (CSV)",
                data=csv_data,
                file_name="parcelas_ativas_cartao.csv",
                mime="text/csv"
            )
        else:
            st.info("Nenhuma compra ativa encontrada para os filtros selecionados.")

    # =========================================================================
    # SUBABA 3: CRONOGRAMA MENSAL FUTURO (MATRIZ & DETALHES)
    # =========================================================================
    elif selected_slug == "detalhes_mensais":
        st.markdown("#### 📅 Cronograma Mensal de Parcelas Vincendas")
        st.write("Consulte exatamente quais parcelas cairão em cada mês futuro.")

        if not df_detalhes.empty:
            meses_disponiveis = sorted(df_detalhes["ano_mes"].unique().tolist())
            col_sel_mes, _ = st.columns([2, 3])
            with col_sel_mes:
                # Mapeia rótulos amigáveis
                labels_mes = [
                    pd.to_datetime(m + "-01").strftime("%B/%Y").capitalize() for m in meses_disponiveis
                ]
                idx_sel = st.selectbox(
                    "📅 Selecione o Mês de Referência:",
                    range(len(meses_disponiveis)),
                    format_func=lambda i: f"{labels_mes[i]} ({df_detalhes[df_detalhes['ano_mes'] == meses_disponiveis[i]]['valor'].count()} parcelas)",
                    key="cartao_sel_cronograma_mes"
                )
                mes_escolhido = meses_disponiveis[idx_sel]

            df_mes_especifico = df_detalhes[df_detalhes["ano_mes"] == mes_escolhido].copy()

            tot_mes_sel = df_mes_especifico["valor"].sum()
            qtd_mes_sel = len(df_mes_especifico)
            tot_mes_str = "R$ ••••••" if modo_privacidade else f"R$ {tot_mes_sel:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            st.info(f"💳 Total estimado para **{labels_mes[idx_sel]}**: **{tot_mes_str}** em **{qtd_mes_sel} parcelas**.")

            df_mes_especifico["Aviso"] = df_mes_especifico["e_ultima_parcela"].apply(
                lambda f: "🏁 Última Parcela! Quita este mês" if f else "⏳ Em andamento"
            )

            colunas_mes = ["nome_base", "categoria", "parcela", "valor", "Aviso"]
            df_mes_tabela = df_mes_especifico[colunas_mes].rename(columns={
                "nome_base": "Estabelecimento",
                "categoria": "Categoria",
                "parcela": "Parcela no Mês",
                "valor": "Valor (R$)"
            })

            if modo_privacidade:
                df_mes_tabela["Valor (R$)"] = "R$ ••••••"
                st.dataframe(df_mes_tabela, use_container_width=True, hide_index=True)
            else:
                st.dataframe(
                    df_mes_tabela,
                    column_config={
                        "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
                    },
                    use_container_width=True,
                    hide_index=True
                )

        else:
            st.info("Nenhuma parcela futura no cronograma para os filtros atuais.")

    # =========================================================================
    # SUBABA 4: HISTÓRICO DE COMPRAS QUITADAS
    # =========================================================================
    elif selected_slug == "historico_quitadas":
        st.markdown(f"#### 🏁 Histórico de Compras Quitadas ({len(df_quitadas)} finalizadas)")
        st.write("Registro de compras parceladas que já completaram todas as parcelas contratadas.")

        if not df_quitadas.empty:
            df_disp_quitadas = df_quitadas.copy()
            df_disp_quitadas["total_pago"] = df_disp_quitadas["valor_parcela"] * df_disp_quitadas["total_parcelas"]

            df_quit_tabela = df_disp_quitadas[[
                "nome_base", "categoria", "total_parcelas", "valor_parcela", "total_pago", "mes_termino"
            ]].rename(columns={
                "nome_base": "Estabelecimento / Compra",
                "categoria": "Categoria",
                "total_parcelas": "Total de Parcelas",
                "valor_parcela": "Parcela (R$)",
                "total_pago": "Total Pago (R$)",
                "mes_termino": "Mês da Quitação"
            })

            if modo_privacidade:
                df_quit_tabela["Parcela (R$)"] = "R$ ••••••"
                df_quit_tabela["Total Pago (R$)"] = "R$ ••••••"
                st.dataframe(df_quit_tabela, use_container_width=True, hide_index=True)
            else:
                st.dataframe(
                    df_quit_tabela,
                    column_config={
                        "Parcela (R$)": st.column_config.NumberColumn("Parcela (R$)", format="R$ %.2f"),
                        "Total Pago (R$)": st.column_config.NumberColumn("Total Pago (R$)", format="R$ %.2f"),
                        "Total de Parcelas": st.column_config.NumberColumn("Total de Parcelas", format="%d")
                    },
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.caption("Nenhuma compra quitada catalogada com os filtros atuais.")
