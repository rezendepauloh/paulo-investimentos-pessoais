import os
from datetime import datetime
import streamlit as st
import pandas as pd
import db_manager
from data_loader import sync_google_sheets_to_sqlite, sync_fundamental_data_from_yfinance

def render_sidebar():
    """
    Renderiza a barra lateral de conexões, autenticação e sincronização.
    Retorna (use_mock, gemini_key, force_refresh).
    """
    force_refresh = False
    with st.sidebar:
        st.header("⚙️ Configurações de Conexão")
        
        # Seletor de Modo de Dados
        data_mode = st.radio(
            "Fonte de Dados:",
            ["Modo Demonstração (Dados Simulados)", "Dados Reais (Google Sheets)"],
            index=1,
            help="Alterne entre dados de teste e a integração em tempo real com suas planilhas do Google Sheets."
        )
        
        use_mock = (data_mode == "Modo Demonstração (Dados Simulados)")
        
        st.markdown("---")
        st.subheader("🤖 Inteligência Artificial")
        gemini_key = st.text_input(
            "Chave Gemini API (opcional):",
            value=os.getenv("GEMINI_API_KEY", ""),
            type="password",
            help="Necessário apenas se não estiver definida no arquivo .env"
        )
        
        st.markdown("---")
        if not use_mock:
            sync_placeholder = st.empty()
            last_sync = db_manager.get_last_sync_time()
            if last_sync and last_sync != "Nunca sincronizado":
                sync_placeholder.caption(f"🕒 Última sinc: **{last_sync}**")

            if st.button("🔄 Sincronizar Google Sheets", use_container_width=True):
                with st.spinner("Sincronizando planilhas com o banco local SQLite..."):
                    try:
                        sync_google_sheets_to_sqlite()
                        st.cache_data.clear()
                        updated_sync = db_manager.get_last_sync_time()
                        sync_placeholder.caption(f"🕒 Última sinc: **{updated_sync}**")
                        st.success(f"✅ Sincronizado com sucesso em **{updated_sync}**!")
                        force_refresh = True
                    except Exception as e:
                        st.error(f"Erro na sincronização: {e}")



            
            if st.button("📊 Atualizar Dados Fundamentalistas", use_container_width=True):
                with st.spinner("Atualizando indicadores fundamentalistas via Yahoo Finance..."):
                    try:
                        res = sync_fundamental_data_from_yfinance()
                        if res:
                            st.success("✅ Indicadores fundamentalistas atualizados com sucesso!")
                            force_refresh = True
                        else:
                            st.error("Erro ao atualizar dados fundamentalistas.")
                    except Exception as e:
                        st.error(f"Erro ao atualizar: {e}")
                        
    return use_mock, gemini_key, force_refresh


