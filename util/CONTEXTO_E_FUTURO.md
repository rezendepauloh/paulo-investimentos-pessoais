# Documentação de Contexto e Visão de Futuro — Paulo Investimentos Pessoais

> **Data de Atualização:** Outubro de 2026  
> **Status:** Ativo / Em Desenvolvimento Contínuo  
> **Propósito:** Registro do ecossistema técnico, regras de negócio e planejamento arquitetural para ingestão especializada por instituição financeira.

---

## 1. Visão Geral do Sistema

O **Paulo Investimentos Pessoais** é um ecossistema completo para gestão patrimonial, inteligência financeira e controle orçamentário. O sistema integra:

1. **Dashboard & Visualização Financeira (Streamlit + Plotly):**
   - **Visão Geral:** Saldo patrimonial líquido, distribuição por classe de ativos (Ações BR, FIIs, Stocks/ETFs EUA, Renda Fixa), acompanhamento de metas e fluxo orçamentário recente.
   - **Desempenho da Carteira:** Cálculo de rentabilidade histórica por cotas (**TWR - Time-Weighted Rate of Return**), splits oficiais e comparativo direto contra benchmarks de mercado (CDI, IPCA, IPCA+6%, Ibovespa, S&P 500).
   - **Extratos e Lançamentos:** Visualização analítica e filtragem granular de receitas, despesas, aportes e proventos.
   - **Análise Fundamentalista:** Balanço Patrimonial, DRE e Fluxo de Caixa histórico importados automaticamente via `yfinance` para múltiplos anos/trimestres.
   - **Consultoria por Inteligência Artificial:** Recomendações didáticas e alocação dinâmica baseada em Markowitz utilizando o **Google Gemini 1.5 Flash**.
   - **Ingestão Inteligente & Conciliação:** Leitura multimodal de comprovantes (OCR com IA), decodificação de arquivos bancários (.OFX / .CSV), Open Finance (Pluggy) e editor interativo para conferência com detecção em tempo real de duplicidades.
   - **Configurações & Diagnósticos:** Gerenciamento de credenciais, status de APIs e validação de consistência contábil da base de dados.

2. **Camada de Dados Híbrida (Google Sheets + SQLite Local):**
   - **Google Sheets:** Fonte da verdade histórica do usuário acessada via API oficial do Google (`gspread`).
   - **SQLite Local (`data/investimentos.db`):** Cache relacional de alta performance para sincronização incremental (Delta Sync), cotações diárias e histórico de demonstrativos contábeis.

3. **Automação, Infraestrutura & Homelab:**
   - Contêiner Docker baseado em Debian Bookworm (`python:3.12-slim-bookworm`).
   - Execução local orquestrada via `docker compose` com suporte a scripts CLI completos para Linux (`./00-iniciar.sh`) e Windows (`00-iniciar.cmd`).
   - Deploy remoto com 1 clique para servidor Mini PC / Homelab (Dockge).

4. **Qualidade & Garantia de Software:**
   - Suíte de testes automatizados completa (`tests/`) com `ColoredTestRunner` cobrindo testes unitários de regras financeiras, persistência no SQLite, cálculo de custódia e integração de conciliação ponta a ponta.

---

## 2. O Desafio Atual da Ingestão de Dados

Atualmente, o módulo de ingestão (`src/services/ingestion_parser.py`) suporta:
- Leitura de comprovantes e fotos via **Gemini Multimodal Vision**.
- Leitura de arquivos `.OFX` via parser estruturado (`ofxtools` com fallback Regex).
- Leitura genérica de `.CSV` com detecção de delimitadores e mapeamento dinâmico de colunas.
- Conexão Open Finance via **Pluggy**.

### O Problema Identificado:
Cada banco comercial, cooperativa ou corretora (Inter, Sicredi, C6, Nubank, XP, Mercado Pago, 99 Pay, Itaú, etc.) possui:
1. **Convenções de sinais opostas:** Em alguns bancos, compras aparecem com valor negativo (`-150.00`), enquanto em outros faturas de cartão mostram compras com valores positivos e pagamentos como crédito.
2. **Layouts de colunas heterogêneos em CSV:** Colunas como `Data / Histórico / Lançamento / Saldo / Valor (R$) / Débito / Crédito / Categoria`.
3. **Padrão de descrições e códigos OFX:** Tags `<MEMO>`, `<NAME>` e códigos `<TRNTYPE>` variam entre instituições financeiras (ex: Pix recebido pode vir como `CREDIT`, `TRANSFER` ou `OTHER`).
4. **Formatação de prints/comprovantes:** Cada aplicativo possui layout gráfico, fontes e informações específicas (ex: recibos de Pix do Sicredi trazem agência/conta do remetente, enquanto o Nubank prioriza o identificador de ponta a ponta).

---

## 3. Visão de Futuro: Arquitetura de Parsers Dedicados por Instituição Financeira

Para alcançar uma experiência **100% precisa, sem falhas de interpretação e perfeitamente adaptada à realidade do usuário**, a evolução da ingestão seguirá o **Padrão Strategy / Dispatcher por Instituição**.

### 3.1. Experiência de Uso (UI no Streamlit)

Na aba de **Ingestão Inteligente e Conciliação de Gastos**:
1. Antes de realizar o upload de arquivos ou imagens, o usuário terá um seletor visual:
   ```text
   [ Selecione a Instituição Financeira / Origem ]
   ┌────────────────────────────────────────────────────────┐
   │ 🏦 Sicredi                                           ▼ │
   │   - 🏦 Banco Inter                                     │
   │   - 🏦 C6 Bank                                         │
   │   - 🟣 Nubank                                          │
   │   - 🟡 XP Investimentos                                │
   │   - 🟢 Mercado Pago                                    │
   │   - 🟠 99 Pay                                          │
   │   - 🏛️ Outro / Genérico (Auto-Detecção)                │
   └────────────────────────────────────────────────────────┘
   ```
2. Após selecionar o banco, o sistema exibe orientações específicas daquela instituição (ex: *"Dica: No Sicredi Internet Banking, exporte o extrato no formato .OFX ou .CSV de Conta Corrente"*).
3. O seletor despacha a interpretação para a **função dedicada (`def`)** exclusiva daquela instituição, garantindo:
   - Sanitização de valores e tratamento de sinal exato.
   - Normalização automática das contas de crédito/débito (`Conta debitada = 'Sicredi'`).
   - Identificação precisa de taxas, juros sobre capital, cashback, estornos e transferências entre contas próprias.

### 3.2. Mapeamento dos Parsers Dedicados Planejados

A pasta `src/services/` passará a contar com submódulos organizados para cada instituição:

```text
src/services/parsers/
├── __init__.py                # Dispatcher unificado (registry de bancos)
├── base_parser.py             # Classe/Interface base padronizando DataFrame de saída
├── inter_parser.py            # def parse_inter_csv / parse_inter_ofx / parse_inter_receipt
├── sicredi_parser.py          # def parse_sicredi_csv / parse_sicredi_ofx / parse_sicredi_receipt
├── c6_parser.py               # def parse_c6_csv / parse_c6_ofx
├── nubank_parser.py           # def parse_nubank_csv / parse_nubank_ofx
├── xp_parser.py               # def parse_xp_csv (notas de corretagem e proventos)
├── mercadopago_parser.py      # def parse_mercadopago_csv / receipts
├── pay99_parser.py            # def parse_99pay_csv / receipts
└── generic_parser.py          # Fallback com heurística e OCR universal
```

### 3.3. Particularidades Previstas por Banco / Fintech

| Instituição | Formatos Chave | Particularidades Conhecidas |
| :--- | :--- | :--- |
| **Sicredi** | `.ofx`, `.csv`, comprovantes Pix | Delimitador `;` no CSV, codificação ANSI/Windows-1252, descrições com prefixos `PIX ENVIADO`, `PIX RECEBIDO`, `COMPRA CARTAO DEB`. |
| **Banco Inter** | `.ofx`, `.csv`, faturas de cartão | Extratos de conta corrente e de investimentos separados; suporte a identificação de proventos e rendimentos em conta. |
| **C6 Bank** | `.csv`, faturas | Faturas em PDF/CSV com discriminação de parcelas `(01/10)`, conversão de compras internacionais em dólares. |
| **Nubank** | `.csv`, `.ofx` | CSV padronizado em UTF-8 com colunas `date`, `category`, `title`, `amount`; valores positivos no extrato de cartão representam pagamentos/estornos. |
| **XP Investimentos** | `.csv`, `.xlsx` | Extrato de conta digital vs. extrato de custódia e notas de corretagem (B3). |
| **Mercado Pago** | `.csv`, prints de app | CSV detalhado com taxas de serviço, repasses e rendimento automático de saldo. |
| **99 Pay** | `.csv`, comprovantes de saldo | Bonificação diária de CDI e pagamentos de boletos. |

---

## 4. Status de Implementação e Roadmap

### 4.1. Status Atual (Concluído ✅)
- [x] **Arquitetura Base**: Implementado `src/services/parsers/base_parser.py` e contrato `BaseBankParser`.
- [x] **Dispatcher Central**: Implementado `src/services/parsers/__init__.py` com `parse_bank_file()`, registry central e fallback seguro para `GenericBankParser`.
- [x] **UI com Seleção Visual e Dicas Contextuais**: Adicionado seletor de instituição bancária com caixas de orientações dinâmicas em `src/tabs/importar_gastos.py`.
- [x] **Parsers Consolidados Prontos**:
  - `SicrediParser` (`src/services/parsers/sicredi_parser.py`): Delimitador `;`, codificação latin-1/windows-1252, sanitização de prefixos operacionais (`PIX ENVIADO`, `COMPRA CARTAO DEB`), normalização automática de Conta = 'Sicredi'.
  - `NubankParser` (`src/services/parsers/nubank_parser.py`): Suporte a extratos de fatura de cartão (`date`, `category`, `title`, `amount`), inversão de sinal para pagamentos/estornos e Conta = 'Nubank'.
  - `InterParser` (`src/services/parsers/inter_parser.py`): Extratos CSV e OFX com atribuição para Banco Inter.
  - `GenericBankParser` (`src/services/parsers/generic_parser.py`): Fallback universal inteligente com regex e IA.
- [x] **Módulos Estruturais Prontos (Esqueleto para evolução gradativa)**:
  - `C6BankParser` (`src/services/parsers/c6_parser.py`)
  - `XPParser` (`src/services/parsers/xp_parser.py`)
  - `MercadoPagoParser` (`src/services/parsers/mercadopago_parser.py`)
  - `Pay99Parser` (`src/services/parsers/pay99_parser.py`)
- [x] **Carregamento Assíncrono & Accordion de Logs (Padrão Bancada)**:
  - Implementado `src/services/async_tasks.py` para execução não-bloqueante em background thread com tracking de logs e tempo.
  - Criado `src/components/status_banner.py` (`render_async_task_expander`) com auto-refresh suave a cada 2s via `@st.fragment` e notificação `st.toast` ao concluir.
  - Sincronização de Google Sheets na Sidebar e reconstrução pesada de rentabilidade histórica (10 anos / BCB) desacopladas da abertura inicial, permitindo uso 100% imediato e responsivo da Visão Geral e demais abas.

### 4.2. Próximos Passos de Evolução Gradativa
1. **Faturas Parceladas C6 Bank**:
   - Tratamento detalhado de parcelas em texto `(01/10)` e conversão de cotação de compras internacionais em dólar.
2. **Extratos de Proventos e Corretagem XP**:
   - Roteamento inteligente de notas de corretagem B3 e proventos creditados direto para a tabela `dividendos`.
3. **Prompts Especializados de OCR Multimodal (Gemini Vision)**:
   - Injeção de instruções contextuais específicas no prompt da IA conforme o banco selecionado na aba de comprovantes.


