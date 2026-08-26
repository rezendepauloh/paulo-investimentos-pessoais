import pandas as pd

def format_number(val, is_currency=False, currency="BRL", decimals=2):
    """
    Formata valores numéricos para o padrão PT-BR com separadores corretos e suporte a moedas.
    """
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
    except Exception:
        return str(val)
