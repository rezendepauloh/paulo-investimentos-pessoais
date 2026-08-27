# 📈 Painel de Finanças e Investimentos Pessoais com Streamlit & IA

Este projeto é um painel financeiro profissional construído em Python com **Streamlit**, integrado diretamente com planilhas de Orçamento e de Ordens do Google Sheets. A aplicação realiza o cálculo automático da evolução de patrimônio líquida e compara com os principais benchmarks nacionais e internacionais (**CDI, IPCA, Ibovespa e S&P 500**) a partir de APIs públicas em tempo real, além de fornecer dicas automatizadas de alocação de recursos usando a inteligência artificial do **Google Gemini**.

---

## 🚀 Como Executar o Projeto Localmente (Docker / WSL)

Requisitos: **WSL (Ubuntu)** e **Docker Desktop** (com integração WSL ativada) ou Docker Engine.

### 1. Clonar ou Acessar o Diretório do Projeto no WSL

No seu terminal do WSL (Ubuntu):

```bash
cd ~/PythonProjects/paulo-investimentos-pessoais
```

### 2. Configurar as Variáveis de Ambiente

Crie o arquivo `.env` a partir do modelo `.env.example`:

```bash
cp .env.example .env
```

Abra o arquivo `.env` e configure:

- Os IDs das suas planilhas (`SPREADSHEET_BUDGET_ID` e `SPREADSHEET_ORDERS_ID`).
- A sua chave da API do Gemini (`GEMINI_API_KEY`), obtida em [Google AI Studio](https://aistudio.google.com/).
- A porta do servidor (padrão: `STREAMLIT_PORT=8502`).

### 3. Iniciar o Ambiente de Desenvolvimento

Execute o script de inicialização rápida:

```bash
chmod +x 00-iniciar.sh
./00-iniciar.sh
```

A aplicação estará acessível em: **[http://localhost:8502](http://localhost:8502)** (ou na porta configurada no `.env`).

---

## 🛠️ Comandos Úteis do Docker

- **Subir os containers em background com build:**

  ```bash
  docker compose up -d --build
  ```

- **Visualizar os logs em tempo real:**

  ```bash
  docker compose logs -f
  ```

- **Parar os containers:**

  ```bash
  docker compose down
  ```

- **Reiniciar os containers:**
  ```bash
  docker compose restart
  ```

---

## 📁 Estrutura de Diretórios e Arquitetura

```text
paulo-investimentos-pessoais/
├── .streamlit/
│   └── config.toml                 # Configurações de porta, CORS e servidor
├── assets/
│   └── css/
│       └── styles.css              # Design system, glassmorphism e tema escuro
├── data/
│   ├── credentials.json            # Chave Google Cloud (ignorado pelo git)
│   └── investimentos.db            # Banco de dados local SQLite
├── src/
│   ├── components/                 # Componentes de UI reutilizáveis
│   │   ├── __init__.py
│   │   ├── header.py               # Header da aplicação com popover de menu
│   │   └── sidebar.py              # Barra lateral de configurações e conexões
│   ├── database/                   # Camada de persistência local SQLite
│   │   ├── __init__.py
│   │   └── db_manager.py           # Gestão de conexões, delta sync e tabelas
│   ├── services/                   # Motores de cálculo, conectores e inteligência
│   │   ├── __init__.py
│   │   ├── data_loader.py          # Carga e sanitização Google Sheets / SQLite
│   │   ├── analytics.py            # Motor de cálculos TWR, cotações e benchmarks
│   │   ├── ai_allocator.py         # Integração com Google Gemini 1.5 Flash
│   │   ├── deduplication.py        # Geração de hash SHA-256 e detector de duplicatas
│   │   ├── ingestion_parser.py     # Parsers para OFX, CSV e OCR com Gemini Vision
│   │   └── pluggy_service.py       # Conector com a API Open Finance da Pluggy
│   ├── tabs/                       # Módulos de páginas/abas isoladas
│   │   ├── __init__.py
│   │   ├── visao_geral.py          # Tab 1: Visão Geral, Alocação e Fluxo de Caixa
│   │   ├── desempenho.py           # Tab 2: Desempenho Histórico e Benchmarks
│   │   ├── extratos.py             # Tab 3: Extratos Detalhados e Filtros
│   │   ├── fundamentalista.py      # Tab 4: Análise Fundamentalista e FIIs
│   │   ├── consultoria_ia.py       # Tab 5: Consultoria de Alocação com IA
│   │   ├── importar_gastos.py      # Tab 6: Ingestão Inteligente e Conciliação
│   │   └── configuracoes.py        # Tab 7: Configurações Globais, Credenciais e Sync
│   └── utils/                      # Funções utilitárias compartilhadas
│       ├── __init__.py
│       ├── formatting.py           # Formatação de moedas, números e normalização
│       └── logger.py               # Sistema de logging centralizado rotativo e colorido
├── logs/                           # Diretório de logs rotativos (3MB, máx 3 arquivos)
│   ├── app/                        # Logs da aplicação e ciclo de vida
│   ├── components/                 # Logs do header e sidebar
│   ├── database/                   # Logs de persistência SQLite
│   ├── services/                   # Logs de serviços e APIs
│   └── tabs/                       # Logs das páginas/abas da UI
├── scripts/                        # Scripts auxiliares de diagnóstico e migração
├── dashboard.py                    # Hub / Ponto de entrada principal do Streamlit
├── Dockerfile                      # Imagem Docker otimizada (Python 3.12-slim-bookworm)
├── docker-compose.yml              # Orquestração do container de desenvolvimento
├── 00-iniciar.sh                   # Script de inicialização rápida no WSL
└── 00-iniciar.cmd                  # Atalho de execução para Windows (WSL)
```

---

## 🧭 Navegação Rápida e Deep Linking (URLs com Query Params)

A aplicação sincroniza automaticamente o estado das páginas e subabas na barra de endereços do navegador. Ao recarregar a página (**F5**) ou compartilhar o link, você é levado diretamente para o ponto exato:

| Página | Parâmetro de URL | Exemplos de Subabas (`&subtab=`) |
| :--- | :--- | :--- |
| **📊 Visão Geral e Orçamento** | `?tab=visao_geral` | — |
| **📈 Desempenho e Benchmarks** | `?tab=desempenho` | — |
| **📑 Extratos e Lançamentos** | `?tab=extratos` | `&subtab=receitas`, `&subtab=despesas`, `&subtab=dividendos`, `&subtab=ordens` |
| **🔍 Análise Fundamentalista** | `?tab=fundamentalista` | `&subtab=balanco`, `&subtab=dre`, `&subtab=fluxo` |
| **🤖 Consultoria de Alocação com IA** | `?tab=consultoria_ia` | — |
| **📥 Importação de Dados** | `?tab=importar_gastos` | `&subtab=comprovantes`, `&subtab=arquivos`, `&subtab=open_finance` |
| **⚙️ Configurações do Sistema** | `?tab=configuracoes` | — |

*Exemplo de acesso direto:* `http://localhost:8502/?tab=configuracoes`

---




## 🔑 Como Obter o JSON de Conta de Serviço do Google Cloud

Para que o seu aplicativo Python acesse com segurança suas planilhas privadas do Google Sheets sem torná-las públicas, é recomendável usar uma **Conta de Serviço**. Siga este passo a passo para gerar o seu arquivo `credentials.json`:

1. **Acessar o Google Cloud Console:**
   - Vá para: [https://console.cloud.google.com/](https://console.cloud.google.com/) e faça login com sua conta do Google.

2. **Criar um Novo Projeto:**
   - No menu superior (geralmente ao lado do logo do Google Cloud), clique no seletor de projetos e selecione **Novo Projeto**.
   - Dê o nome de `FinancasApp` (ou qualquer outro nome) e clique em **Criar**.

3. **Ativar as APIs Necessárias:**
   - No campo de busca do topo, pesquise por **Google Sheets API** e clique em **Ativar** (Enable).
   - Em seguida, pesquise por **Google Drive API** e clique em **Ativar** (Enable).

4. **Criar a Conta de Serviço:**
   - No menu lateral esquerdo, vá para **APIs e Serviços** > **Credenciais** (Credentials).
   - Clique no botão **+ Criar Credenciais** (+ Create Credentials) no menu superior e selecione **Conta de Serviço** (Service Account).
   - Preencha as informações:
     - **Nome da Conta de Serviço:** ex: `streamlit-sheets-reader`
     - Clique em **Criar e Continuar** (Create and Continue).
     - Nas etapas seguintes (permissões de acesso), você pode apenas clicar em **Concluir** (Done) pois não são obrigatórias para este tipo de conexão.

5. **Gerar a Chave Privada (JSON):**
   - Na tabela de credenciais, localize a conta de serviço criada (na seção _Contas de Serviço_ / _Service Accounts_) e clique no e-mail dela.
   - Vá para a aba superior chamada **Chaves** (Keys).
   - Clique em **Adicionar Chave** (Add Key) > **Criar Nova Chave** (Create New Key).
   - Selecione o formato **JSON** e clique em **Criar**.
   - O download do arquivo será feito automaticamente.

6. **Colocar as Credenciais no Projeto:**
   - Renomeie o arquivo baixado para `credentials.json`.
   - Salve esse arquivo na raiz do diretório `d:\PythonProjects\paulo-investimentos-pessoais\`.
   - _Nota de Segurança:_ O arquivo `.gitignore` já está configurado para **NÃO** enviar esse arquivo para o GitHub, mantendo seus dados protegidos!

7. **Compartilhar a Planilha com a Conta de Serviço (Passo Fundamental):**
   - Abra o arquivo `credentials.json` em um editor de texto e localize o campo `"client_email"` (ele terá um formato parecido com `streamlit-sheets-reader@seu-projeto.iam.gserviceaccount.com`).
   - Abra as suas duas planilhas no navegador:
     - **Orçamento:** Insira seu Google Sheets
     - **Ordens:** Insira seu Google Sheets
   - Em cada uma delas, clique no botão **Compartilhar** (Share) no canto superior direito.
   - Cole o e-mail da conta de serviço (`client_email`), defina a permissão como **Leitor** (Viewer) e desmarque a opção de enviar notificação. Clique em **Compartilhar**.

---

## 🎨 Principais Recursos do Painel

- **Abas Customizadas:** Divisão entre Visão Geral (orçamentos e carteira), Desempenho Histórico, Visualização de Extrato de Lançamentos, Análise Fundamentalista, Consultoria com IA e **Importação Inteligente de Dados**.
- **Ingestão Híbrida Inteligente (Nova Feature):**
  - **📸 Leitura de Comprovantes via OCR/IA:** Extração automática de prints, faturas e comprovantes Pix com Google Gemini Vision e Schema estruturado (Pydantic).
  - **📄 Arquivos Bancários (.OFX / .CSV):** Leitura de extratos bancários com detecção automática de formatos e separadores.
  - **🏦 Open Finance (Pluggy):** Sincronização direta de transações bancárias via API.
  - **🛡️ Detecção Rigorosa de Duplicidades:** Gerador de Hash SHA-256 (`Data_Valor_Descrição`) que compara os lotes contra as transações já salvas e contra duplicatas internas.
  - **📋 Conciliação Interativa (Human-in-the-Loop):** Interface com `st.data_editor` permitindo editar categoria, valor e aprovar registros antes de persistir no Google Sheets e SQLite.
- **Modo Demonstração (Fallback inteligente):** O aplicativo carrega dados simulados de altíssima qualidade caso as credenciais reais ainda não tenham sido configuradas. Isso permite testar todos os gráficos e a consultoria da IA instantaneamente!
- **Gráficos Dinâmicos com Plotly:** Gráficos interativos com zoom e exibição de valores nos eixos para facilitar o monitoramento.
- **Benchmarks Nacionais e Internacionais:**
  - **CDI e IPCA:** Coletados diretamente da API do Banco Central do Brasil em tempo real.
  - **Ibovespa e S&P 500:** Coletados do Yahoo Finance (`yfinance`).
- **Inteligência Artificial Gemini:** Diagnóstico sobre sua capacidade de poupança (salário vs gastos), riscos de diversificação e rebalanceamento saudável com base nos seus ativos reais.

---

## 🚀 Upgrades e Melhorias Recentes

- **Módulo de Ingestão Híbrida e Conciliação Humana**: Entrada unificada para OCR Multimodal, arquivos bancários (.OFX/.CSV) e API Open Finance da Pluggy com persistência imediata em lote no Google Sheets e SQLite local.
- **Deduplicação Determinística com Hashing SHA-256**: Prevenção ativa de lançamentos duplicados comparando novos dados com bases históricas.
- **Cálculo de Rentabilidade TWR (Time-Weighted Return) por Cotas**: Implementamos a fórmula matemática padrão da ANBIMA e das corretoras profissionais. Agora, novos aportes e resgates volumosos não causam mais o efeito de "diluição de rentabilidade", gerando gráficos históricos 100% corretos.
- **Normalização Multiplicativa de Splits e Bonificações**: Suporte total a desdobramentos de ativos de forma retroativa e proporcional ao tempo, garantindo que o custo médio e as quantidades históricas fiquem matematicamente alinhados com o estado atual.
- **Correção Dinâmica e Silenciosa de Decimais PT-BR**: Sistema inteligente baseado em Regex para converter, ler e autocorrigir valores do Google Sheets que sofreram distorções de localidade (ponto vs vírgula decimal brasileira).
- **Desacoplamento Completo e Configuração Dinâmica (`.env`)**: Removemos todos os dados sensíveis e tabelas estáticas de splits ou correções de ativos do código-fonte. Agora, tudo é lido de forma dinâmica de variáveis JSON em `.env` (`CORRECOES_CONHECIDAS` e `SPLITS_OFICIAIS`).
- **Sistema de Logs Profissional e Rotativo**: Monitoramento robusto através de um logger rotativo configurado para manter no máximo 3 arquivos de log de até 3MB cada (limpando os mais antigos automaticamente) para garantir a saúde do espaço em disco.

---

## 🩺 Troubleshooting / Resolução de Problemas Comuns

### 1. `NS_ERROR_NET_TIMEOUT` ou `localhost:8502` não responde no navegador

Caso o container esteja ativo (`docker compose logs` exibindo `Uvicorn server started`), mas o navegador dê timeout no Windows:

- **Causa comum:** Travamento no serviço de _localhost forwarding_ do WSL 2.
- **Solução:**
  1. No terminal do PowerShell do Windows (fora do WSL), encerre o WSL:
     ```powershell
     wsl --shutdown
     ```
  2. Abra novamente o WSL e inicie o projeto:
     ```bash
     ./00-iniciar.sh
     ```
  3. Alternativa direta pelo IP interno do WSL no navegador:
     ```bash
     hostname -I | awk '{print $1}'
     # Acesse: http://<IP_DO_WSL>:8502
     ```

### 2. Recriar containers e limpar caches do Docker

```bash
docker compose down -v
docker compose up -d --build
```
