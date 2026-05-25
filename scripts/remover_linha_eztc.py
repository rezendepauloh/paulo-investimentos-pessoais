import os
import sys
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

logger = logging.getLogger("RemoverLinhaEztc")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Adiciona saída para console também
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

logger.info("=== DELETANDO LINHA DE BONIFICAÇÃO DISTORCIDA (EZTC3) ===")

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
    idx_data = headers.index("Data envio")
    
    remover_ticker = os.getenv("REMOVER_TICKER", "EZTC3")
    remover_data = os.getenv("REMOVER_DATA", "10/12/2025")
    
    logger.info(f"Localizando a linha de bonificação de {remover_ticker} de {remover_data}...")
    linha_encontrada = None
    
    for row_idx, row in enumerate(all_values[1:], start=2):
        op = str(row[idx_tipo_op]).strip().upper()
        papel = str(row[idx_papel]).strip().upper()
        data_envio = str(row[idx_data]).strip()
        
        if papel == remover_ticker and ("BONIFICAÇÃO" in op or "BONIFICACAO" in op) and remover_data in data_envio:
            linha_encontrada = row_idx
            break
            
    if not linha_encontrada:
        logger.info(f"A linha de bonificação de {remover_ticker} de {remover_data} não foi encontrada na planilha!")
    else:
        worksheet.delete_rows(linha_encontrada)
        logger.info(f" ✅ Linha {linha_encontrada} de {remover_ticker} deletada com sucesso diretamente na planilha do Google Sheets!")
        
except Exception as e:
    logger.error(f"Erro ao conectar ou atualizar o Google Sheets: {e}")

logger.info("=== CONCLUÍDO ===")
