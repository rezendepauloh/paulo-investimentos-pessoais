# -*- coding: utf-8 -*-
"""
Gerenciador de tarefas e carregamento assíncrono em segundo plano (Background Worker).
Permite computar tarefas pesadas (cálculo de carteira, série histórica de performance,
ingestão de cotações) em background sem congelar o Streamlit nem bloquear a navegação.
"""
import time
import threading
from typing import Dict, Any, Callable, Optional
import pandas as pd
from src.utils.logger import get_logger

logger = get_logger("services", "async_tasks")

# Registro global de tarefas em memória do processo Python
_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

def get_task_state(task_id: str) -> Dict[str, Any]:
    """Retorna o estado atual da tarefa."""
    with _LOCK:
        if task_id not in _TASKS:
            return {
                "status": "idle",
                "running": False,
                "result": None,
                "error": None,
                "logs": [],
                "start_time": 0.0,
                "end_time": 0.0,
            }
        return dict(_TASKS[task_id])

def is_task_running(task_id: str) -> bool:
    """Retorna True se a tarefa estiver sendo executada em segundo plano."""
    state = get_task_state(task_id)
    return state.get("running", False)

def get_task_result(task_id: str) -> Any:
    """Retorna o resultado já computado da tarefa, ou None se ainda não estiver pronto."""
    state = get_task_state(task_id)
    return state.get("result")

def get_task_logs(task_id: str, max_lines: int = 15) -> str:
    """Retorna as últimas N linhas de log da tarefa."""
    state = get_task_state(task_id)
    logs = state.get("logs", [])
    if not logs:
        if state.get("running"):
            return "⏳ Processando em segundo plano... Aguarde alguns instantes."
        return "Nenhum log registrado."
    return "\n".join(logs[-max_lines:])

def start_background_task(
    task_id: str,
    target_func: Callable,
    args: tuple = (),
    kwargs: Optional[dict] = None,
    task_label: str = "Tarefa"
) -> bool:
    """
    Inicia uma função em uma thread daemon separada caso ela já não esteja rodando.
    Retorna True se iniciou uma nova thread, ou False se já estava ativa.
    """
    if kwargs is None:
        kwargs = {}

    with _LOCK:
        current = _TASKS.get(task_id)
        if current and current.get("running"):
            return False  # Já está rodando

        _TASKS[task_id] = {
            "status": "running",
            "running": True,
            "label": task_label,
            "result": current.get("result") if current else None,
            "error": None,
            "logs": [f"🚀 [{time.strftime('%H:%M:%S')}] Iniciando {task_label} em segundo plano..."],
            "start_time": time.time(),
            "end_time": 0.0,
        }

    def _worker():
        t0 = time.time()
        logger.info(f"Thread assíncrona iniciada para task '{task_id}' ({task_label})")
        try:
            with _LOCK:
                _TASKS[task_id]["logs"].append(
                    f"⚙️ [{time.strftime('%H:%M:%S')}] Executando cálculos e sincronização de dados..."
                )
            
            res = target_func(*args, **kwargs)

            elapsed = round(time.time() - t0, 2)
            with _LOCK:
                _TASKS[task_id]["status"] = "success"
                _TASKS[task_id]["running"] = False
                _TASKS[task_id]["result"] = res
                _TASKS[task_id]["end_time"] = time.time()
                _TASKS[task_id]["logs"].append(
                    f"✅ [{time.strftime('%H:%M:%S')}] Concluído com sucesso em {elapsed}s!"
                )
            logger.info(f"Task '{task_id}' finalizada com sucesso em {elapsed}s")

        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            with _LOCK:
                _TASKS[task_id]["status"] = "error"
                _TASKS[task_id]["running"] = False
                _TASKS[task_id]["error"] = str(e)
                _TASKS[task_id]["end_time"] = time.time()
                _TASKS[task_id]["logs"].append(
                    f"❌ [{time.strftime('%H:%M:%S')}] Erro na execução ({elapsed}s): {e}"
                )
            logger.error(f"Erro na task assíncrona '{task_id}': {e}", exc_info=True)

    thread = threading.Thread(target=_worker, name=f"BackgroundTask_{task_id}", daemon=True)
    thread.start()
    return True
