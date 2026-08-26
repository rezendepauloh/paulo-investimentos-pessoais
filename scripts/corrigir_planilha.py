import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Adiciona o diretório raiz ao sys.path para permitir importações dos módulos principais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Garante a existência da pasta de logs
os.makedirs("../logs", exist_ok=True)

# Configuração do Logger Rotativo (máximo 3 arquivos de 3MB)
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_file = "../logs/scripts.log"
log_handler = RotatingFileHandler(log_file, maxBytes=3 * 1024 * 1024, backupCount=2, encoding="utf-8")
log_handler.setFormatter(log_formatter)

logger = logging.getLogger("CorretorPlanilha")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Adiciona saída para console também
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

logger.info("=== INICIANDO CORREÇÃO CIRÚRGICA NO GOOGLE SHEETS ===")

load_dotenv(dotenv_path="../.env", override=True)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

orders_id = os.getenv("SPREADSHEET_ORDERS_ID")
creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "../credentials.json")

if not os.path.exists(creds_path) and os.path.exists("credentials.json"):
    creds_path = "credentials.json"

if not orders_id:
    logger.error("Erro: SPREADSHEET_ORDERS_ID não configurado no arquivo .env!")
    sys.exit(1)

if not os.path.exists(creds_path):
    logger.error(f"Erro: Arquivo de credenciais '{creds_path}' não encontrado!")
    sys.exit(1)

try:
    credentials = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(orders_id)
    worksheet = spreadsheet.get_worksheet(0)
    
    logger.info(f"Conectado com sucesso à planilha: '{spreadsheet.title}'")
    
    all_values = worksheet.get_all_values()
    headers = all_values[0]
    
    idx_tipo_op = headers.index("Compra/Venda")
    idx_papel = headers.index("Papel")
    idx_qtd = headers.index("Qtd Executada")
    idx_data = headers.index("Data envio")
    
    logger.info("Analisando linhas da planilha do Google Sheets...")
    correcoes_conhecidas = {}
    correcoes_env = os.getenv("CORRECOES_CONHECIDAS", "{}")
    try:
        correcoes_dict = json.loads(correcoes_env)
        correcoes_conhecidas = {tuple(k.split("|")): float(v) for k, v in correcoes_dict.items()}
    except Exception as e:
        logger.error(f"Erro ao carregar CORRECOES_CONHECIDAS do .env: {e}")

    correcoes = []
    
    for row_idx, row in enumerate(all_values[1:], start=2):
        op = str(row[idx_tipo_op]).strip().upper()
        papel = str(row[idx_papel]).strip().upper()
        data_envio = str(row[idx_data]).strip()
        
        if "BONIFICAÇÃO" in op or "BONIFICACAO" in op or "DESDOBRAMENTO" in op:
            data_envio_limpa = data_envio.split(" ")[0].strip()
            if "-" in data_envio_limpa:
                parts = data_envio_limpa.split("-")
                if len(parts) == 3:
                    data_envio_limpa = f"{parts[2]}/{parts[1]}/{parts[0]}"
            
            chave = (papel, data_envio_limpa)
            if chave in correcoes_conhecidas:
                val_correto_num = correcoes_conhecidas[chave]
                # Converte o separador decimal para vírgula (Google Sheets em PT-BR)
                val_correto_str = str(val_correto_num).replace('.', ',')
                correcoes.append((row_idx, idx_qtd + 1, val_correto_str, f"{papel} ({val_correto_str})"))
                
    if not correcoes:
        logger.info("Nenhuma linha inconsistente de desdobramento/bonificação foi encontrada para correção!")
    else:
        logger.info(f"Encontradas {len(correcoes)} células para correção dinâmica. Aplicando...")
        for row_num, col_num, val_correto, descricao in correcoes:
            worksheet.update_cell(row_num, col_num, val_correto)
            logger.info(f" ✅ Linha {row_num}: Quantidade de {descricao} corrigida para decimal '{val_correto}'")
            
        logger.info("🎉 Todas as inconsistências foram corrigidas diretamente no seu Google Sheets com sucesso!")
        
except Exception as e:
    logger.error(f"Erro ao conectar ou atualizar o Google Sheets: {e}")

logger.info("=== CONCLUÍDO ===")
