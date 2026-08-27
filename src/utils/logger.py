import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

class SafeStreamWrapper:
    """Wrapper para streams que previne travamentos catastróficos por UnicodeEncodeError no Windows/WSL."""
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        try:
            self.stream.write(data)
        except UnicodeEncodeError:
            try:
                encoding = getattr(self.stream, "encoding", None) or "ascii"
                safe_data = data.encode(encoding, errors="replace").decode(encoding)
                self.stream.write(safe_data)
            except Exception:
                safe_data = data.encode("ascii", errors="replace").decode("ascii")
                self.stream.write(safe_data)

    def flush(self):
        if hasattr(self.stream, "flush"):
            self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)

class ANSIColoredFormatter(logging.Formatter):
    """Formatador de logging com cores ANSI automáticas baseadas no nível da mensagem para o terminal."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    COLORS = {
        logging.DEBUG: "\033[90m",                      # Cinza Escuro
        logging.INFO: "\033[36m",                       # Ciano
        logging.WARNING: "\033[33m",                    # Amarelo
        logging.ERROR: "\033[31m\033[1m",               # Vermelho Negrito
        logging.CRITICAL: "\033[41m\033[37m\033[1m",    # Fundo Vermelho / Texto Branco Negrito
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        log_fmt = f"{color}[%(asctime)s] [%(levelname)s] [%(name)s]{self.RESET} %(message)s"
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def get_logger(category: str, module_name: str) -> logging.Logger:
    """
    Retorna um logger configurado com gravação rotativa em subpasta (logs/<category>/<module_name>.log)
    e saída colorida no terminal.
    
    - Limite por arquivo: 3 MB
    - BackupCount: 3 arquivos de histórico (descarta os mais antigos automaticamente)
    """
    category_dir = LOGS_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = category_dir / f"{module_name}.log"
    logger_name = f"{category}.{module_name}"
    logger = logging.getLogger(logger_name)
    
    # Evita duplicação de handlers se já configurado
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # 1. Handler para Arquivo (Log puro em disco sem códigos ANSI, 3MB e 3 backups)
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=3 * 1024 * 1024,  # 3 MB
        backupCount=3,             # Mantém 3 arquivos de histórico
        encoding='utf-8'
    )
    plain_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(plain_formatter)
    file_handler.setLevel(logging.INFO)
    
    # 2. Handler para Terminal (Console com Cores ANSI e proteção Unicode)
    safe_stdout = SafeStreamWrapper(sys.stdout)
    stream_handler = logging.StreamHandler(safe_stdout)
    color_formatter = ANSIColoredFormatter()
    stream_handler.setFormatter(color_formatter)
    stream_handler.setLevel(logging.INFO)
    
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    
    return logger
