import streamlit as st
from ai_allocator import generate_allocation_tips

def render_tab_consultoria_ia(df_holdings, df_receitas, df_despesas, df_dividendos, df_orders):
    """
    Renderiza a aba de Consultoria Estratégica com Inteligência Artificial (Google Gemini).
    """
    st.subheader("🤖 Consultoria Estratégica com Inteligência Artificial")
    st.markdown("""
    O assistente de inteligência artificial analisa em tempo real os ativos da sua carteira, o histórico de rentabilidade 
    e o fluxo de caixa do seu orçamento para gerar um diagnóstico completo e sugerir novos aportes com segurança e eficiência.
    """)
    
    st.info("🧠 A IA do Gemini analisará sua relação Receitas vs Despesas, a taxa de poupança atual e a distribuição dos ativos para dar recomendações de alocação personalizadas baseadas no mercado financeiro brasileiro.")
    
    btn_analise = st.button("🚀 Solicitar Diagnóstico da Inteligência Artificial", key="gemini_btn")
    
    if btn_analise:
        with st.spinner("A Inteligência Artificial está analisando seus números... Isso pode levar alguns segundos."):
            relatorio = generate_allocation_tips(df_holdings, df_receitas, df_despesas, df_dividendos, df_orders=df_orders)
            
            st.markdown("---")
            st.markdown("### 📋 Diagnóstico Personalizado do Gemini")
            st.markdown(relatorio)
            st.markdown("---")
