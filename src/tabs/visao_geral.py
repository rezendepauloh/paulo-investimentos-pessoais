import streamlit as st
import pandas as pd
import plotly.express as px
from src.services import get_usd_brl_rate
from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("tabs", "visao_geral")

def render_tab_visao_geral(df_holdings, df_orders, df_receitas, df_despesas, df_dividendos):
    """
    Renderiza a aba de Visão Geral, Métricas Patrimoniais, Alocação de Recursos e Fluxo de Caixa.
    """
    if df_holdings.empty:
        st.warning("Nenhuma ordem ativa na carteira de investimentos.")
        return

    # Leitura dos filtros definidos na sidebar
    modo_privacidade = st.session_state.get("vg_modo_privacidade", False)
    filtro_mes_ano = st.session_state.get("vg_filtro_mes_ano", "Mais Recente (Automático)")
    classes_selecionadas = st.session_state.get("vg_classes_selecionadas", [])
    filtro_essencial = st.session_state.get("vg_essencial_filtro", "Todos os Gastos")

    # Aplica filtro de classes de ativos sobre o df_holdings
    if classes_selecionadas and "tipo" in df_holdings.columns:
        df_holdings_filtered = df_holdings[df_holdings["tipo"].isin(classes_selecionadas)]
    else:
        df_holdings_filtered = df_holdings

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

    # Aplica filtro de essencialidade nas despesas se selecionado
    if filtro_essencial == "Apenas Essenciais" and "Essencial vs. Não Essencial" in df_despesas_realized.columns:
        df_despesas_realized = df_despesas_realized[df_despesas_realized["Essencial vs. Não Essencial"].str.lower().str.contains("essencial") & ~df_despesas_realized["Essencial vs. Não Essencial"].str.lower().str.contains("não")]
    elif filtro_essencial == "Apenas Não Essenciais" and "Essencial vs. Não Essencial" in df_despesas_realized.columns:
        df_despesas_realized = df_despesas_realized[df_despesas_realized["Essencial vs. Não Essencial"].str.lower().str.contains("não")]

    # Métricas Globais (respeitando classes filtradas)
    total_market_val = df_holdings_filtered["valor_atual"].sum() if not df_holdings_filtered.empty else 0.0
    
    # Calcula o Capital Investido líquido (Aportes - Resgates/Vendas)
    total_invested = 0.0
    if not df_orders.empty:
        usd_brl_rate = get_usd_brl_rate()
        active_tickers = df_holdings_filtered["ticker"].tolist() if not df_holdings_filtered.empty else []
        for _, row in df_orders.iterrows():
            papel = str(row.get("Papel", "")).strip()
            if active_tickers and papel not in active_tickers:
                continue

            action = str(row.get("Compra/Venda", "")).strip().upper()
            val = float(row.get("Total líquido", 0))
            moeda = str(row.get("Moeda", "BRL")).strip().upper()
            qty = float(row.get("Qtd Executada", 0))
            
            # Conversão para BRL se for USD
            if moeda == "USD":
                is_planilha_em_brl = False
                if val >= 1000.0 or (qty > 0 and (val / qty) > 15.0):
                    is_planilha_em_brl = True
                val_brl = val if is_planilha_em_brl else val * usd_brl_rate
            else:
                val_brl = val
                
            if any(op in action for op in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO"]):
                total_invested += val_brl
            elif "VENDA" in action or action == "V":
                total_invested -= val_brl
    else:
        total_invested = df_holdings_filtered["total_investido"].sum() if not df_holdings_filtered.empty else 0.0
        
    total_profit = total_market_val - total_invested
    total_return_pct = (total_profit / total_invested) * 100.0 if total_invested > 0 else 0.0
    
    # Identifica o mês de análise conforme o filtro da sidebar
    target_year = pd.Timestamp.now().year
    target_month = pd.Timestamp.now().month
    
    if filtro_mes_ano and filtro_mes_ano != "Mais Recente (Automático)":
        try:
            m_part, y_part = filtro_mes_ano.split("/")
            target_month = int(m_part)
            target_year = int(y_part)
        except Exception:
            pass
    else:
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
    
    # Fluxo de caixa recente
    total_receitas = df_receitas_realized["Valor"].sum() if not df_receitas_realized.empty else 0.0
    total_despesas = df_despesas_realized["Valor"].sum() if not df_despesas_realized.empty else 0.0
    
    # Formata valores para exibição no estilo PT-BR com suporte a Modo Privacidade
    total_market_val_formatted = format_number(total_market_val, is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
    total_invested_formatted = format_number(total_invested, is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
    total_profit_formatted = format_number(abs(total_profit), is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
    total_return_pct_formatted = format_number(abs(total_return_pct), decimals=2, mask_privacy=modo_privacidade)
    saving_rate_formatted = format_number(saving_rate, is_currency=True, currency="BRL", mask_privacy=modo_privacidade)
    saving_pct_formatted = format_number(saving_pct, decimals=1, mask_privacy=modo_privacidade)
    
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
        df_sunburst = df_holdings_filtered.copy()
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
        st.plotly_chart(fig_sunburst, width='stretch')
        
    else:
        col_g1, col_g2, col_g3 = st.columns(3)
        
        with col_g1:
            st.subheader("Distribuição por Classe de Ativos")
            fig_pie_type = px.pie(
                df_holdings_filtered,
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
            if "setor_economico" in df_holdings_filtered.columns:
                df_holdings_filtered["setor_economico"] = df_holdings_filtered["setor_economico"].fillna("Outros").replace("", "Outros")
                fig_pie_sector = px.pie(
                    df_holdings_filtered,
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
                df_holdings_filtered,
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

    # Gráficos de Categorias de Receitas e Despesas
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
            st.plotly_chart(fig_desp_sun, width='stretch')
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

    # Análise de Custo de Vida e Saúde Financeira
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
                st.plotly_chart(fig_cv_sunburst, width='stretch')
                
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
                        
                        total_desp_real = df_despesas_realized["Valor"].sum()
                        essencial_val = df_despesas_realized[df_despesas_realized["Essencial vs. Não Essencial"].str.upper() == "ESSENCIAL"]["Valor"].sum()
                        pct_ess = (essencial_val / total_desp_real * 100.0) if total_desp_real > 0 else 0.0
                        st.markdown(f"**Proporção de Gastos Essenciais:** `{pct_ess:.1f}%` (Ideal: ~50% pela regra 50/30/20)")
                    else:
                        st.info("Coluna 'Essencial vs. Não Essencial' não preenchida.")

    # Histórico Mensal de Receitas, Despesas e Dividendos
    st.markdown("### 📊 Evolução Mensal de Receitas, Despesas e Dividendos")
    
    df_rec_m = df_receitas.copy() if not df_receitas.empty else pd.DataFrame()
    df_desp_m = df_despesas.copy() if not df_despesas.empty else pd.DataFrame()
    df_div_m = df_dividendos.copy() if not df_dividendos.empty else pd.DataFrame()
    
    monthly_data = []
    
    if not df_rec_m.empty and "Recebido em" in df_rec_m.columns:
        df_rec_m["Mes"] = pd.to_datetime(df_rec_m["Recebido em"]).dt.strftime("%Y-%m")
        df_grouped_rec = df_rec_m.groupby("Mes")["Valor"].sum().reset_index()
        for _, r in df_grouped_rec.iterrows():
            monthly_data.append({"Mês": r["Mes"], "Tipo": "Receitas", "Valor": r["Valor"]})
            
    if not df_desp_m.empty and "Gasto em" in df_desp_m.columns:
        df_desp_m["Mes"] = pd.to_datetime(df_desp_m["Gasto em"]).dt.strftime("%Y-%m")
        df_grouped_desp = df_desp_m.groupby("Mes")["Valor"].sum().reset_index()
        for _, r in df_grouped_desp.iterrows():
            monthly_data.append({"Mês": r["Mes"], "Tipo": "Despesas", "Valor": r["Valor"]})
            
    if not df_div_m.empty and "Recebido em" in df_div_m.columns:
        df_div_m["Mes"] = pd.to_datetime(df_div_m["Recebido em"]).dt.strftime("%Y-%m")
        df_grouped_div = df_div_m.groupby("Mes")["Valor"].sum().reset_index()
        for _, r in df_grouped_div.iterrows():
            monthly_data.append({"Mês": r["Mes"], "Tipo": "Dividendos", "Valor": r["Valor"]})
            
    if monthly_data:
        df_monthly = pd.DataFrame(monthly_data).sort_values("Mês")
        
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
        fig_monthly_bar.update_xaxes(type='category')
        fig_monthly_bar.update_traces(
            hovertemplate="<b>Mês:</b> %{x}<br><b>Valor:</b> R$ %{y:,.2f}<extra></extra>"
        )
        st.plotly_chart(fig_monthly_bar, width='stretch')
    else:
        st.info("Sem dados de receitas, despesas ou dividendos para agrupar por mês.")
