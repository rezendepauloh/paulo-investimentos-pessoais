# Backlog e Histórico de Entregas

> **Objetivo:** Registro do ciclo de vida, entregas concluídas e roadmap arquitetural do Paulo Investimentos Pessoais.

---

## 📌 Roadmap & Próximas Entregas

- [ ] **Alocação Dinâmica Automatizada:** Algoritmo de Fronteira Eficiente de Markowitz com integração de restrições configuradas pelo usuário.
- [ ] **Exportação de Relatório Mensal em PDF:** Geração automática de fechamento patrimonial com gráficos Plotly renderizados.
- [ ] **Integração Adicional Open Finance:** Conexão contínua para sincronização de saldo em conta corrente em D-0 via Webhook.

---

## ✅ Marcos Entregues Recentemente

### Consolidação Arquitetural & Documentação (Novembro/2026)
- Centralização unificada das diretrizes para agentes autônomos em `AGENTS.md`.
- Migração de regras e contexto legados (`.antigravityrules`, `.antigravity-context.md`, `.antigravityignore`).
- Criação da central unificada de documentação em `Docs/` com dossiês de arquitetura, guias e testes.
- Refatoração do `README.md` com badges oficiais e navegação aprofundada.

### Ingestão Dedicada por Instituição Financeira (Outubro/2026)
- Criação do pacote `src/services/parsers/` com arquitetura Strategy/Dispatcher por banco.
- Parsers dedicados para Sicredi, Inter, C6 Bank, Nubank, 99 Pay, Mercado Pago, B3 e cartões de loja (Vuon/Renner).
- Ingestão multimodal de comprovantes via Gemini Vision com extração estruturada (Pydantic).
- Detecção e prevenção em tempo real de duplicidades de lançamentos via hash SHA-256 no `st.data_editor`.

### Motor de Desempenho e Benchmarks
- Rentabilidade histórica por cotas (**TWR**).
- Integração de cotações em tempo real via `yfinance`.
- Comparativo automatizado contra benchmarks oficiais (**CDI, IPCA, Ibovespa e S&P 500**).
- Reconciliação automática de desdobramentos de ações (*splits*).

