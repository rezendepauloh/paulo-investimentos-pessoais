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

from src.services.credit_card_projection import (
    calculate_credit_card_projections,
    calculate_credit_card_health_indicators,
    generate_credit_card_diagnosis,
)
from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("tabs", "cartao_credito")

SUBTABS_CARTAO = {
    "visao_geral": "📊 Projeção & Visão Geral",
    "compras_ativas": "🛒 Compras Parceladas Ativas",
    "finalizacoes_mes": "🏁 Término de Parcelas & Alívio",
    "detalhes_mensais": "📅 Cronograma Mensal Futuro",
    "historico_quitadas": "🏁 Histórico de Compras Quitadas"
}
SLUG_TO_LABEL_CARTAO = SUBTABS_CARTAO
LABEL_TO_SLUG_CARTAO = {v: k for k, v in SUBTABS_CARTAO.items()}

def render_tab_cartao_credito(df_despesas: pd.DataFrame, df_receitas: pd.DataFrame = None):
    """
    Renderiza a interface analítica e preditiva de parcelas futuras do cartão de crédito.
    """
    st.subheader("💳 Controle de Parcelas & Previsão de Cartão de Crédito")
    st.caption("Acompanhe o saldo residual devedor, previsão de faturas futuras e término de parcelamentos.")

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

    # Filtros lidos da sidebar de acordo com a subtab atual (com fallback para histórico)
    modo_privacidade = st.session_state.get("cartao_modo_privacidade", False)

    if selected_slug == "visao_geral":
        filtro_categoria = st.session_state.get("cartao_vg_categoria", st.session_state.get("cartao_filtro_categoria", "Todas as Categorias"))
        termo_busca = st.session_state.get("cartao_vg_busca", st.session_state.get("cartao_busca", "")).strip().lower()
    elif selected_slug == "compras_ativas":
        filtro_categoria = st.session_state.get("cartao_ativas_categoria", "Todas as Categorias")
        termo_busca = st.session_state.get("cartao_ativas_busca", "").strip().lower()
    elif selected_slug == "finalizacoes_mes":
        filtro_categoria = st.session_state.get("cartao_term_categoria", "Todas as Categorias")
        termo_busca = st.session_state.get("cartao_term_busca", "").strip().lower()
    elif selected_slug == "detalhes_mensais":
        filtro_categoria = st.session_state.get("cartao_cron_categoria", "Todas as Categorias")
        termo_busca = st.session_state.get("cartao_cron_busca", "").strip().lower()
    elif selected_slug == "historico_quitadas":
        filtro_categoria = st.session_state.get("cartao_quit_categoria", "Todas as Categorias")
        termo_busca = st.session_state.get("cartao_quit_busca", "").strip().lower()
    else:
        filtro_categoria = "Todas as Categorias"
        termo_busca = ""

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

    # Recalcula dinamicamente a projeção mensal para que o gráfico da Curva de Decaimento (L150)
    # reflita com fidelidade as compras e parcelas filtradas por categoria e busca
    if not df_detalhes.empty:
        df_proj_mensal = df_detalhes.groupby(["ano_mes", "mes_ano"]).agg(
            total_mes=("valor", "sum"),
            qtd_parcelas=("valor", "count"),
            compras_encerrando=("e_ultima_parcela", lambda x: int(sum(x)))
        ).reset_index().sort_values("ano_mes")
    else:
        df_proj_mensal = pd.DataFrame(columns=["ano_mes", "mes_ano", "total_mes", "qtd_parcelas", "compras_encerrando"])

    # Recalcula totais com base nos filtros
    tot_comprometido_filtrado = float(df_ativas["valor_restante"].sum()) if not df_ativas.empty else 0.0
    qtd_ativas_filtradas = len(df_ativas)
    media_val = float(df_proj_mensal["total_mes"].mean()) if not df_proj_mensal.empty else 0.0

    # -------------------------------------------------------------------------
    # CARDS DE MÉTRICAS EXECUTIVAS
    # -------------------------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        v_str = "R$ ••••••" if modo_privacidade else f"R$ {tot_comprometido_filtrado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric(
            "💳 Total Comprometido Futuro",
            v_str,
            help="Soma total de todas as parcelas que ainda restam a pagar nos cartões para a seleção atual."
        )

    with col2:
        v_media = "R$ ••••••" if modo_privacidade else f"R$ {media_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric(
            "⏳ Média Mensal Estimada",
            v_media,
            help="Média do valor comprometido por mês nos próximos períodos considerando o filtro ativo."
        )

    with col3:
        st.metric(
            "🛒 Compras Parceladas Ativas",
            f"{qtd_ativas_filtradas}",
            help="Quantidade de produtos ou serviços com parcelas ainda em andamento."
        )

    with col4:
        # Se filtrado, recalcula a quantidade encerrando no mês de destaque
        mes_destaque = resumo.get("mes_destaque_encerramento", resumo.get("proximo_mes", ""))
        encerrando = len(df_ativas[df_ativas["mes_termino"] == mes_destaque]) if not df_ativas.empty else 0
        st.metric(
            f"🏁 Finalizam em {mes_destaque}" if mes_destaque else "🏁 Finalizam em Breve",
            f"{encerrando} compras",
            help=f"Quantidade de compras parceladas que completam sua última parcela em {mes_destaque}, liberando limite e aliviando a fatura seguinte."
        )

    st.markdown("---")
    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # PAINEL DE DIAGNÓSTICO DE SOLVÊNCIA & DECISÃO DO CARTÃO
    # -------------------------------------------------------------------------
    if selected_slug == "visao_geral":
        indicators = calculate_credit_card_health_indicators(df_despesas, projections, df_receitas)
        diagnosticos_cc = generate_credit_card_diagnosis(indicators)

        if diagnosticos_cc:
            st.markdown("#### 🎯 Diagnóstico de Solvência & Tomada de Decisão")
            st.caption("Avaliação de comprometimento de renda, alavancagem de curto prazo e qualidade do endividamento.")
            
            cols_cc = st.columns(min(3, len(diagnosticos_cc)))
            for idx, d_item in enumerate(diagnosticos_cc):
                with cols_cc[idx % len(cols_cc)]:
                    val_card = "••••••" if modo_privacidade and "R$" in str(d_item['valor']) else d_item['valor']
                    st.markdown(
                        f"""
                        <div style="border-radius: 8px; border: 1px solid #e0e0e0; padding: 12px; margin-bottom: 14px; background-color: rgba(255, 255, 255, 0.03);">
                            <div style="font-size: 1.05rem; font-weight: 600;">{d_item['icone']} {d_item['titulo']}</div>
                            <div style="font-size: 1.35rem; font-weight: bold; margin: 4px 0;">{val_card}</div>
                            <div style="font-size: 0.86rem; color: #888;">{d_item['mensagem']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

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
    # SUBABA 3: TÉRMINO DE PARCELAS & ALÍVIO ORÇAMENTÁRIO
    # =========================================================================
    elif selected_slug == "finalizacoes_mes":
        st.markdown("#### 🏁 Compras Parceladas que Finalizam no Mês")
        st.caption("Consulte as compras que completam sua última parcela no mês selecionado na barra lateral e o alívio que trarão ao seu orçamento.")

        if not df_ativas.empty:
            # Identifica compras que possuem data_termino e ano_mes
            df_ativas_term = df_ativas.copy()
            df_ativas_term["ano_mes_termino"] = pd.to_datetime(df_ativas_term["data_termino"]).dt.strftime("%Y-%m")
            
            # Ordena os meses disponíveis cronologicamente
            meses_termino_disponiveis = sorted(df_ativas_term["ano_mes_termino"].unique().tolist())

            if meses_termino_disponiveis:
                # Obtém o mês selecionado na sidebar (ou primeiro disponível)
                mes_termino_escolhido = st.session_state.get("cartao_term_mes", meses_termino_disponiveis[0])
                if mes_termino_escolhido not in meses_termino_disponiveis:
                    mes_termino_escolhido = meses_termino_disponiveis[0]

                # Rótulo amigável para exibição
                dt_escolhido = pd.to_datetime(mes_termino_escolhido + "-01")
                meses_pt = {
                    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
                    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
                    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
                }
                nome_mes_exibicao = f"{meses_pt.get(dt_escolhido.month, dt_escolhido.strftime('%B'))}/{dt_escolhido.year}"

                # Filtra compras que terminam no mês selecionado
                df_finalizando = df_ativas_term[df_ativas_term["ano_mes_termino"] == mes_termino_escolhido].copy()

                # Métricas do mês selecionado
                total_alivio_mensal = float(df_finalizando["valor_parcela"].sum())
                qtd_compras_fim = len(df_finalizando)
                total_contratado_fim = float((df_finalizando["valor_parcela"] * df_finalizando["total_parcelas"]).sum())

                # Formatações com modo de privacidade
                str_alivio = "R$ ••••••" if modo_privacidade else f"R$ {total_alivio_mensal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                str_total_contratado = "R$ ••••••" if modo_privacidade else f"R$ {total_contratado_fim:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                # Cards de Resumo do Impacto
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric(
                        "🕊️ Alívio Mensal na Fatura Seguinte",
                        str_alivio,
                        help="Soma do valor das parcelas que chegam ao fim neste mês e deixarão de ser cobradas a partir da próxima fatura."
                    )
                with c2:
                    st.metric(
                        "📦 Compras Encerrando",
                        f"{qtd_compras_fim}",
                        help="Quantidade de contratos de compras parceladas que realizam sua última cobrança neste mês."
                    )
                with c3:
                    st.metric(
                        "💰 Custo Total Destas Compras",
                        str_total_contratado,
                        help="Valor original somado de todas as parcelas dessas compras que estão sendo concluídas."
                    )

                st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

                # Layout com Gráfico e Tabela
                col_graf, col_tab = st.columns([1, 1])

                with col_graf:
                    st.markdown("##### 🏷️ Alívio por Categoria de Despesa")
                    if "categoria" in df_finalizando.columns and not df_finalizando.empty:
                        cat_fim = df_finalizando.groupby("categoria")["valor_parcela"].sum().reset_index()
                        cat_fim = cat_fim.sort_values("valor_parcela", ascending=False)

                        fig_cat = px.pie(
                            cat_fim,
                            names="categoria",
                            values="valor_parcela",
                            hole=0.45,
                            color_discrete_sequence=px.colors.qualitative.Safe
                        )
                        fig_cat.update_layout(
                            margin=dict(l=10, r=10, t=10, b=10),
                            height=300,
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=-0.2)
                        )
                        st.plotly_chart(fig_cat, use_container_width=True)
                    else:
                        st.caption("Sem dados de categoria para este mês.")

                with col_tab:
                    st.markdown("##### 💡 Impacto no Fluxo de Caixa")
                    st.info(
                        f"Ao quitar essas **{qtd_compras_fim} compras**, seu limite de crédito será recomposto e seu custo fixo mensal terá uma redução definitiva de **{str_alivio}** por mês."
                    )
                    st.markdown(
                        """
                        - **Dica de Planejamento:** Aproveite a liberação desse fluxo mensal para direcionar aos aportes de investimentos ou reforçar sua reserva de emergência.
                        - O término ocorre exatamente na data da fatura deste mês.
                        """
                    )

                st.markdown("##### 📋 Compras que Realizam a Última Parcela")
                df_tab_finalizando = df_finalizando[[
                    "nome_base", "categoria", "total_parcelas", "valor_parcela", "conta"
                ]].copy()
                
                df_tab_finalizando["Última Parcela"] = df_tab_finalizando["total_parcelas"].apply(lambda t: f"{t}/{t}")
                df_tab_finalizando["Total Compra (R$)"] = df_finalizando["valor_parcela"] * df_finalizando["total_parcelas"]

                colunas_fim_exibicao = [
                    "nome_base", "categoria", "Última Parcela", "valor_parcela", "Total Compra (R$)", "conta"
                ]
                df_render_fim = df_tab_finalizando[colunas_fim_exibicao].rename(columns={
                    "nome_base": "Estabelecimento / Compra",
                    "categoria": "Categoria",
                    "valor_parcela": "Valor Parcela (R$)",
                    "conta": "Conta / Cartão"
                })

                if modo_privacidade:
                    df_render_fim["Valor Parcela (R$)"] = "R$ ••••••"
                    df_render_fim["Total Compra (R$)"] = "R$ ••••••"
                    st.dataframe(df_render_fim, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(
                        df_render_fim,
                        column_config={
                            "Valor Parcela (R$)": st.column_config.NumberColumn("Valor Parcela (R$)", format="R$ %.2f"),
                            "Total Compra (R$)": st.column_config.NumberColumn("Total Compra (R$)", format="R$ %.2f")
                        },
                        use_container_width=True,
                        hide_index=True
                    )

                # Exportação CSV das compras finalizando
                csv_fim = df_render_fim.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Exportar Compras Finalizando (CSV)",
                    data=csv_fim,
                    file_name=f"compras_finalizando_{mes_termino_escolhido}.csv",
                    mime="text/csv"
                )

            else:
                st.info("Nenhuma previsão de término de compras catalogada para os filtros atuais.")
        else:
            st.info("Nenhuma compra parcelada ativa para análise de término.")

    # =========================================================================
    # SUBABA 4: CRONOGRAMA MENSAL FUTURO (MATRIZ & DETALHES)
    # =========================================================================
    elif selected_slug == "detalhes_mensais":
        st.markdown("#### 📅 Cronograma Mensal de Parcelas Vincendas")
        st.write("Consulte exatamente quais parcelas cairão em cada mês futuro.")

        if not df_detalhes.empty:
            meses_disponiveis = sorted(df_detalhes["ano_mes"].unique().tolist())
            
            # Obtém o mês selecionado na sidebar (ou primeiro disponível)
            mes_escolhido = st.session_state.get("cartao_cron_mes", meses_disponiveis[0])
            if mes_escolhido not in meses_disponiveis:
                mes_escolhido = meses_disponiveis[0]

            dt_escolhido_cron = pd.to_datetime(mes_escolhido + "-01")
            meses_pt = {
                1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
                5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
                9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
            }
            nome_mes_cron = f"{meses_pt.get(dt_escolhido_cron.month, dt_escolhido_cron.strftime('%B'))}/{dt_escolhido_cron.year}"

            df_mes_especifico = df_detalhes[df_detalhes["ano_mes"] == mes_escolhido].copy()

            tot_mes_sel = df_mes_especifico["valor"].sum()
            qtd_mes_sel = len(df_mes_especifico)
            tot_mes_str = "R$ ••••••" if modo_privacidade else f"R$ {tot_mes_sel:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            st.info(f"💳 Total estimado para **{nome_mes_cron}**: **{tot_mes_str}** em **{qtd_mes_sel} parcelas**.")

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
