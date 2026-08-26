import streamlit as st
import pandas as pd
import plotly.graph_objects as go

def render_tab_desempenho(df_perf):
    """
    Renderiza a aba de Desempenho Histórico e comparação com Benchmarks de Mercado.
    """
    st.subheader("📈 Evolução da Rentabilidade Acumulada vs Benchmarks")
    st.markdown("Esta visualização reconstrói a valorização percentual da sua carteira dia a dia e a compara com o CDI, IPCA (Inflação), Ibovespa e S&P 500.")
    
    if df_perf.empty:
        st.info("Sem ordens no histórico para calcular performance.")
        return

    # Seletor de período do gráfico
    col_sel1, _ = st.columns([1, 4])
    with col_sel1:
        days_option = st.selectbox(
            "Período de Análise:",
            options=["Desde o início", "Últimos 12 meses", "Últimos 6 meses", "Último mês"],
            index=0
        )
        
    # Filtra o DataFrame histórico de acordo com a opção selecionada
    df_chart = df_perf.copy()
    if not df_chart.empty:
        max_date = df_chart.index.max()
        if days_option == "Últimos 12 meses":
            df_chart = df_chart[df_chart.index >= max_date - pd.Timedelta(days=365)]
        elif days_option == "Últimos 6 meses":
            df_chart = df_chart[df_chart.index >= max_date - pd.Timedelta(days=180)]
        elif days_option == "Último mês":
            df_chart = df_chart[df_chart.index >= max_date - pd.Timedelta(days=30)]
        
    # Garante que os retornos comecem em 0% no período selecionado
    comparison_columns = [c for c in df_chart.columns if "Acumulado (%)" in c]
    for col in comparison_columns:
        base_val = df_chart[col].iloc[0]
        df_chart[f"{col} Ajustado"] = df_chart[col] - base_val
        
    fig_perf = go.Figure()
    
    # Mapeamento de cores
    colors_map = {
        "Retorno Carteira Acumulado (%) Ajustado": {"label": "Sua Carteira", "color": "#00E676", "width": 4},
        "CDI Acumulado (%) Ajustado": {"label": "CDI", "color": "#FFC107", "width": 2},
        "IPCA Acumulado (%) Ajustado": {"label": "IPCA (Inflação)", "color": "#FF5252", "width": 2},
        "IPCA + 6% Acumulado (%) Ajustado": {"label": "IPCA + 6%", "color": "#E91E63", "width": 2},
        "Ibovespa Acumulado (%) Ajustado": {"label": "Ibovespa", "color": "#00E5FF", "width": 2},
        "S&P 500 Acumulado (%) Ajustado": {"label": "S&P 500", "color": "#E040FB", "width": 2}
    }
    
    for col, settings in colors_map.items():
        if col in df_chart.columns:
            fig_perf.add_trace(go.Scatter(
                x=df_chart.index,
                y=df_chart[col],
                mode='lines',
                name=settings["label"],
                line=dict(color=settings["color"], width=settings["width"]),
                hovertemplate="%{y:.2f}%"
            ))
            
    fig_perf.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",
        xaxis_title="Data",
        yaxis_title="Ganho/Perda (%)",
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", ticksuffix="%"),
        separators=",."
    )
    
    st.plotly_chart(fig_perf, width='stretch')
    
    # Tabela resumo comparativa
    st.markdown("### 📋 Resumo Acumulado no Período Selecionado")
    resumo_dados = []
    for col, settings in colors_map.items():
        if col in df_chart.columns:
            ultimo_retorno = df_chart[col].iloc[-1]
            resumo_dados.append({
                "Benchmark / Portfólio": settings["label"],
                "Rentabilidade no Período (%)": f"{ultimo_retorno:+.2f}%"
            })
    st.table(pd.DataFrame(resumo_dados))
