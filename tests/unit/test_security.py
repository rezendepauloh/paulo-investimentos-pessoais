# -*- coding: utf-8 -*-
"""
Testes unitários de segurança defensiva, Fail-Closed Auth, Rate Limiting,
validação estrita de inputs e proteção contra Injection / DoS / XXE / Zip-Bomb.
"""
import io
import os
import time
import types
import unittest
import zipfile
from unittest.mock import patch

import tests.test_helpers  # noqa: F401
from src.database import db_manager
from src.services.analytics import is_valid_yfinance_ticker, normalize_ticker
from src.services.ingestion_parser import parse_ofx, sanitize_ofx_content
from src.services.parsers.base_parser import BaseBankParser
from src.services.pluggy_service import PluggyService
from src.utils.security import (
    AuthRateLimiter,
    AuthService,
    hash_password_pbkdf2,
    is_auth_required,
    redact_secrets,
    safe_open_pdf,
    safe_read_zip_entries,
    sanitize_html,
    sanitize_spreadsheet_cell,
    strip_xml_xxe,
    validate_host_header,
    validate_identifier,
    validate_runtime_security_config,
    validate_safe_filename,
    validate_spreadsheet_id,
    validate_ticker_symbol,
    validate_upload_bytes,
    verify_password_pbkdf2,
)


class _DummyBankParser(BaseBankParser):
    def parse_csv(self, file_bytes: bytes, filename: str = ""):
        return self.empty_dataframe()

    def parse_ofx(self, file_input, filename: str = ""):
        return self.empty_dataframe()


class TestSecurityModule(unittest.TestCase):
    def test_pbkdf2_hashing_and_verification(self):
        h1 = hash_password_pbkdf2("S3nh4SuperF0rte!2026")
        h2 = hash_password_pbkdf2("S3nh4SuperF0rte!2026")
        self.assertTrue(h1.startswith("pbkdf2_sha256$260000$"))
        self.assertNotEqual(h1, h2)  # Sal aleatório único
        self.assertTrue(verify_password_pbkdf2("S3nh4SuperF0rte!2026", h1))
        self.assertFalse(verify_password_pbkdf2("senha_errada", h1))
        self.assertFalse(verify_password_pbkdf2("", h1))
        self.assertFalse(verify_password_pbkdf2("x", "formato_invalido"))

        with self.assertRaises(ValueError):
            hash_password_pbkdf2("")

    def test_fail_closed_runtime_config(self):
        # 1. Sem variáveis (REQUIRE_AUTH omitido -> padrão é exigir auth fail-closed)
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(is_auth_required())
            ok, msg = validate_runtime_security_config()
            self.assertFalse(ok)
            self.assertIn("DASHBOARD_AUTH_PASSWORD_HASH", msg)

        # 2. Com hash inválido ou segredo fraco -> deve falhar
        with patch.dict(
            os.environ,
            {
                "REQUIRE_AUTH": "true",
                "DASHBOARD_AUTH_PASSWORD_HASH": "not_pbkdf2",
                "DASHBOARD_SESSION_SECRET": "a" * 32,
            },
            clear=True,
        ):
            ok, _ = validate_runtime_security_config()
            self.assertFalse(ok)

        valid_hash = hash_password_pbkdf2("SenhaForte!99")
        with patch.dict(
            os.environ,
            {
                "REQUIRE_AUTH": "true",
                "DASHBOARD_AUTH_PASSWORD_HASH": valid_hash,
                "DASHBOARD_SESSION_SECRET": "curto",
            },
            clear=True,
        ):
            ok, msg = validate_runtime_security_config()
            self.assertFalse(ok)
            self.assertIn("DASHBOARD_SESSION_SECRET", msg)

        # 3. Configuração completa válida -> deve aprovar
        with patch.dict(
            os.environ,
            {
                "REQUIRE_AUTH": "true",
                "DASHBOARD_AUTH_PASSWORD_HASH": valid_hash,
                "DASHBOARD_SESSION_SECRET": "s" * 40,
            },
            clear=True,
        ):
            ok, msg = validate_runtime_security_config()
            self.assertTrue(ok)
            self.assertEqual(msg, "")

        # 4. REQUIRE_AUTH=false em produção continua bloqueado (fail-closed)
        with patch.dict(
            os.environ,
            {"REQUIRE_AUTH": "false", "APP_ENV": "prod"},
            clear=True,
        ):
            ok, _ = validate_runtime_security_config()
            self.assertFalse(ok)

    def test_negative_authentication_401_and_rate_limiting_429(self):
        valid_hash = hash_password_pbkdf2("MinhaSenhaSegura#123")
        strong_secret = "segredo_hmac_com_mais_de_32_caracteres_123456"

        with patch.dict(
            os.environ,
            {
                "REQUIRE_AUTH": "true",
                "DASHBOARD_AUTH_PASSWORD_HASH": valid_hash,
                "DASHBOARD_SESSION_SECRET": strong_secret,
                "ALLOWED_HOSTS": "localhost,127.0.0.1",
            },
            clear=True,
        ):
            limiter = AuthRateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=60)
            auth = AuthService(rate_limiter=limiter)

            # Requisição sem login -> 401
            code, _ = auth.authenticate_request(headers={"Host": "localhost"}, session_token=None)
            self.assertEqual(code, 401)

            # Token forjado -> 401
            code, _ = auth.authenticate_request(headers={"Host": "localhost"}, session_token="token.forjado")
            self.assertEqual(code, 401)

            # Senha vazia -> 401
            code, _ = auth.verify_credentials("", client_key="ip1")
            self.assertEqual(code, 401)

            # 3 tentativas inválidas -> 401; a partir da 4ª tentativa bloqueia com 429
            self.assertEqual(auth.verify_credentials("errada1", client_key="ip_bf")[0], 401)
            self.assertEqual(auth.verify_credentials("errada2", client_key="ip_bf")[0], 401)
            self.assertEqual(auth.verify_credentials("errada3", client_key="ip_bf")[0], 401)
            self.assertEqual(auth.verify_credentials("errada4", client_key="ip_bf")[0], 429)
            self.assertEqual(auth.verify_credentials("MinhaSenhaSegura#123", client_key="ip_bf")[0], 429)

            # Login válido -> 200 e token válido
            code, _ = auth.verify_credentials("MinhaSenhaSegura#123", client_key="ip_ok")
            self.assertEqual(code, 200)
            token = auth.create_session_token(ttl_seconds=60)
            self.assertTrue(auth.validate_session_token(token))
            self.assertEqual(auth.authenticate_request(headers={"Host": "localhost:8502"}, session_token=token)[0], 200)

            # Host Header malicioso com token válido -> 401
            self.assertEqual(auth.authenticate_request(headers={"Host": "evil.attacker.com"}, session_token=token)[0], 401)

            # Token expirado -> 401
            self.assertFalse(auth.validate_session_token(token, now=time.time() + 120))

    def test_host_header_whitelist(self):
        self.assertTrue(validate_host_header("localhost:8502", "localhost,127.0.0.1"))
        self.assertTrue(validate_host_header("127.0.0.1:8094", "localhost,127.0.0.1"))
        self.assertFalse(validate_host_header("attacker.example.com", "localhost,127.0.0.1"))
        self.assertFalse(validate_host_header("localhost\r\nX-Injected: 1", "localhost"))

    def test_sql_identifier_and_db_manager_whitelist(self):
        self.assertEqual(validate_identifier("despesas", allowed=db_manager.ALLOWED_TABLES), "despesas")
        for bad in ["despesas; DROP TABLE ordens;--", "sqlite_master", "despesas OR 1=1", "../evil"]:
            with self.assertRaises(ValueError):
                validate_identifier(bad, allowed=db_manager.ALLOWED_TABLES)
            with self.assertRaises(ValueError):
                db_manager.get_table_data(bad)
            with self.assertRaises(ValueError):
                db_manager.clear_table(bad)

    def test_ticker_and_spreadsheet_id_whitelists(self):
        self.assertEqual(validate_ticker_symbol("PETR4"), "PETR4")
        self.assertEqual(normalize_ticker("petr4"), "PETR4.SA")
        self.assertTrue(is_valid_yfinance_ticker("HGLG11"))

        for bad_ticker in ["PETR4; rm -rf /", "<script>alert(1)</script>", "VALE 3", "A" * 25]:
            with self.assertRaises(ValueError):
                validate_ticker_symbol(bad_ticker)
            self.assertFalse(is_valid_yfinance_ticker(bad_ticker))
            self.assertEqual(normalize_ticker(bad_ticker), "")

        valid_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        self.assertEqual(validate_spreadsheet_id(valid_id), valid_id)
        for bad_id in ["short", "../../etc/passwd", "abc def", "id;drop"]:
            with self.assertRaises(ValueError):
                validate_spreadsheet_id(bad_id)

    def test_xss_and_formula_injection_sanitization(self):
        self.assertEqual(
            sanitize_html('<img src=x onerror="alert(1)">'),
            "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
        )
        self.assertEqual(sanitize_spreadsheet_cell("=CMD|' /C calc'!A0"), "'=CMD|' /C calc'!A0")
        self.assertEqual(sanitize_spreadsheet_cell("+1+1"), "'+1+1")
        self.assertEqual(sanitize_spreadsheet_cell("-1+1"), "'-1+1")
        self.assertEqual(sanitize_spreadsheet_cell("@SUM(1,1)"), "'@SUM(1,1)")
        self.assertEqual(sanitize_spreadsheet_cell("\t=1"), "'\t=1")
        self.assertEqual(sanitize_spreadsheet_cell(123.45), 123.45)
        self.assertEqual(sanitize_spreadsheet_cell(-99.5), -99.5)
        self.assertEqual(sanitize_spreadsheet_cell("Supermercado"), "Supermercado")

    def test_xxe_stripping_in_ofx(self):
        malicious_ofx = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>\n'
            "<OFX><STMTTRN><TRNAMT>-50.00</TRNAMT><MEMO>COMPRA &xxe;</MEMO></STMTTRN></OFX>"
        )
        cleaned = strip_xml_xxe(malicious_ofx)
        self.assertNotIn("<!DOCTYPE", cleaned.upper())
        self.assertNotIn("<!ENTITY", cleaned.upper())

        sanitized = sanitize_ofx_content(malicious_ofx)
        self.assertNotIn("<!DOCTYPE", sanitized.upper())
        df = parse_ofx(malicious_ofx, filename="extrato.ofx")
        self.assertIsNotNone(df)

    def test_path_traversal_zip_bomb_and_upload_validation(self):
        with self.assertRaises(ValueError):
            validate_safe_filename("../../etc/passwd")
        with self.assertRaises(ValueError):
            validate_safe_filename("nome\x00.csv")
        self.assertEqual(validate_safe_filename("pasta/sub/extrato.csv"), "extrato.csv")

        # Magic bytes inválidos para PDF e ZIP
        with self.assertRaises(ValueError):
            validate_upload_bytes(b"NOT_A_PDF", filename="fatura.pdf", allowed_extensions=[".pdf"])
        with self.assertRaises(ValueError):
            validate_upload_bytes(b"NOT_A_ZIP", filename="extrato.zip", allowed_extensions=[".zip"])

        # ZIP com Path Traversal interno
        buf_trav = io.BytesIO()
        with zipfile.ZipFile(buf_trav, "w") as zf:
            zf.writestr("../../evil.csv", "Data,Descricao,Valor\n")
        with self.assertRaises(ValueError):
            safe_read_zip_entries(buf_trav.getvalue())

        # Simulação de Zip-Bomb (alta taxa de compressão)
        buf_bomb = io.BytesIO()
        with zipfile.ZipFile(buf_bomb, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.csv", b"A" * (2 * 1024 * 1024))
        with self.assertRaises(ValueError):
            safe_read_zip_entries(buf_bomb.getvalue(), max_ratio=50)

        # BaseBankParser retorna DataFrame vazio seguro diante de Zip-Bomb
        parser = _DummyBankParser()
        with self.assertLogs("services.parsers.base", level="WARNING"):
            df_bomb = parser.parse_zip(buf_bomb.getvalue(), filename="bomb.zip")
        self.assertTrue(df_bomb.empty)

    def test_pdf_dos_page_limit(self):
        fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        fake_reader = types.SimpleNamespace(is_encrypted=False, pages=[object()] * 150)
        with patch("pypdf.PdfReader", return_value=fake_reader, create=True):
            with self.assertRaises(ValueError):
                safe_open_pdf(fake_pdf, filename="grande.pdf", max_pages=100)

    def test_secret_redaction(self):
        fake_gkey = "AIza" + "SyDummySecretKey123456789012345"
        msg = f"Falha {fake_gkey} e Bearer eyJhbGciOi.abc.def password=segredo"
        red = redact_secrets(msg)
        self.assertNotIn("DummySecretKey", red)
        self.assertNotIn("eyJhbGciOi", red)
        self.assertNotIn("segredo", red)
        self.assertIn("[REDACTED", red)

    def test_pluggy_fail_closed_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            svc = PluggyService(client_id="", client_secret="")
            with self.assertRaises(ValueError):
                svc.get_auth_token()


if __name__ == "__main__":
    unittest.main()
