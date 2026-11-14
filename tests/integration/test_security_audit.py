# -*- coding: utf-8 -*-
"""
Testes de Integração e Auditoria Contínua de Segurança (SecOps):
a) Varredura de segredos e PII em todos os arquivos rastreados pelo Git (`git ls-files`)
b) Comportamento Fail-Closed de scripts e serviços quando credenciais são omitidas
c) Validação de sintaxe de scripts/Dockerfiles/Compose/TOML e permissões de arquivos
"""
import os
import py_compile
import re
import stat
import subprocess
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class TestSecurityAudit(unittest.TestCase):
    def test_git_tracked_files_have_no_secrets_or_hardcoded_pii(self):
        """Varredura contínua de segredos em todos os arquivos rastreados pelo Git (ou código local em container)."""
        import shutil

        files_to_scan = []
        if shutil.which("git") and (ROOT_DIR / ".git").exists():
            proc = subprocess.run(
                ["git", "ls-files"],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            files_to_scan = [f for f in proc.stdout.splitlines() if f.strip()]
            self.assertGreater(len(files_to_scan), 10)
        else:
            # Em container isolado (.git excluído via .dockerignore), varre fontes e scripts montados
            for p in ROOT_DIR.rglob("*"):
                if p.is_file() and not any(part in p.parts for part in (".git", "__pycache__", "logs", "data", "temp")):
                    files_to_scan.append(str(p.relative_to(ROOT_DIR)))

        secret_patterns = [
            ("Google API Key", re.compile(r"AIza[0-9A-Za-z_-]{20,}")),
            ("Private Key Block", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
            ("GitHub Token", re.compile(r"ghp_[0-9A-Za-z]{20,}")),
            ("Real CPF/PDF Password Leak", re.compile(r"046376")),
        ]

        findings = []
        for rel_path in files_to_scan:
            if rel_path == "tests/integration/test_security_audit.py":
                continue

            full_path = ROOT_DIR / rel_path
            if not full_path.is_file():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError:
                continue  # Ignora binários

            for label, pattern in secret_patterns:
                if pattern.search(content):
                    findings.append(f"{rel_path}: {label}")

        self.assertEqual(
            findings,
            [],
            f"Foram detectados possíveis segredos/PII em arquivos rastreados pelo Git: {findings}",
        )

    def test_hardcoded_homelab_ip_absent_from_runtime_code_and_scripts(self):
        """Garante remoção de IPs/usuários hardcoded do homelab nos scripts, compose e .env.example."""
        targets = [
            "00-iniciar.sh",
            "00-iniciar.cmd",
            ".env.example",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.server.yml",
        ]
        for rel in targets:
            text = (ROOT_DIR / rel).read_text(encoding="utf-8")
            self.assertNotIn("192.168.0.8", text, f"IP hardcoded residual em {rel}")
            self.assertNotIn("umbrel", text.lower(), f"Usuário hardcoded residual em {rel}")

    def test_fail_closed_scripts_abort_without_required_env(self):
        """Valida comportamento fail-closed ao omitir variáveis obrigatórias."""
        # 1. scripts/remover_linha_eztc.py deve sair com erro sem REMOVER_TICKER / REMOVER_DATA
        clean_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(ROOT_DIR)}
        proc = subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "remover_linha_eztc.py")],
            cwd=str(ROOT_DIR),
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(proc.returncode, 0, "remover_linha_eztc.py deveria falhar em modo fail-closed.")

        # 2. Função deploy_homelab de 00-iniciar.sh deve falhar (Fail-Closed) em diretório sem .env ou com HOMELAB_* vazios
        import tempfile
        proc_syntax = subprocess.run(
            ["bash", "-n", str(ROOT_DIR / "00-iniciar.sh")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc_syntax.returncode, 0, f"Erro de sintaxe em 00-iniciar.sh: {proc_syntax.stderr}")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Extrai apenas definições de funções até antes de show_menu()/loop CLI
            script_src = (ROOT_DIR / "00-iniciar.sh").read_text(encoding="utf-8")
            funcs_only = script_src.split("\nshow_menu() {")[0]
            bash_run = subprocess.run(
                ["bash", "-c", funcs_only + "\n deploy_homelab </dev/null"],
                cwd=tmpdir,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmpdir},
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(bash_run.returncode, 0)
            self.assertIn("Fail-Closed", bash_run.stdout + bash_run.stderr)

    def test_infrastructure_hardening_and_syntax(self):
        """Verifica ausência de flags inseguras, bind restrito, usuário non-root e compilação Python."""
        dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("NODE_TLS_REJECT_UNAUTHORIZED=0", dockerfile)
        self.assertNotIn("PIP_TRUSTED_HOST", dockerfile)
        self.assertNotIn("--trusted-host", dockerfile)
        self.assertIn("USER appuser", dockerfile)

        for compose_name in ("docker-compose.yml", "docker-compose.server.yml"):
            compose_txt = (ROOT_DIR / compose_name).read_text(encoding="utf-8")
            self.assertIn("127.0.0.1", compose_txt, f"{compose_name} deve fazer bind padrão em 127.0.0.1")
            self.assertIn("no-new-privileges:true", compose_txt)
            self.assertIn("cap_drop", compose_txt)

        dev_compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn(".:/app", dev_compose, "Mount amplo .:/app expõe .env e .git ao container")

        st_config = (ROOT_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('address = "127.0.0.1"', st_config)
        self.assertIn("enableCORS = true", st_config)
        self.assertIn("enableXsrfProtection = true", st_config)
        self.assertIn("showErrorDetails = false", st_config)

        init_sh = (ROOT_DIR / "00-iniciar.sh").read_text(encoding="utf-8")
        self.assertNotIn("chmod 777", init_sh)
        self.assertNotIn("/tmp/investimentos_prod.env.$$", init_sh)

        # Compilação Python de módulos críticos para diretório temporário isolado
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            for idx, py_rel in enumerate((
                "dashboard.py",
                "src/utils/security.py",
                "src/utils/logger.py",
                "src/database/db_manager.py",
            )):
                py_compile.compile(
                    str(ROOT_DIR / py_rel),
                    cfile=os.path.join(tmpdir, f"mod_{idx}.pyc"),
                    doraise=True,
                )

    def test_sensitive_local_file_permissions(self):
        """Valida que .env (se presente) não possui permissões de leitura/escrita para grupo ou terceiros."""
        env_file = ROOT_DIR / ".env"
        if env_file.exists():
            mode = stat.S_IMODE(env_file.stat().st_mode)
            self.assertEqual(
                mode & 0o077,
                0,
                f"Arquivo .env possui permissões excessivas ({oct(mode)}). Exige-se chmod 600.",
            )

        init_sh = ROOT_DIR / "00-iniciar.sh"
        mode_sh = stat.S_IMODE(init_sh.stat().st_mode)
        self.assertEqual(mode_sh & 0o002, 0, f"00-iniciar.sh gravável por world ({oct(mode_sh)}).")

    def test_gitignore_and_dockerignore_protection(self):
        gitignore = (ROOT_DIR / ".gitignore").read_text(encoding="utf-8")
        for pat in (".env", "data/credentials.json", "*.pem", "*.key", "*.db", "logs/"):
            self.assertIn(pat, gitignore)

        dockerignore = (ROOT_DIR / ".dockerignore").read_text(encoding="utf-8")
        for pat in (".env", "data/", "*.db", "credentials.json", "temp/", "tests/"):
            self.assertIn(pat, dockerignore)


if __name__ == "__main__":
    unittest.main()
