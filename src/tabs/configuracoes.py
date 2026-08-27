import os
import sys
import datetime
import streamlit as st
import pandas as pd
from src.database import db_manager
from src.services import (
    sync_google_sheets_to_sqlite,
    sync_fundamental_data_from_yfinance,
)
from src.utils.logger import get_logger

logger = get_logger("tabs", "configuracoes")

def render_tab_configuracoes():
    """
    Renderiza a página central de Configurações do Sistema, Gerenciamento de Credenciais,
    Fontes de Dados, Sincronizações Manuais e Diagnósticos de Infraestrutura.
    """
    st.markdown('<div class="tab-header">⚙️ Configurações Globais do Sistema</div>', unsafe_allow_html=True)
    st.caption("Gerencie preferências de conexão, chaves de API, rotinas de sincronização e verifique a saúde dos serviços.")

    col1, col2 = st.columns([6, 6])

    with col1:
        # ==========================================
        # 1. FONTE DE DADOS E MODO DE OPERAÇÃO
        # ==========================================
        st.markdown("### 🗄️ Fonte de Dados")
        current_mock_state = st.session_state.get("use_mock", False)
        default_index = 0 if current_mock_state else 1

        selected_mode = st.radio(
            "Modo de Operação:",
            options=["Modo Demonstração (Dados Simulados)", "Dados Reais (Google Sheets / SQLite)"],
            index=default_index,
            help="Alterne entre visualização de demonstração e dados reais sincronizados das suas planilhas.",
            key="config_data_mode_radio"
        )
        new_mock_state = (selected_mode == "Modo Demonstração (Dados Simulados)")
        if new_mock_state != current_mock_state:
            st.session_state.use_mock = new_mock_state
            logger.info(f"Configurações: Fonte de dados alterada para {'Mock' if new_mock_state else 'Google Sheets'}")
            st.rerun()

        st.markdown("---")

        # ==========================================
        # 2. INTELIGÊNCIA ARTIFICIAL (GEMINI API)
        # ==========================================
        st.markdown("### 🤖 Inteligência Artificial (Google Gemini)")
        env_gemini_key = os.getenv("GEMINI_API_KEY", "")
        current_key = st.session_state.get("gemini_key", env_gemini_key)

        gemini_input = st.text_input(
            "Chave de API do Gemini:",
            value=current_key,
            type="password",
            help="Obtenha uma chave gratuita em https://aistudio.google.com/",
            key="config_gemini_key_input"
        )
        if gemini_input != current_key:
            st.session_state.gemini_key = gemini_input
            os.environ["GEMINI_API_KEY"] = gemini_input
            st.success("✅ Chave Gemini API atualizada na sessão!")
            logger.info("Configurações: Chave Gemini API atualizada pelo usuário.")

        if current_key:
            st.caption("🟢 Chave de API configurada.")
        else:
            st.caption("🟡 Nenhuma chave configurada. As abas de IA utilizarão respostas de aviso.")

        st.markdown("---")

        # ==========================================
        # 3. OPEN FINANCE (PLUGGY)
        # ==========================================
        st.markdown("### 🏦 Conexão Open Finance (Pluggy)")
        pluggy_id = os.getenv("PLUGGY_CLIENT_ID", "")
        pluggy_sec = os.getenv("PLUGGY_CLIENT_SECRET", "")
        if pluggy_id and pluggy_sec:
            st.caption("🟢 Credenciais Pluggy detectadas no ambiente `.env`.")
        else:
            st.caption("⚪ Credenciais Pluggy não configuradas no `.env`. Configure `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET` para ativar.")

    with col2:
        # ==========================================
        # 4. ROTINAS DE SINCRONIZAÇÃO E BANCO LOCAL
        # ==========================================
        st.markdown("### 🔄 Sincronização & Persistência Local")
        last_sync = db_manager.get_last_sync_time()
        st.info(f"🕒 **Última sincronização completa:** {last_sync if last_sync else 'Nunca sincronizado'}")

        col_sync1, col_sync2 = st.columns(2)
        with col_sync1:
            if st.button("🔄 Sincronizar Google Sheets", use_container_width=True, type="primary"):
                with st.spinner("Sincronizando planilhas com SQLite local..."):
                    try:
                        sync_google_sheets_to_sqlite()
                        st.cache_data.clear()
                        updated_sync = db_manager.get_last_sync_time()
                        st.success(f"✅ Sincronizado às **{updated_sync}**!")
                        logger.info("Configurações: Sincronização Google Sheets executada com sucesso.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na sincronização: {e}")
                        logger.error(f"Erro na sincronização Google Sheets: {e}")

        with col_sync2:
            if st.button("📊 Sincronizar Fundamentalista", use_container_width=True):
                with st.spinner("Atualizando indicadores contábeis via Yahoo Finance..."):
                    try:
                        res = sync_fundamental_data_from_yfinance()
                        if res:
                            st.success("✅ Dados fundamentalistas atualizados!")
                            logger.info("Configurações: Dados fundamentalistas atualizados com sucesso.")
                        else:
                            st.warning("⚠️ Nenhum ticker elegível ou banco vazio.")
                    except Exception as e:
                        st.error(f"Erro ao atualizar demonstrativos: {e}")
                        logger.error(f"Erro ao atualizar demonstrativos fundamentalistas: {e}")

        if st.button("🧹 Limpar Cache do Streamlit", use_container_width=True):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("✨ Cache em memória do Streamlit limpo com sucesso!")
            logger.info("Configurações: Cache do Streamlit limpo.")

        st.markdown("---")

        # ==========================================
        # 5. DIAGNÓSTICO DO AMBIENTE & SISTEMA
        # ==========================================
        st.markdown("### 🖥️ Diagnóstico do Sistema")
        db_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "data", "investimentos.db")
        creds_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "data", "credentials.json")

        diag_data = {
            "Item": [
                "Versão do Python",
                "Fuso Horário Ativo",
                "Hora do Servidor",
                "Banco SQLite Local",
                "Arquivo de Credenciais Google",
                "Porta Streamlit (.env)"
            ],
            "Status / Valor": [
                sys.version.split()[0],
                os.getenv("TZ", "America/Campo_Grande"),
                datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "✅ Encontrado" if os.path.exists(db_path) else "❌ Não encontrado",
                "✅ Encontrado" if os.path.exists(creds_path) else "❌ Não encontrado",
                os.getenv("STREAMLIT_PORT", "8502")
            ]
        }
        st.dataframe(pd.DataFrame(diag_data), width='stretch', hide_index=True)
