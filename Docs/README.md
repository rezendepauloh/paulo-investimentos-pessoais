# 📚 Documentação Técnica — Paulo Investimentos Pessoais

> **Central unificada de documentação de engenharia, arquitetura, manuais operacionais e guias do sistema.**  
> Plataforma e ecossistema analítico financeiro desenvolvido em **Python** com **Streamlit**, desenhado para gestão patrimonial, inteligência financeira, acompanhamento de carteira e controle orçamentário.

---

## 🗂️ Estrutura e Mapa de Navegação da Documentação

```text
Docs/
├── README.md                                         # Este índice central unificado
│
├── 🏛️ arquitetura/                                   # Decisões fundamentais de engenharia e modelagem
│   ├── dossie_arquitetura_sistema.md                 # Visão global da arquitetura, fluxo de dados e serviços
│   ├── camada_dados_hibrida_sheets_sqlite.md         # Modelo híbrido Google Sheets + SQLite (Delta Sync e índices)
│   ├── motor_analytics_twr_benchmarks.md             # Motor TWR, splits, cotações e benchmarks de mercado
│   ├── pipeline_ingestao_parsers_dedicados.md        # Dispatcher por banco (OFX, CSV), IA multimodal e detecção SHA-256
│   └── contexto_e_futuro_parsers.md                  # Contexto operacional detalhado e estratégia por banco (Strategy)
│
├── 📖 guias/                                         # Manuais práticos de operação, instalação e utilitários
│   ├── instalacao_e_deploy_docker.md                 # Deploy via Docker Compose (WSL, Linux e Servidor Homelab)
│   ├── configuracao_google_sheets_e_credenciais.md   # Configuração OAuth, Conta de Serviço e chaves .env
│   ├── conciliacao_gastos_e_extratos.md              # Uso da tela de conciliação, importação de faturas e comprovantes
│   └── scripts_manutencao_e_splits.md                # Scripts utilitários de diagnóstico, migração e reconciliação
│
├── 🧪 testes/                                        # Suíte de testes automatizados e integridade
│   └── suite_de_testes_automatizados.md              # Manual de execução dos testes com ColoredTestRunner no Docker
│
└── 🚨 issues/                                        # Registro de roadmap, pendências e melhorias
    └── backlog_e_historico_de_issues.md              # Histórico de entregas e roadmap da plataforma
```

---

## 🚀 Acessos Rápidos Mais Utilizados

### 1. Operação Técnica e Uso Diário
- **Como subir o sistema no Docker/WSL:** [Guia de Instalação e Deploy Docker](guias/instalacao_e_deploy_docker.md)
- **Como obter e configurar as credenciais do Google Sheets:** [Configuração de Credenciais & Google Sheets](guias/configuracao_google_sheets_e_credenciais.md)
- **Como conciliar extratos e faturas de cartão:** [Guia de Conciliação e Ingestão de Gastos](guias/conciliacao_gastos_e_extratos.md)
- **Como ajustar desdobramentos de ações e rodar diagnósticos:** [Scripts de Manutenção e Splits](guias/scripts_manutencao_e_splits.md)

### 2. Engenharia e Arquitetura de Software
- **Visão macro e decisões técnicas do sistema:** [Dossiê Global de Arquitetura](arquitetura/dossie_arquitetura_sistema.md)
- **Como opera a persistência híbrida (Google Sheets + SQLite):** [Camada de Dados Híbrida](arquitetura/camada_dados_hibrida_sheets_sqlite.md)
- **Como a rentabilidade (TWR) e benchmarks são calculados:** [Motor de Analytics & Benchmarks](arquitetura/motor_analytics_twr_benchmarks.md)
- **Como funcionam os parsers dedicados por banco:** [Pipeline de Ingestão e Parsers Dedicados](arquitetura/pipeline_ingestao_parsers_dedicados.md)
- **Visão detalhada e estratégia de ingestão por banco:** [Contexto e Futuro dos Parsers](arquitetura/contexto_e_futuro_parsers.md)

### 3. Qualidade, Testes & Roadmap
- **Como executar a suíte de testes com validação rigorosa:** [Manual de Testes Automatizados](testes/suite_de_testes_automatizados.md)
- **Acompanhamento do roadmap e entregas do projeto:** [Backlog e Histórico de Issues](issues/backlog_e_historico_de_issues.md)
- **Diretrizes para agentes autônomos de programação:** [AGENTS.md](../AGENTS.md)

