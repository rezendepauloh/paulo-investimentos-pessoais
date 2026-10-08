#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Executor Unificado da Suíte de Testes — Paulo Investimentos Pessoais
Executa testes unitários e de integração com relatório colorido e detalhado.
"""

import os
import sys
import time
import unittest

# Habilitar cores ANSI no Windows caso executado via pwsh/cmd
if sys.platform == 'win32':
    os.system('')

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
WHITE = "\033[37m"
DARK_GRAY = "\033[90m"

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, '..'))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Garante carregamento prévio dos helpers e mocks
import tests.test_helpers

class ColoredTestResult(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        self.stream.write(f" {GREEN}✔ PASS{RESET} {DARK_GRAY}{test.id()}{RESET}\n")
        self.stream.flush()

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.write(f" {RED}✖ ERROR{RESET} {BOLD}{test.id()}{RESET}\n")
        self.stream.flush()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.write(f" {RED}✖ FAIL{RESET} {BOLD}{test.id()}{RESET}\n")
        self.stream.flush()

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.stream.write(f" {YELLOW}⚡ SKIP{RESET} {DARK_GRAY}{test.id()} ({reason}){RESET}\n")
        self.stream.flush()

class ColoredTestRunner(unittest.TextTestRunner):
    resultclass = ColoredTestResult

def run_suite(suite_name, suite_dir):
    print(f"\n{CYAN}▶ Executando Suíte: {BOLD}{suite_name}{RESET} ({DARK_GRAY}{suite_dir}{RESET})")
    print(f"{DARK_GRAY}{'─' * 65}{RESET}")
    start = time.perf_counter()
    loader = unittest.TestLoader()
    suite = loader.discover(suite_dir, pattern="test_*.py")
    runner = ColoredTestRunner(verbosity=0)
    result = runner.run(suite)
    elapsed = (time.perf_counter() - start) * 1000
    print(f"{DARK_GRAY}{'─' * 65}{RESET}")
    print(f"⏱ Tempo: {YELLOW}{elapsed:.1f}ms{RESET} | Rodados: {BOLD}{result.testsRun}{RESET} | Falhas: {RED if result.failures else GREEN}{len(result.failures)}{RESET} | Erros: {RED if result.errors else GREEN}{len(result.errors)}{RESET}")
    return result

def main():
    print("")
    print(f"{CYAN}╔═══════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{CYAN}║     PAULO INVESTIMENTOS — SUÍTE DE TESTES AUTOMATIZADOS       ║{RESET}")
    print(f"{CYAN}╚═══════════════════════════════════════════════════════════════╝{RESET}")

    suites = [
        ("💾 Banco de Dados, Parsing, Deduplicação & Analytics", os.path.join(TESTS_DIR, "unit")),
        ("🌐 Integração, Fluxos de Ingestão & Conciliação", os.path.join(TESTS_DIR, "integration")),
    ]

    total_run = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    global_start = time.perf_counter()

    for name, s_dir in suites:
        if os.path.exists(s_dir):
            res = run_suite(name, s_dir)
            total_run += res.testsRun
            total_failures += len(res.failures)
            total_errors += len(res.errors)
            total_skipped += len(res.skipped)

    total_time = (time.perf_counter() - global_start) * 1000

    print("\n" + "=" * 65)
    print(f"{BOLD}RESUMO GERAL DA VALIDAÇÃO DO PAULO INVESTIMENTOS:{RESET}")
    print(f"• Total de Testes Executados : {BOLD}{total_run}{RESET}")
    print(f"• Sucesso Total              : {GREEN}{total_run - total_failures - total_errors}{RESET}")
    print(f"• Falhas                     : {RED if total_failures else GREEN}{total_failures}{RESET}")
    print(f"• Erros                      : {RED if total_errors else GREEN}{total_errors}{RESET}")
    print(f"• Ignorados                  : {YELLOW}{total_skipped}{RESET}")
    print(f"• Duração Total              : {YELLOW}{total_time:.1f}ms{RESET}")
    print("=" * 65)

    if total_failures == 0 and total_errors == 0:
        print(f"\n{GREEN}{BOLD}🎉 PARABÉNS! TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!{RESET}")
        print(f"{GREEN}Todos os módulos de banco, inteligência, parsers e regras de carteira estão íntegros.{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n{RED}{BOLD}❌ ATENÇÃO: Foram encontradas inconsistências na suíte de testes.{RESET}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
