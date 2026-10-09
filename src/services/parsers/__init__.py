# -*- coding: utf-8 -*-
"""
Dispatcher e Registry Central de Parsers Bancários.
Gerencia as instâncias de cada instituição financeira e faz o roteamento
inteligente de arquivos CSV, OFX e Comprovantes.
"""
from typing import Dict, Any, Optional
import pandas as pd
from src.services.parsers.base_parser import BaseBankParser
from src.services.parsers.generic_parser import GenericBankParser
from src.services.parsers.sicredi_parser import SicrediParser
from src.services.parsers.nubank_parser import NubankParser
from src.services.parsers.inter_parser import InterParser
from src.services.parsers.c6_parser import C6BankParser
from src.services.parsers.xp_parser import XPParser
from src.services.parsers.mercadopago_parser import MercadoPagoParser
from src.services.parsers.pay99_parser import Pay99Parser
from src.utils.logger import get_logger

logger = get_logger("services", "parsers.dispatcher")

# Registro Oficial de Instituições Suportadas
INSTITUTION_REGISTRY: Dict[str, BaseBankParser] = {
    "generic": GenericBankParser(),
    "sicredi": SicrediParser(),
    "nubank": NubankParser(),
    "inter": InterParser(),
    "c6": C6BankParser(),
    "xp": XPParser(),
    "mercadopago": MercadoPagoParser(),
    "99pay": Pay99Parser(),
}

# Opções para a UI (chave amigável -> ID do parser)
UI_INSTITUTION_OPTIONS = [
    ("Auto-Detecção (Genérico)", "generic"),
    ("Sicredi", "sicredi"),
    ("Banco Inter", "inter"),
    ("Nubank", "nubank"),
    ("C6 Bank", "c6"),
    ("XP Investimentos", "xp"),
    ("Mercado Pago", "mercadopago"),
    ("99 Pay", "99pay"),
]

def get_parser(institution_key: str = "generic") -> BaseBankParser:
    """
    Retorna a instância do parser dedicado para a chave fornecida.
    Se não encontrada, retorna o GenericBankParser com segurança.
    """
    key_clean = (institution_key or "generic").lower().replace(" ", "")
    for k, parser in INSTITUTION_REGISTRY.items():
        if k == key_clean or k in key_clean:
            return parser
    return INSTITUTION_REGISTRY["generic"]

def get_institution_guidelines(institution_key: str = "generic") -> str:
    """Retorna as instruções de exportação para a instituição selecionada."""
    parser = get_parser(institution_key)
    return getattr(parser, "guidelines", "Exporte seu extrato em formato .OFX ou .CSV.")

def parse_bank_file(
    file_bytes: bytes,
    filename: str,
    institution_key: str = "generic"
) -> pd.DataFrame:
    """
    Função despachante principal para arquivos bancários (.OFX ou .CSV).
    Roteia para o parser da instituição selecionada ou detectada.
    """
    parser = get_parser(institution_key)
    fname_low = filename.lower()

    logger.info(f"Despachando arquivo '{filename}' para parser '{parser.institution_name}' (chave: {institution_key})")

    if fname_low.endswith(".ofx"):
        return parser.parse_ofx(file_bytes, filename=filename)
    else:
        return parser.parse_csv(file_bytes, filename=filename)

__all__ = [
    "BaseBankParser",
    "GenericBankParser",
    "SicrediParser",
    "NubankParser",
    "InterParser",
    "C6BankParser",
    "XPParser",
    "MercadoPagoParser",
    "Pay99Parser",
    "INSTITUTION_REGISTRY",
    "UI_INSTITUTION_OPTIONS",
    "get_parser",
    "get_institution_guidelines",
    "parse_bank_file",
]
