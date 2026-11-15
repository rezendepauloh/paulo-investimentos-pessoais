# -*- coding: utf-8 -*-
"""
Módulo Central de Segurança, Autenticação Fail-Closed, Sanitização e Defesa contra DoS/Injection.
"""
import hashlib
import hmac
import html
import io
import os
import re
import secrets
import time
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Limites defensivos padrão contra DoS / Bombs
MAX_UPLOAD_BYTES = 15 * 1024 * 1024        # 15 MB por arquivo enviado
MAX_ZIP_ENTRIES = 50                       # Máximo de arquivos dentro de um ZIP
MAX_ZIP_ENTRY_BYTES = 20 * 1024 * 1024     # 20 MB descomprimido por entrada
MAX_ZIP_TOTAL_BYTES = 50 * 1024 * 1024     # 50 MB descomprimido total
MAX_ZIP_RATIO = 100                        # Taxa máxima de compressão permitida
MAX_PDF_PAGES = 100                        # Limite de páginas por PDF
MAX_IMAGE_PIXELS = 25_000_000              # 25 MPx (previne DecompressionBomb no Pillow/OCR)
MAX_HTTP_RESPONSE_BYTES = 10 * 1024 * 1024 # 10 MB para respostas HTTP externas

# Whitelists estritas (Regex)
RE_SQL_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
RE_TICKER = re.compile(r"^[A-Z0-9^.=/-]{1,20}$")
RE_SPREADSHEET_ID = re.compile(r"^[a-zA-Z0-9_-]{10,128}$")
RE_HOST = re.compile(r"^[a-zA-Z0-9._:-]{1,253}$")

# Prefixos perigosos de Formula Injection em planilhas (CSV/Google Sheets)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Padrões de segredos para redação em logs e mensagens de erro
_SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"sk-[0-9A-Za-z_-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ghp_[0-9A-Za-z]{20,}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"(clientSecret|api_key|apiKey|password|senha|token)\s*[:=]\s*['\"]?[^\s'\",;}]+", re.IGNORECASE), r"\1=[REDACTED]"),
]


def redact_secrets(text: Any) -> str:
    """Remove ou mascara possíveis credenciais, tokens e senhas antes de gravar em logs ou UI."""
    if text is None:
        return ""
    msg = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


def sanitize_html(value: Any) -> str:
    """Escapa caracteres HTML para prevenir XSS ao renderizar blocos HTML no Streamlit."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def sanitize_spreadsheet_cell(value: Any) -> Any:
    """
    Neutraliza Formula Injection (CSV/Google Sheets Injection) em células gravadas com USER_ENTERED.
    Preserva números puros e prefixa apóstrofo em strings iniciadas por =, +, -, @, TAB ou CR.
    """
    if value is None or isinstance(value, (int, float, bool)):
        return value
    s = str(value)
    if s and s[0] in _FORMULA_PREFIXES:
        return f"'{s}"
    return s


def validate_identifier(identifier: str, allowed: Optional[Iterable[str]] = None) -> str:
    """Valida identificador SQL (tabela/coluna) contra regex estrita e whitelist opcional."""
    if not isinstance(identifier, str) or not RE_SQL_IDENTIFIER.match(identifier):
        raise ValueError(f"Identificador SQL inválido: {identifier!r}")
    if allowed is not None and identifier not in set(allowed):
        raise ValueError(f"Identificador SQL fora da whitelist permitida: {identifier!r}")
    return identifier


def validate_ticker_symbol(ticker: str) -> str:
    """Valida ticker financeiro contra whitelist estrita de caracteres permitidos."""
    if not isinstance(ticker, str):
        raise ValueError("Ticker deve ser string.")
    cleaned = ticker.strip().upper()
    if not RE_TICKER.match(cleaned):
        raise ValueError(f"Ticker inválido ou fora da whitelist: {ticker!r}")
    return cleaned


def validate_spreadsheet_id(spreadsheet_id: str) -> str:
    """Valida formato do ID de planilha Google Sheets."""
    if not isinstance(spreadsheet_id, str) or not RE_SPREADSHEET_ID.match(spreadsheet_id.strip()):
        raise ValueError("ID de planilha Google Sheets inválido.")
    return spreadsheet_id.strip()


def validate_safe_filename(filename: str) -> str:
    """Valida e normaliza nome de arquivo prevenindo Path Traversal e bytes nulos."""
    if not filename or "\x00" in filename:
        raise ValueError("Nome de arquivo inválido.")
    normalized = filename.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"Path traversal detectado no nome de arquivo: {filename!r}")
    base = parts[-1] if parts else ""
    if not base or base in (".", ".."):
        raise ValueError("Nome de arquivo vazio após sanitização.")
    return base


def strip_xml_xxe(content_str: str) -> str:
    """Remove declarações DOCTYPE e ENTITY para mitigar XXE / Billion Laughs em parsers SGML/XML."""
    if not content_str:
        return ""
    cleaned = re.sub(r"<!DOCTYPE[^>]*(\[[^\]]*\])?\s*>", "", content_str, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<!ENTITY[^>]*>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned


def validate_upload_bytes(
    file_bytes: bytes,
    filename: str = "",
    allowed_extensions: Optional[Iterable[str]] = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> bytes:
    """
    Valida tamanho máximo, extensão permitida, path traversal e magic bytes básicos de uploads.
    """
    if not isinstance(file_bytes, (bytes, bytearray)) or len(file_bytes) == 0:
        raise ValueError("Arquivo enviado está vazio ou em formato inválido.")
    if len(file_bytes) > max_bytes:
        raise ValueError(
            f"Arquivo excede o limite máximo permitido de {max_bytes // (1024 * 1024)} MB."
        )

    safe_name = validate_safe_filename(filename) if filename else ""
    ext = os.path.splitext(safe_name)[1].lower() if safe_name else ""

    if allowed_extensions is not None:
        allowed_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in allowed_extensions}
        if ext and ext not in allowed_set:
            raise ValueError(f"Extensão de arquivo não permitida: {ext}")

    # Validação básica de magic bytes para formatos binários conhecidos
    data = bytes(file_bytes)
    if ext == ".pdf" and not data.lstrip().startswith(b"%PDF-"):
        raise ValueError("Assinatura binária inválida para arquivo PDF.")
    if ext == ".zip" and not data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        raise ValueError("Assinatura binária inválida para arquivo ZIP.")
    if ext == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Assinatura binária inválida para imagem PNG.")
    if ext in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("Assinatura binária inválida para imagem JPEG.")

    return data


def safe_read_zip_entries(
    file_bytes: bytes,
    password_candidates: Optional[List[str]] = None,
    allowed_inner_extensions: Optional[Iterable[str]] = None,
    max_zip_bytes: int = MAX_UPLOAD_BYTES,
    max_entries: int = MAX_ZIP_ENTRIES,
    max_entry_bytes: int = MAX_ZIP_ENTRY_BYTES,
    max_total_bytes: int = MAX_ZIP_TOTAL_BYTES,
    max_ratio: int = MAX_ZIP_RATIO,
) -> List[Tuple[str, bytes]]:
    """
    Extrai arquivos de um ZIP em memória com proteção estrita contra:
    - Zip-Bomb / Decompression Bomb (tamanho por entrada, tamanho total, ratio e leitura em streaming limitada)
    - Path Traversal em nomes internos
    - Excesso de entradas
    """
    validate_upload_bytes(file_bytes, filename="archive.zip", allowed_extensions=[".zip"], max_bytes=max_zip_bytes)

    pwds = list(password_candidates or [])
    if "" not in pwds:
        pwds.append("")

    allowed_exts = (
        {e.lower() if e.startswith(".") else f".{e.lower()}" for e in allowed_inner_extensions}
        if allowed_inner_extensions is not None
        else None
    )

    extracted: List[Tuple[str, bytes]] = []
    total_uncompressed = 0

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        infos = [
            info for info in zf.infolist()
            if not info.is_dir() and not info.filename.startswith("__MACOSX")
        ]
        if len(infos) > max_entries:
            raise ValueError(f"Arquivo ZIP excede o limite máximo de {max_entries} arquivos internos.")

        for info in infos:
            safe_inner_name = validate_safe_filename(info.filename)
            inner_ext = os.path.splitext(safe_inner_name)[1].lower()
            if allowed_exts is not None and inner_ext not in allowed_exts:
                continue

            if info.file_size > max_entry_bytes:
                raise ValueError(f"Entrada '{safe_inner_name}' excede limite de tamanho descomprimido.")

            comp_size = max(1, info.compress_size)
            if info.file_size > 0 and (info.file_size / comp_size) > max_ratio:
                raise ValueError(f"Taxa de compressão suspeita (possível Zip-Bomb) em '{safe_inner_name}'.")

            if total_uncompressed + info.file_size > max_total_bytes:
                raise ValueError("Tamanho total descomprimido do ZIP excede o limite de segurança.")

            entry_bytes = None
            for pwd in pwds:
                pwd_b = pwd.encode("utf-8") if pwd else None
                try:
                    with zf.open(info, "r", pwd=pwd_b) as member:
                        chunks = []
                        read_so_far = 0
                        while True:
                            chunk = member.read(65536)
                            if not chunk:
                                break
                            read_so_far += len(chunk)
                            if read_so_far > max_entry_bytes or (total_uncompressed + read_so_far) > max_total_bytes:
                                raise ValueError("Zip-Bomb detectado durante leitura em streaming.")
                            if (read_so_far / comp_size) > max_ratio and read_so_far > 1024 * 1024:
                                raise ValueError("Taxa de descompressão em streaming excedeu limite de segurança.")
                            chunks.append(chunk)
                        entry_bytes = b"".join(chunks)
                        total_uncompressed += len(entry_bytes)
                    break
                except RuntimeError:
                    # Senha incorreta para esta entrada; tenta próxima candidata
                    continue

            if entry_bytes is not None:
                extracted.append((safe_inner_name, entry_bytes))

    return extracted


def safe_open_image(file_bytes: bytes, max_bytes: int = MAX_UPLOAD_BYTES, max_pixels: int = MAX_IMAGE_PIXELS):
    """Abre imagem via PIL com proteção contra Decompression Bomb (MAX_IMAGE_PIXELS) e verificação de integridade."""
    from PIL import Image

    validate_upload_bytes(file_bytes, max_bytes=max_bytes)
    Image.MAX_IMAGE_PIXELS = max_pixels
    img_check = Image.open(io.BytesIO(file_bytes))
    img_check.verify()
    img = Image.open(io.BytesIO(file_bytes))
    if img.width * img.height > max_pixels:
        raise ValueError(f"Imagem excede limite de {max_pixels} pixels.")
    return img


def safe_open_pdf(
    file_bytes: bytes,
    filename: str = "",
    password: str = "",
    password_env_keys: Optional[List[str]] = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_pages: int = MAX_PDF_PAGES,
):
    """Abre PDF via pypdf com limite de tamanho, descriptografia controlada e teto de páginas contra DoS."""
    import pypdf

    validate_upload_bytes(file_bytes, filename=filename or "document.pdf", allowed_extensions=[".pdf"], max_bytes=max_bytes)
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))

    if reader.is_encrypted:
        candidates: List[str] = []
        if password and password.strip():
            candidates.append(password.strip())
        for env_k in (password_env_keys or []):
            val = os.getenv(env_k, "").strip()
            if val and val not in candidates:
                candidates.append(val)

        decrypted = False
        for pwd in candidates:
            try:
                if reader.decrypt(pwd):
                    decrypted = True
                    break
            except Exception:
                continue

        if not decrypted:
            # Tenta senha vazia somente quando nenhuma senha foi exigida explicitamente
            try:
                if reader.decrypt(""):
                    decrypted = True
            except Exception:
                pass

        if not decrypted:
            raise PermissionError("PDF protegido por senha; credencial ausente ou inválida.")

    if len(reader.pages) > max_pages:
        raise ValueError(f"PDF excede o limite de segurança de {max_pages} páginas.")

    return reader


# =============================================================================
# AUTENTICAÇÃO FAIL-CLOSED, HASHING PBKDF2, TOKENS HMAC E RATE LIMITING
# =============================================================================

def hash_password_pbkdf2(password: str, iterations: int = 260_000, salt: Optional[str] = None) -> str:
    """Gera hash seguro PBKDF2-HMAC-SHA256 no formato pbkdf2_sha256$<iters>$<salt_hex>$<digest_hex>."""
    if not password:
        raise ValueError("Senha não pode ser vazia.")
    salt_hex = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
    return f"pbkdf2_sha256${iterations}${salt_hex}${dk.hex()}"


def verify_password_pbkdf2(password: str, stored_hash: str) -> bool:
    """Verifica senha contra hash PBKDF2-HMAC-SHA256 em tempo constante."""
    if not password or not stored_hash:
        return False
    try:
        cleaned = stored_hash.strip()
        sep = ":" if ":" in cleaned and "$" not in cleaned else "$"
        parts = cleaned.split(sep)
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        if iterations < 100_000:
            return False
        salt_bytes = bytes.fromhex(parts[2])
        expected_hex = parts[3]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
        return hmac.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False


def validate_host_header(host: str, allowed_hosts_env: Optional[str] = None) -> bool:
    """
    Valida o cabeçalho Host contra lista branca configurada em ALLOWED_HOSTS (ou localhost/127.0.0.1).
    Previne ataques de Host Header Injection / DNS Rebinding.
    """
    if not host or not isinstance(host, str):
        return False
    host_clean = host.strip().lower().split(":")[0]
    if not RE_HOST.match(host.strip()):
        return False
    raw_allowed = allowed_hosts_env if allowed_hosts_env is not None else os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,::1")
    allowed = {h.strip().lower().split(":")[0] for h in raw_allowed.split(",") if h.strip()}
    if not allowed:
        allowed = {"localhost", "127.0.0.1", "::1"}
    return host_clean in allowed


def is_auth_required() -> bool:
    """
    Determina se a autenticação é obrigatória.
    Fail-Closed: em produção (APP_ENV=prod/production) é SEMPRE obrigatória,
    e por padrão também ativa se REQUIRE_AUTH != 'false'.
    """
    app_env = os.getenv("APP_ENV", "dev").strip().lower()
    if app_env in ("prod", "production"):
        return True
    req_auth = os.getenv("REQUIRE_AUTH", "true").strip().lower()
    return req_auth not in ("0", "false", "no", "off")


def validate_runtime_security_config() -> Tuple[bool, str]:
    """
    Valida configuração de segurança em modo Fail-Closed.
    Retorna (ok, mensagem_erro). Serviços/UI não devem iniciar se retornar False.
    """
    if not is_auth_required():
        return True, ""

    pwd_hash = os.getenv("DASHBOARD_AUTH_PASSWORD_HASH", "").strip()
    pwd_plain = os.getenv("DASHBOARD_ACCESS_PASSWORD", "").strip()
    session_secret = os.getenv("DASHBOARD_SESSION_SECRET", "").strip()

    if not pwd_hash and not pwd_plain:
        return (
            False,
            "Bloqueio Fail-Closed: Autenticação obrigatória ativa, mas nenhuma credencial "
            "(DASHBOARD_AUTH_PASSWORD_HASH ou DASHBOARD_ACCESS_PASSWORD) foi definida no .env."
        )

    if pwd_plain and len(pwd_plain) < 10 and not pwd_hash:
        return (
            False,
            "Bloqueio Fail-Closed: DASHBOARD_ACCESS_PASSWORD deve ter pelo menos 10 caracteres."
        )

    if pwd_hash and not pwd_hash.startswith(("pbkdf2_sha256$", "pbkdf2_sha256:")):
        return (
            False,
            "Bloqueio Fail-Closed: DASHBOARD_AUTH_PASSWORD_HASH possui formato inválido (esperado pbkdf2_sha256$...)."
        )

    if not session_secret or len(session_secret) < 16:
        return (
            False,
            "Bloqueio Fail-Closed: DASHBOARD_SESSION_SECRET ausente ou menor que 16 caracteres."
        )

    return True, ""


class AuthRateLimiter:
    """Proteção contra força bruta com janela deslizante e bloqueio temporário por cliente."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._attempts: Dict[str, List[float]] = {}
        self._locked_until: Dict[str, float] = {}

    def is_locked(self, client_key: str, now: Optional[float] = None) -> Tuple[bool, int]:
        ts = now if now is not None else time.time()
        until = self._locked_until.get(client_key, 0.0)
        if until > ts:
            return True, int(until - ts) + 1
        return False, 0

    def record_failure(self, client_key: str, now: Optional[float] = None) -> bool:
        ts = now if now is not None else time.time()
        cutoff = ts - self.window_seconds
        recent = [t for t in self._attempts.get(client_key, []) if t >= cutoff]
        recent.append(ts)
        self._attempts[client_key] = recent
        if len(recent) >= self.max_attempts:
            self._locked_until[client_key] = ts + self.lockout_seconds
            return True
        return False

    def reset(self, client_key: str) -> None:
        self._attempts.pop(client_key, None)
        self._locked_until.pop(client_key, None)


class AuthService:
    """
    Serviço de autenticação Fail-Closed com tokens assinados HMAC-SHA256 e proteção anti-brute-force.
    """

    def __init__(self, rate_limiter: Optional[AuthRateLimiter] = None):
        self.rate_limiter = rate_limiter or AuthRateLimiter()

    def _get_session_secret(self) -> bytes:
        sec = os.getenv("DASHBOARD_SESSION_SECRET", "").strip()
        if not sec or len(sec) < 16:
            raise PermissionError("DASHBOARD_SESSION_SECRET não configurado (Fail-Closed).")
        return sec.encode("utf-8")

    def verify_credentials(self, password: str, client_key: str = "default") -> Tuple[int, str]:
        """
        Verifica senha do usuário em tempo constante respeitando Fail-Closed e Rate Limiting.
        Retorna (status_code, mensagem):
          - 200: Autenticado
          - 401: Credencial inválida ou configuração ausente (Fail-Closed)
          - 429: Limite de tentativas excedido
        """
        ok_cfg, err_cfg = validate_runtime_security_config()
        if not ok_cfg:
            return 401, err_cfg

        locked, remaining = self.rate_limiter.is_locked(client_key)
        if locked:
            return 429, f"Muitas tentativas inválidas. Aguarde {remaining}s."

        if not password or not isinstance(password, str):
            self.rate_limiter.record_failure(client_key)
            return 401, "Credenciais ausentes ou inválidas."

        pwd_hash = os.getenv("DASHBOARD_AUTH_PASSWORD_HASH", "").strip()
        pwd_plain = os.getenv("DASHBOARD_ACCESS_PASSWORD", "").strip()

        valid = False
        if pwd_hash:
            valid = verify_password_pbkdf2(password, pwd_hash)
        elif pwd_plain:
            digest_in = hashlib.sha256(password.encode("utf-8")).digest()
            digest_env = hashlib.sha256(pwd_plain.encode("utf-8")).digest()
            valid = hmac.compare_digest(digest_in, digest_env)

        if not valid:
            self.rate_limiter.record_failure(client_key)
            return 401, "Credenciais inválidas."

        self.rate_limiter.reset(client_key)
        return 200, "Autenticado com sucesso."

    def create_session_token(self, ttl_seconds: int = 1800) -> str:
        """Gera token de sessão assinado com HMAC-SHA256 e expiração."""
        secret_bytes = self._get_session_secret()
        exp = int(time.time()) + max(60, int(ttl_seconds))
        nonce = secrets.token_hex(16)
        payload = f"{exp}.{nonce}"
        sig = hmac.new(secret_bytes, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def validate_session_token(self, token: Optional[str], now: Optional[float] = None) -> bool:
        """Valida assinatura HMAC-SHA256 e prazo de expiração do token de sessão."""
        if not token or not isinstance(token, str):
            return False
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False
            exp_str, nonce, sig = parts
            exp = int(exp_str)
            ts = now if now is not None else time.time()
            if exp < ts:
                return False
            secret_bytes = self._get_session_secret()
            payload = f"{exp_str}.{nonce}"
            expected_sig = hmac.new(secret_bytes, payload.encode("utf-8"), hashlib.sha256).hexdigest()
            return hmac.compare_digest(sig, expected_sig)
        except Exception:
            return False

    def authenticate_request(
        self,
        headers: Optional[Dict[str, str]] = None,
        session_token: Optional[str] = None,
        client_key: str = "default",
    ) -> Tuple[int, str]:
        """
        Valida uma requisição protegida (usado pela WebUI e por testes negativos HTTP 401).
        Verifica Host Header (quando informado), configuração Fail-Closed e token/Authorization Bearer.
        """
        if is_auth_required():
            ok_cfg, err_cfg = validate_runtime_security_config()
            if not ok_cfg:
                return 401, err_cfg

        if headers:
            host_hdr = headers.get("Host") or headers.get("host")
            if host_hdr and not validate_host_header(host_hdr):
                return 401, "Host header não autorizado."

        if not is_auth_required():
            return 200, "OK"

        token = session_token
        if not token and headers:
            auth_hdr = headers.get("Authorization") or headers.get("authorization") or ""
            if auth_hdr.startswith("Bearer "):
                token = auth_hdr[7:].strip()

        if not token:
            return 401, "Autenticação obrigatória ausente."

        if not self.validate_session_token(token):
            return 401, "Token de sessão inválido ou expirado."

        return 200, "OK"
