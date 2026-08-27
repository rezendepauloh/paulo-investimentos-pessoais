import re
import unicodedata
import pandas as pd

def normalize_text(text: str) -> str:
    """
    Normaliza texto removendo acentos, pontuação, múltiplos espaços e convertendo para minúsculas.
    Útil para comparações e geração de hashes determinísticos.
    """
    if pd.isna(text) or text is None:
        return ""
    text_str = str(text).strip().lower()
    # Remove acentos
    text_str = unicodedata.normalize("NFKD", text_str)
    text_str = "".join([c for c in text_str if not unicodedata.combining(c)])
    # Remove pontuações e caracteres especiais
    text_str = re.sub(r"[^\w\s]", "", text_str)
    # Remove múltiplos espaços
    text_str = re.sub(r"\s+", " ", text_str).strip()
    return text_str

def format_number(val, is_currency=False, currency="BRL", decimals=2, mask_privacy=False):
    """
    Formata valores numéricos para o padrão PT-BR com separadores corretos, suporte a moedas
    e modo privacidade opcional.
    """
    if mask_privacy:
        if is_currency:
            prefix = "US$" if currency == "USD" else "R$"
            return f"{prefix} ••••••"
        return "••••••"

    if pd.isna(val) or val is None:
        return ""
    try:
        val_float = float(val)
        fmt_str = f"{{:,.{decimals}f}}"
        formatted = fmt_str.format(val_float)
        
        # Inverte separadores para padrão brasileiro
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        
        if is_currency:
            if currency == "USD":
                return f"US$ {formatted}"
            return f"R$ {formatted}"
            
        return formatted
    except (ValueError, TypeError):
        return str(val)
