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
    "analise_contabil": "📐 Análise Contábil & Solvência",
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

    # =========================================================================
    # SUBABA 5: ANÁLISE CONTÁBIL & SOLVÊNCIA DAS OBRIGAÇÕES (ADC)
    # =========================================================================
    elif selected_slug == "analise_contabil":
        st.markdown("### 📐 Diagnóstico Contábil de Passivos & Tomada de Decisão Financeira")
        st.caption("Aplicação rigorosa dos conceitos de Análise das Demonstrações Contábeis (ADC): Estrutura de Capital, Liquidez, Composição do Endividamento e Solvência Orçamentária.")

        indicators_cc = calculate_credit_card_health_indicators(df_despesas, projections, df_receitas)
        diagnosticos_cc = generate_credit_card_diagnosis(indicators_cc)

        if diagnosticos_cc:
            st.markdown("#### 🔍 Pareceres do Diagnóstico:")
            cols_diag = st.columns(min(3, len(diagnosticos_cc)))
            for idx, d_item in enumerate(diagnosticos_cc):
                with cols_diag[idx % len(cols_diag)]:
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

        st.markdown("---")
        st.markdown("#### 📈 Matriz Contábil & Indicadores de Solvência")

        tab_solv, tab_perfil, tab_vert, tab_balao = st.tabs([
            "💧 Comprometimento & Cobertura",
            "⚖️ Estrutura & Alongamento",
            "📊 Análise Vertical & Qualidade",
            "🏢 Balão & Grandes Passivos"
        ])

        with tab_solv:
            st.markdown("##### 💧 Comprometimento do Fluxo de Renda Mensal")
            renda_est = indicators_cc.get("renda_mensal_estimada", 0.0)
            fatura_prox = indicators_cc.get("fatura_proximo_mes", 0.0)
            taxa_comp = indicators_cc.get("taxa_comprometimento_renda")
            saldo_tot = indicators_cc.get("saldo_devedor_total", 0.0)

            c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
            with c_kpi1:
                r_txt = "R$ ••••••" if modo_privacidade else f"R$ {renda_est:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("Renda Mensal Base", r_txt, help="Média mensal de receitas auferidas no período.")
            with c_kpi2:
                f_txt = "R$ ••••••" if modo_privacidade else f"R$ {fatura_prox:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("Próxima Fatura (Passivo Imediato)", f_txt, help="Total das parcelas programadas para o próximo mês.")
            with c_kpi3:
                comp_txt = f"{taxa_comp * 100:.1f}%" if taxa_comp is not None else "N/D"
                st.metric("Taxa de Comprometimento", comp_txt, help="Fatura / Renda Mensal. Nível saudável: até 20%.")

            # Gráfico de evolução da taxa de comprometimento ao longo dos próximos meses
            if not df_proj_mensal.empty and renda_est > 0:
                df_curva_comp = df_proj_mensal.head(12).copy()
                df_curva_comp["taxa_comp_pct"] = (df_curva_comp["total_mes"] / renda_est) * 100.0

                fig_comp = go.Figure()
                fig_comp.add_trace(go.Scatter(
                    x=df_curva_comp["mes_ano"],
                    y=df_curva_comp["taxa_comp_pct"],
                    mode="lines+markers",
                    name="Comprometimento da Renda (%)",
                    line=dict(color="#00E5FF", width=3),
                    marker=dict(size=8),
                    hovertemplate="<b>%{x}</b><br>Comprometimento: %{y:.1f}%<extra></extra>"
                ))
                fig_comp.add_hline(
                    y=20.0, line_dash="dash", line_color="#00E676",
                    annotation_text="Teto Saudável (20%)", annotation_position="bottom right"
                )
                fig_comp.add_hline(
                    y=35.0, line_dash="dot", line_color="#FF5252",
                    annotation_text="Limite Crítico (35%)", annotation_position="top right"
                )
                fig_comp.update_layout(
                    title=dict(text="Curva Projetada de Comprometimento de Renda nos Próximos Meses", font=dict(size=14, color="#e0e0e0")),
                    hovermode="x unified",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.02)",
                    font_color="#ffffff",
                    xaxis_title="Mês/Ano",
                    yaxis_title="Comprometimento (%)",
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)"),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)", ticksuffix="%"),
                    margin=dict(l=40, r=20, t=50, b=40),
                    height=340
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            with st.expander("📚 **Fórmulas e Fundamentos de Comprometimento & Cobertura (ADC)**", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("##### 💧 Índice de Comprometimento de Renda ($ICR$)")
                    st.latex(r"ICR = \frac{\text{Fatura Mensal}}{\text{Renda Líquida Mensal}}")
                    st.caption("Proporção do faturamento/salário absorvido por dívidas de curto prazo. Em análise financeira prudencial, deve situar-se abaixo de 20% a 25%.")
                with c2:
                    st.markdown("##### 🛡️ Cobertura do Passivo Circulante ($CPC$)")
                    st.latex(r"CPC = \frac{\text{Renda Líquida} - \text{Despesas Essenciais}}{\text{Fatura do Cartão}}")
                    st.caption("Capacidade do fluxo de caixa livre mensal absorver os compromissos parcelados sem necessidade de desinvestir ou recorrer a cheque especial.")

        with tab_perfil:
            st.markdown("##### ⚖️ Estrutura Temporal & Alongamento dos Passivos")
            meses_alav = indicators_cc.get("meses_alavancagem_futura")
            
            # Cálculo de Composição do Endividamento (CP vs LP):
            # Curto Prazo (CP): próximas 12 faturas
            # Longo Prazo (PNC): parcelas além de 12 meses (incluindo balões)
            if not df_proj_mensal.empty:
                cp_val = float(df_proj_mensal.head(12)["total_mes"].sum())
                lp_val = float(df_proj_mensal.iloc[12:]["total_mes"].sum()) if len(df_proj_mensal) > 12 else 0.0
                total_exigivel = cp_val + lp_val
                comp_cp_pct = (cp_val / total_exigivel * 100.0) if total_exigivel > 0 else 100.0
                comp_lp_pct = (lp_val / total_exigivel * 100.0) if total_exigivel > 0 else 0.0
            else:
                cp_val, lp_val, total_exigivel, comp_cp_pct, comp_lp_pct = 0.0, 0.0, 0.0, 0.0, 0.0

            c_e1, c_e2, c_e3 = st.columns(3)
            with c_e1:
                cp_txt = "R$ ••••••" if modo_privacidade else f"R$ {cp_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("Passivo Circulante (Próximos 12m)", cp_txt, help="Soma das parcelas vincendas até 1 ano.")
            with c_e2:
                lp_txt = "R$ ••••••" if modo_privacidade else f"R$ {lp_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("Exigível a Longo Prazo (> 12m)", lp_txt, help="Obrigações e balões com vencimento superior a 1 ano.")
            with c_e3:
                st.metric("Composição do Endividamento ($CE$)", f"{comp_cp_pct:.1f}% CP", help="Percentual da dívida concentrado no curto prazo.")

            col_perfil1, col_perfil2 = st.columns(2)
            with col_perfil1:
                fig_donut = go.Figure(data=[go.Pie(
                    labels=["Curto Prazo (≤ 12 meses)", "Longo Prazo (> 12 meses)"],
                    values=[cp_val, lp_val],
                    hole=0.45,
                    marker=dict(colors=["#3B82F6", "#E040FB"]),
                    textinfo="label+percent"
                )])
                fig_donut.update_layout(
                    title=dict(text="Composição do Endividamento ($CE$)", font=dict(size=14, color="#e0e0e0")),
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#ffffff",
                    legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
                    margin=dict(l=20, r=20, t=50, b=30),
                    height=320
                )
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_perfil2:
                # Gráfico de Alavancagem em meses de gastos/renda
                ref_m = indicators_cc.get("gasto_mensal_medio", renda_est)
                meses_alav_val = (saldo_tot / ref_m) if ref_m > 0 else 0.0
                fig_bar_alav = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=meses_alav_val,
                    title={'text': "Meses de Orçamento Comprometidos", 'font': {'size': 14, 'color': "#e0e0e0"}},
                    gauge={
                        'axis': {'range': [0, 15], 'tickwidth': 1, 'tickcolor': "white"},
                        'bar': {'color': "#00E5FF"},
                        'steps': [
                            {'range': [0, 2.5], 'color': "rgba(0, 230, 118, 0.25)"},
                            {'range': [2.5, 6.0], 'color': "rgba(255, 193, 7, 0.25)"},
                            {'range': [6.0, 15], 'color': "rgba(255, 82, 82, 0.25)"}
                        ],
                        'threshold': {
                            'line': {'color': "#FF5252", 'width': 3},
                            'thickness': 0.75,
                            'value': 6.0
                        }
                    }
                ))
                fig_bar_alav.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#ffffff",
                    margin=dict(l=30, r=30, t=50, b=20),
                    height=320
                )
                st.plotly_chart(fig_bar_alav, use_container_width=True)

            with st.expander("📚 **Fórmulas e Fundamentos de Estrutura de Capital (ADC)**", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("##### ⏳ Composição do Endividamento ($CE$)")
                    st.latex(r"CE = \frac{\text{Passivo Circulante (CP)}}{\text{Passivo Exigível Total (CP + LP)}}")
                    st.caption("Quanto menor o índice, mais alongado é o perfil das dívidas, reduzindo o risco de insolvência imediata.")
                with c2:
                    st.markdown("##### ⌛ Índice de Alavancagem em Meses ($IAM$)")
                    st.latex(r"IAM = \frac{\text{Saldo Residual Devedor Total}}{\text{Renda ou Gasto Mensal Médio}}")
                    st.caption("Indica quantos meses de fluxo financeiro integral seriam necessários para quitar todas as obrigações a prazo contratadas.")

        with tab_vert:
            st.markdown("##### 📊 Análise Vertical de Qualidade & Concentração dos Gastos Parcelados")
            col_v1, col_v2 = st.columns(2)

            with col_v1:
                # Distribuição por Essencialidade
                if not df_ativas.empty:
                    col_ess_name = "essencial_nao_essencial" if "essencial_nao_essencial" in df_ativas.columns else "Essencial vs. Não Essencial"
                    df_ess_agg = df_ativas.groupby(col_ess_name)["valor_restante"].sum().reset_index()
                    fig_ess = px.pie(
                        df_ess_agg,
                        names=col_ess_name,
                        values="valor_restante",
                        color=col_ess_name,
                        color_discrete_map={"Essencial": "#00E676", "Não essencial": "#FF5252", "Variável": "#FFC107"},
                        hole=0.4
                    )
                    fig_ess.update_layout(
                        title=dict(text="Análise Vertical: Essencial vs. Supérfluo", font=dict(size=14, color="#e0e0e0")),
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#ffffff",
                        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
                        margin=dict(l=20, r=20, t=50, b=30),
                        height=320
                    )
                    st.plotly_chart(fig_ess, use_container_width=True)

            with col_v2:
                # Distribuição por Categoria
                if not df_ativas.empty:
                    df_cat_agg = df_ativas.groupby("categoria")["valor_restante"].sum().reset_index().sort_values("valor_restante", ascending=False).head(5)
                    fig_cat = px.bar(
                        df_cat_agg,
                        x="valor_restante",
                        y="categoria",
                        orientation="h",
                        color="categoria",
                        text_auto=False
                    )
                    fig_cat.update_layout(
                        title=dict(text="Top 5 Categorias em Saldo Devedor Restante", font=dict(size=14, color="#e0e0e0")),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(255,255,255,0.02)",
                        font_color="#ffffff",
                        xaxis_title="Saldo Devedor (R$)",
                        yaxis_title="Categoria",
                        showlegend=False,
                        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)"),
                        yaxis=dict(showgrid=False, autorange="reversed"),
                        margin=dict(l=20, r=20, t=50, b=30),
                        height=320
                    )
                    st.plotly_chart(fig_cat, use_container_width=True)

            with st.expander("📚 **Fórmulas e Fundamentos de Análise Vertical (ADC)**", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("##### 📐 Análise Vertical de Passivos ($AV$)")
                    st.latex(r"AV_i = \frac{\text{Saldo Devedor da Categoria } i}{\text{Saldo Devedor Total}} \times 100")
                    st.caption("Identifica onde está o principal foco de alavancagem orçamentária para direcionar esforços de corte.")
                with c2:
                    st.markdown("##### 🎯 Índice de Qualidade da Dívida ($IQD$)")
                    st.latex(r"IQD = \frac{\text{Parcelas em Gastos Essenciais}}{\text{Total de Parcelas Ativas}}")
                    st.caption("Prioriza alavancagem produtiva (patrimônio, educação, saúde) em detrimento de despesas de consumo descartável.")

        with tab_balao:
            st.markdown("##### 🏢 Avaliação de Solvência para Balões & Compromissos Extraordinários")
            balao_info = indicators_cc.get("balao_compromisso")

            if balao_info:
                v_balao = balao_info["valor"]
                v_balao_fmt = "R$ ••••••" if modo_privacidade else f"R$ {v_balao:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                mes_venc = balao_info["mes_ano"]

                col_b1, col_b2, col_b3 = st.columns(3)
                with col_b1:
                    st.metric("Obrigação Futura Mapeada", balao_info["nome"])
                with col_b2:
                    st.metric("Valor a Liquidar", v_balao_fmt)
                with col_b3:
                    st.metric("Data Prevista de Vencimento", mes_venc)

                # Cálculo de aporte mensal necessário para cobrir o balão sem desinvestir ativos de longo prazo
                hoje = pd.Timestamp.now().normalize()
                try:
                    mo_b, yr_b = mes_venc.split("/")
                    dt_balao_target = pd.Timestamp(int(yr_b), int(mo_b), 1)
                    meses_restantes = max(1, (dt_balao_target.year - hoje.year) * 12 + (dt_balao_target.month - hoje.month))
                except Exception:
                    meses_restantes = 12

                aporte_sugerido = v_balao / meses_restantes
                aporte_fmt = "R$ ••••••" if modo_privacidade else f"R$ {aporte_sugerido:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                st.info(f"💡 **Plano de Amortização Programada (Sinking Fund):** Restam **{meses_restantes} meses** até o vencimento em **{mes_venc}**. Para liquidar a parcela balão integralmente sem recorrer a resgates patrimoniais forçados, o aporte mensal sugerido em Renda Fixa de Liquidez é de **{aporte_fmt}/mês**.")

                # Gráfico de evolução do Sinking Fund vs Curva do Balão
                meses_range = [hoje + pd.DateOffset(months=i) for i in range(meses_restantes + 1)]
                labels_range = [m.strftime("%m/%Y") for m in meses_range]
                fundo_acumulado = [aporte_sugerido * i for i in range(len(meses_range))]

                fig_sink = go.Figure()
                fig_sink.add_trace(go.Scatter(
                    x=labels_range,
                    y=fundo_acumulado,
                    mode="lines+markers",
                    name="Reserva Acumulada Planejada (R$)",
                    line=dict(color="#00E676", width=3),
                    marker=dict(size=6)
                ))
                fig_sink.add_hline(
                    y=v_balao, line_dash="dash", line_color="#FF5252",
                    annotation_text=f"Meta: {v_balao_fmt}", annotation_position="top right"
                )
                fig_sink.update_layout(
                    title=dict(text="Curva de Acumulação do Fundo Amortizador (Sinking Fund)", font=dict(size=14, color="#e0e0e0")),
                    hovermode="x unified",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.02)",
                    font_color="#ffffff",
                    xaxis_title="Linha do Tempo",
                    yaxis_title="Montante (R$)",
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)"),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)"),
                    margin=dict(l=40, r=20, t=50, b=40),
                    height=320
                )
                st.plotly_chart(fig_sink, use_container_width=True)

            else:
                st.info("Nenhum balão ou compromisso futuro único de grande porte identificado entre as despesas.")

            with st.expander("📚 **Fórmulas e Fundamentos de Sinking Fund & Gestão de Passivos Extraordinários**", expanded=False):
                st.markdown("##### 🏛️ Fundo Amortizador ($Sinking\\ Fund$)")
                st.latex(r"\text{Aporte Mensal} = \frac{\text{Valor Futuro da Parcela Balão}}{\text{Número de Meses até o Vencimento}}")
                st.caption("Técnica contábil de provisionamento prévio em ativos de alta liquidez e baixo risco (CDI / Selic) para neutralizar choques de liquidez na data de quitação.")
