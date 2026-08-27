import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from src.utils.logger import get_logger

logger = get_logger("tabs", "desempenho")

def render_tab_desempenho(df_perf):
    """
    Renderiza a aba de Desempenho Histórico e comparação com Benchmarks de Mercado.
    """
    st.subheader("📈 Evolução da Rentabilidade Acumulada vs Benchmarks")
    st.markdown("Esta visualização reconstrói a valorização percentual da sua carteira dia a dia e a compara com o CDI, IPCA (Inflação), Ibovespa e S&P 500.")
    
    if df_perf.empty:
        st.info("Sem ordens no histórico para calcular performance.")
        return

    # Lê os filtros da sidebar
    days_option = st.session_state.get("perf_periodo", "Desde o início")
    benchmarks_ativos = st.session_state.get("perf_benchmarks_selecionados", ["CDI", "IPCA (Inflação)", "IPCA + 6%", "Ibovespa", "S&P 500"])
        
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
    
    # Mapeamento de cores e labels
    colors_map = {
        "Retorno Carteira Acumulado (%) Ajustado": {"label": "Sua Carteira", "color": "#00E676", "width": 4, "is_carteira": True},
        "CDI Acumulado (%) Ajustado": {"label": "CDI", "color": "#FFC107", "width": 2, "bench_name": "CDI"},
        "IPCA Acumulado (%) Ajustado": {"label": "IPCA (Inflação)", "color": "#FF5252", "width": 2, "bench_name": "IPCA (Inflação)"},
        "IPCA + 6% Acumulado (%) Ajustado": {"label": "IPCA + 6%", "color": "#E91E63", "width": 2, "bench_name": "IPCA + 6%"},
        "Ibovespa Acumulado (%) Ajustado": {"label": "Ibovespa", "color": "#00E5FF", "width": 2, "bench_name": "Ibovespa"},
        "S&P 500 Acumulado (%) Ajustado": {"label": "S&P 500", "color": "#E040FB", "width": 2, "bench_name": "S&P 500"}
    }
    
    for col, settings in colors_map.items():
        if col in df_chart.columns:
            # Sempre exibe a carteira; benchmarks dependem do multi-select
            if settings.get("is_carteira", False) or settings.get("bench_name") in benchmarks_ativos:
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
    
    # Tabela resumo comparativa (exibe apenas a carteira e os benchmarks selecionados)
    st.markdown("### 📋 Resumo Acumulado no Período Selecionado")
    resumo_dados = []
    for col, settings in colors_map.items():
        if col in df_chart.columns:
            if settings.get("is_carteira", False) or settings.get("bench_name") in benchmarks_ativos:
                ultimo_retorno = df_chart[col].iloc[-1]
                resumo_dados.append({
                    "Benchmark / Portfólio": settings["label"],
                    "Rentabilidade no Período (%)": f"{ultimo_retorno:+.2f}%"
                })
    if resumo_dados:
        st.dataframe(pd.DataFrame(resumo_dados), width='stretch', hide_index=True)

