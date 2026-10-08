# -*- coding: utf-8 -*-
"""
Helper universal de testes para o Paulo Investimentos Pessoais.
Garante mocks seguros e transparentes de dependências de terceiros e APIs externas
(google.generativeai, yfinance, gspread, pluggy, dotenv, etc.),
permitindo que a suíte inteira rode com 100% de confiabilidade e isolamento tanto no host local
quanto dentro do contêiner Docker.
"""

import importlib.util
import sys
import types
from unittest.mock import MagicMock

def _is_installed(pkg_name: str) -> bool:
    """Verifica se um pacote está instalado sem emitir avisos de import estático para o LSP da IDE."""
    return importlib.util.find_spec(pkg_name) is not None

# 1. Mock seguro de python-dotenv
if _is_installed("dotenv"):
    import dotenv  # noqa: F401
else:
    mock_dotenv = types.ModuleType("dotenv")
    mock_dotenv.load_dotenv = MagicMock(return_value=True)
    mock_dotenv.dotenv_values = MagicMock(return_value={})
    sys.modules["dotenv"] = mock_dotenv

# 2. Mock seguro de google.generativeai
if _is_installed("google.generativeai"):
    import google.generativeai as genai  # noqa: F401
else:
    mock_genai = types.ModuleType("google.generativeai")
    mock_genai.configure = MagicMock(return_value=None)
    mock_model = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"transacoes": []}'
    mock_model.generate_content = MagicMock(return_value=mock_resp)
    mock_genai.GenerativeModel = MagicMock(return_value=mock_model)
    sys.modules["google.generativeai"] = mock_genai

# 3. Mock seguro de yfinance
if _is_installed("yfinance"):
    import yfinance as yf  # noqa: F401
else:
    mock_yf = types.ModuleType("yfinance")
    mock_ticker = MagicMock()
    mock_yf.Ticker = MagicMock(return_value=mock_ticker)
    mock_yf.download = MagicMock()
    sys.modules["yfinance"] = mock_yf

# 4. Mock seguro de gspread
if _is_installed("gspread"):
    import gspread  # noqa: F401
else:
    mock_gspread = types.ModuleType("gspread")
    mock_client = MagicMock()
    mock_gspread.authorize = MagicMock(return_value=mock_client)
    mock_gspread.service_account = MagicMock(return_value=mock_client)
    sys.modules["gspread"] = mock_gspread
