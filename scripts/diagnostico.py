import os
import sys
import re
import json
import datetime
import logging
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv(dotenv_path="../.env", override=True)
from logging.handlers import RotatingFileHandler

# Adiciona o diretório raiz ao sys.path para permitir importações dos módulos principais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Garante a existência da pasta de logs
os.makedirs("../logs", exist_ok=True)

# Configuração do Logger Rotativo (máximo 3 arquivos de 3MB)
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_file = "../logs/scripts.log"
log_handler = RotatingFileHandler(log_file, maxBytes=3 * 1024 * 1024, backupCount=2, encoding="utf-8")
log_handler.setFormatter(log_formatter)

logger = logging.getLogger("Diagnostico")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Adiciona saída para console também
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

logger.info("=== INICIANDO DIAGNÓSTICO DA CARTEIRA HISTÓRICA ===")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.services import get_orders_data, normalize_ticker
    import yfinance as yf
except Exception as e:
    logger.error(f"Erro ao importar dependências: {e}")
    sys.exit(1)


# 1. Carrega ordens
try:
    df_orders = get_orders_data(use_mock=False)
except Exception as e:
    logger.error(f"Erro ao carregar os dados da planilha de ordens: {e}")
    sys.exit(1)

if df_orders.empty:
    logger.error("A planilha de ordens está vazia ou não pôde ser carregada!")
    sys.exit(1)

logger.info(f"Total de ordens carregadas da planilha: {len(df_orders)}")

# 2. Filtra e exibe
df = df_orders.dropna(subset=["data envio"]).sort_values("data envio").copy()
logger.info(f"Total de ordens válidas cronológicas: {len(df)}")

# 3. Analisa especificamente as bonificações de ativos conhecidos
logger.info("Analisando desdobramentos e bonificações na memória do Python...")
df_bonificacoes = df[df["Compra/Venda"].str.upper().str.contains("DESDOBRAMENTO|BONIFICACAO|BONIFICAÇÃO")].copy()

if df_bonificacoes.empty:
    logger.info("Nenhuma bonificação encontrada na memória!")
else:
    correcoes_conhecidas = {}
    correcoes_env = os.getenv("CORRECOES_CONHECIDAS", "{}")
    try:
        correcoes_dict = json.loads(correcoes_env)
        correcoes_conhecidas = {tuple(k.split("|")): float(v) for k, v in correcoes_dict.items()}
    except Exception as e:
        logger.error(f"Erro ao carregar CORRECOES_CONHECIDAS do .env: {e}")

    ativos_alvo = list(set([k[0] for k in correcoes_conhecidas.keys()])) if correcoes_conhecidas else ["EZTC3"]
    cols_bonif = ["data envio", "Compra/Venda", "Papel", "Qtd Executada", "Preço médio", "Total líquido", "Moeda"]
    df_alvo = df_bonificacoes[df_bonificacoes["Papel"].isin(ativos_alvo)].sort_values("data envio")
    
    logger.info(f"\n--- Bonificações de Ativos Alvo ---\n{df_alvo[cols_bonif].to_string(index=False)}")
    
    if ("EZTC3", "29/04/2019") in correcoes_conhecidas:
        logger.info("\n--- Detalhes específicos de EZTC3 (29/04/2019) ---")
        df_eztc = df_alvo[(df_alvo["Papel"] == "EZTC3") & (df_alvo["data envio"].dt.strftime("%d/%m/%Y") == "29/04/2019")]
        if not df_eztc.empty:
            qtd_eztc = df_eztc.iloc[0]["Qtd Executada"]
            logger.info(f"Quantidade lida para EZTC3 em 29/04/2019: {qtd_eztc} (Tipo: {type(qtd_eztc)})")
        else:
            logger.warning("Bonificação de EZTC3 de 29/04/2019 não encontrada no DataFrame de ordens!")

logger.info("=== DIAGNÓSTICO CONCLUÍDO COM SUCESSO ===")
