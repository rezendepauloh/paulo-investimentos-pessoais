# Scripts de Manutenção, Diagnóstico e Splits

> **Objetivo:** Documentar o propósito e uso dos scripts utilitários localizados no diretório `scripts/`.

---

## 1. Reconciliação de Splits de Ações (`scripts/auto_ajustar_splits.py`)

Ajusta o histórico de ordens para refletir desdobramentos oficiais de ações da B3:

```bash
docker compose exec paulo-investimentos-app python scripts/auto_ajustar_splits.py
```

O script:
- Consulta eventos corporativos de splits e grupamentos no `yfinance`.
- Ajusta quantidade e preço médio histórico de cada ativo.
- Gera relatório de auditoria detalhando as alterações.

---

## 2. Diagnóstico de Integridade (`scripts/diagnostico.py`)

Valida o estado das conexões e consistência do banco de dados:

```bash
docker compose exec paulo-investimentos-app python scripts/diagnostico.py
```

Verifica:
- Conexão e permissões com as planilhas do Google Sheets via API.
- Integridade do banco SQLite local (`data/investimentos.db`).
- Disponibilidade da API do Gemini e Yahoo Finance.
- Presença e formatação de variáveis no `.env`.

