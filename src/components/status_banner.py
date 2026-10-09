# -*- coding: utf-8 -*-
"""
Componente visual de status e acompanhamento de tarefas em segundo plano (Accordion/Expander de Logs).
Compatível com a arquitetura dos sistemas automated-OTRS-and-CitSmart e verifica-nomes-diarios-oficiais.
Permite auto-atualização leve via @st.fragment sem recarregar a página inteira.
"""
import streamlit as st
from src.services.async_tasks import (
    is_task_running,
    get_task_logs,
    get_task_state
)

def render_async_task_expander(
    task_id: str,
    title: str = "⏳ Carregamento em Segundo Plano – Acompanhar Progresso",
    info_text: str = "Os dados estão sendo processados em segundo plano. O sistema permanece livre e responsivo para uso!"
):
    """
    Renderiza um accordion (st.expander) com as últimas linhas de log e atualização automática
    enquanto a tarefa estiver em execução. Ao finalizar, notifica suavemente.
    """
    state = get_task_state(task_id)
    if not state.get("running") and state.get("status") != "running":
        return

    with st.expander(title, expanded=False):
        st.info(info_text)

        # Utiliza st.fragment para auto-refresh suave a cada 2 segundos apenas no bloco do accordion
        @st.fragment(run_every="2s")
        def _render_logs_fragment():
            current_state = get_task_state(task_id)
            logs = get_task_logs(task_id, max_lines=25)
            
            with st.container(height=220):
                st.code(logs, language="text")

            col_btn, _ = st.columns([2.5, 7.5])
            with col_btn:
                if st.button("🔄 Atualizar Visualização", key=f"btn_refresh_async_{task_id}"):
                    st.rerun()

            # Quando terminar, dispara rerun global para atualizar os gráficos instantaneamente
            if not current_state.get("running"):
                st.toast(f"✅ {current_state.get('label', 'Processamento')} concluído com sucesso!", icon="🎉")
                st.rerun()

        _render_logs_fragment()
