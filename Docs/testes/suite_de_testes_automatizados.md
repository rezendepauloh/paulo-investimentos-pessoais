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
- **Testes de Integração (`tests/integration/`):**
  - `test_data_flow.py`: Fluxo completo de leitura, sanitização e sincronização.

---

## 2. Como Executar os Testes

Como o projeto possui dependências gerenciadas pelo Docker (como `gspread`, `yfinance`, `ofxtools`), os testes devem ser executados no contêiner ou em ambiente com as dependências instaladas:

### No Contêiner Docker Ativo:

```bash
docker compose exec paulo-investimentos-app python tests/run_all.py
```

### Executar Teste Específico via Pytest:

```bash
docker compose exec paulo-investimentos-app pytest tests/unit/test_bank_parsers.py -v
```

---

## 3. Critério de Aceite para Novas Funcionalidades

Conforme estabelecido no [AGENTS.md](../../AGENTS.md):
- **100% de aprovação** na suíte de testes antes de qualquer commit ou deploy (0 falhas, 0 erros).

