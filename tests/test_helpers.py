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
    try:
        return importlib.util.find_spec(pkg_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _ensure_package_stub(name: str):
    """Cria stub de pacote em sys.modules caso ainda não exista."""
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    elif not hasattr(mod, "__path__"):
        mod.__path__ = []
    return mod


def _rowcol_to_a1(row: int, col: int) -> str:
    """Converte índices (row, col) base-1 em notação A1 do Excel/Sheets."""
    letters = []
    c = int(col)
    while c > 0:
        c, rem = divmod(c - 1, 26)
        letters.append(chr(65 + rem))
    return f"{''.join(reversed(letters))}{int(row)}"


# 0. Mock seguro de streamlit caso não esteja instalado no ambiente host
if not _is_installed("streamlit"):
    mock_st = _ensure_package_stub("streamlit")
    mock_st.cache_data = lambda *a, **kw: (lambda f: f) if not a or not callable(a[0]) else a[0]
    mock_st.cache_resource = lambda *a, **kw: (lambda f: f) if not a or not callable(a[0]) else a[0]
    mock_st.session_state = {}
    mock_st.secrets = {}
    mock_st.error = MagicMock()
    mock_st.warning = MagicMock()
    mock_st.info = MagicMock()
    mock_st.success = MagicMock()
    mock_st.markdown = MagicMock()
    mock_st.stop = MagicMock()

# 1. Mock seguro de python-dotenv
if _is_installed("dotenv"):
    import dotenv  # noqa: F401
else:
    mock_dotenv = types.ModuleType("dotenv")
    mock_dotenv.load_dotenv = MagicMock(return_value=True)
    mock_dotenv.dotenv_values = MagicMock(return_value={})
    sys.modules["dotenv"] = mock_dotenv

# 2. Mock seguro de google.generativeai e google.oauth2.service_account
if _is_installed("google.generativeai"):
    import google.generativeai as genai  # noqa: F401
else:
    mock_google = _ensure_package_stub("google")
    mock_genai = _ensure_package_stub("google.generativeai")
    mock_genai.configure = MagicMock(return_value=None)
    mock_model = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"transacoes": []}'
    mock_model.generate_content = MagicMock(return_value=mock_resp)
    mock_genai.GenerativeModel = MagicMock(return_value=mock_model)
    mock_google.generativeai = mock_genai

if not _is_installed("google.oauth2.service_account"):
    mock_google = _ensure_package_stub("google")
    mock_oauth2 = _ensure_package_stub("google.oauth2")
    mock_sa = _ensure_package_stub("google.oauth2.service_account")
    mock_creds_cls = MagicMock()
    mock_creds_cls.from_service_account_file = MagicMock(return_value=MagicMock())
    mock_sa.Credentials = mock_creds_cls
    mock_oauth2.service_account = mock_sa
    mock_google.oauth2 = mock_oauth2

# 3. Mock seguro de yfinance
if _is_installed("yfinance"):
    import yfinance as yf  # noqa: F401
else:
    mock_yf = _ensure_package_stub("yfinance")
    mock_ticker = MagicMock()
    mock_yf.Ticker = MagicMock(return_value=mock_ticker)
    mock_yf.download = MagicMock()

# 4. Mock seguro de gspread (+ gspread.utils e gspread.exceptions)
if _is_installed("gspread"):
    import gspread  # noqa: F401
else:
    mock_gspread = _ensure_package_stub("gspread")
    mock_client = MagicMock()
    mock_gspread.authorize = MagicMock(return_value=mock_client)
    mock_gspread.service_account = MagicMock(return_value=mock_client)

    mock_gspread_utils = _ensure_package_stub("gspread.utils")
    mock_gspread_utils.rowcol_to_a1 = _rowcol_to_a1
    mock_gspread.utils = mock_gspread_utils

    mock_gspread_exc = _ensure_package_stub("gspread.exceptions")
    mock_gspread_exc.APIError = type("APIError", (Exception,), {})
    mock_gspread_exc.WorksheetNotFound = type("WorksheetNotFound", (Exception,), {})
    mock_gspread_exc.SpreadsheetNotFound = type("SpreadsheetNotFound", (Exception,), {})
    mock_gspread.exceptions = mock_gspread_exc

# 5. Mocks seguros de pacotes opcionais de parse/visualização quando ausentes no host
for _opt_pkg in ("ofxtools", "pypdf", "pytesseract", "pdf2image", "plotly"):
    if not _is_installed(_opt_pkg):
        _ensure_package_stub(_opt_pkg)

if not _is_installed("ofxtools.Parser") and "ofxtools" in sys.modules:
    _ofx_parser_mod = _ensure_package_stub("ofxtools.Parser")
    if not hasattr(_ofx_parser_mod, "OFXTree"):
        class _FallbackOFXTree:
            def parse(self, *args, **kwargs):
                raise ValueError("ofxtools stub parse triggers fallback")
            def convert(self):
                raise ValueError("ofxtools stub convert")
        _ofx_parser_mod.OFXTree = _FallbackOFXTree

if not _is_installed("plotly.express") and "plotly" in sys.modules:
    _px = _ensure_package_stub("plotly.express")
    _go = _ensure_package_stub("plotly.graph_objects")
    sys.modules["plotly"].express = _px
    sys.modules["plotly"].graph_objects = _go
