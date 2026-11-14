# Suíte de Testes Automatizados e Integridade

> **Objetivo:** Instruções e boas práticas para execução da suíte de testes do Paulo Investimentos Pessoais.

---

## 1. Visão Geral da Suíte

A suíte de testes cobre regras de negócio financeiras, cálculos de rentabilidade, deduplicação por hash, conexões com SQLite e parsers bancários dedicados:

- **Testes Unitários (`tests/unit/`):**
  - `test_formatting.py`: Formatação de moedas (BRL/USD), números e mascaramento de privacidade.
  - `test_deduplication.py`: Geração de assinaturas SHA-256 e detecção de duplicatas.
  - `test_analytics.py`: Fórmulas TWR, preço médio e cálculo de rentabilidade.
  - `test_bank_parsers.py`: Parsers de bancos (Inter, Sicredi, C6, Nubank, 99Pay, Vuon, etc.).
  - `test_db_manager.py`: Criação de esquemas, índices e consultas no SQLite.
  - `test_portfolio_health.py`: Diagnóstico de saúde da carteira.
  - `test_fundamental_analysis.py`: Validação de indicadores fundamentalistas.
  - `test_security.py`: Autenticação Fail-Closed, PBKDF2, tokens HMAC, rate limiting (`401`/`429`), whitelists SQL/Ticker/Spreadsheet ID, anti-XSS, anti-Formula Injection, anti-XXE, anti-Zip-Bomb e redação de segredos.
- **Testes de Integração (`tests/integration/`):**
  - `test_data_flow.py`: Fluxo completo de leitura, sanitização e sincronização.
  - `test_security_audit.py`: Varredura contínua de segredos em `git ls-files`, validação Fail-Closed de scripts (`00-iniciar.sh`, `remover_linha_eztc.py`), checagem de hardening de infraestrutura e permissões de arquivos (`.env` `chmod 600`).

---

## 2. Como Executar os Testes

Como `tests/` é excluído da imagem de produção via `.dockerignore`, execute via launcher ou montando os volumes de teste em modo somente leitura:

### Via Launcher Oficial (Recomendado):

```bash
./00-iniciar.sh --test
```

### Via Docker Compose Run ou Pytest:

```bash
docker compose run --rm -v "$(pwd)/tests:/app/tests:ro" -v "$(pwd)/scripts:/app/scripts:ro" app python tests/run_all.py

# Teste específico via pytest:
docker compose run --rm -v "$(pwd)/tests:/app/tests:ro" app pytest tests/unit/test_security.py tests/integration/test_security_audit.py -v
```

---

## 3. Critério de Aceite para Novas Funcionalidades

Conforme estabelecido no [AGENTS.md](../../AGENTS.md):
- **100% de aprovação** na suíte de testes antes de qualquer commit ou deploy (0 falhas, 0 erros).

