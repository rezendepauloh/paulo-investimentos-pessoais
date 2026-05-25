# 📈 Painel de Finanças e Investimentos Pessoais com Streamlit & IA

Este projeto é um painel financeiro profissional construído em Python com **Streamlit**, integrado diretamente com planilhas de Orçamento e de Ordens do Google Sheets. A aplicação realiza o cálculo automático da evolução de patrimônio líquida e compara com os principais benchmarks nacionais e internacionais (**CDI, IPCA, Ibovespa e S&P 500**) a partir de APIs públicas em tempo real, além de fornecer dicas automatizadas de alocação de recursos usando a inteligência artificial do **Google Gemini**.

---

## 🚀 Como Executar o Projeto Localmente

Siga o passo a passo abaixo para rodar o projeto na sua máquina:

### 1. Clonar ou Acessar o Diretório do Projeto

No seu terminal do Windows (PowerShell/CMD), acesse a pasta do projeto:

```bash
cd d:\PythonProjects\paulo-investimentos-pessoais
```

### 2. Criar e Ativar Ambiente Virtual (Recomendado)

Para isolar as dependências e evitar conflitos no seu Python global, crie e ative um ambiente virtual (`venv`):

```powershell
# Cria o ambiente virtual na pasta .venv
python -m venv .venv

# Ativa o ambiente virtual (no PowerShell do Windows)
.venv\Scripts\Activate.ps1

# Ou se estiver usando o CMD tradicional do Windows:
# .venv\Scripts\activate.bat
```

### 3. Instalar as Dependências

Com o ambiente virtual ativado (você verá `(.venv)` no início da linha de comando), instale as dependências:

```bash
pip install -r requirements.txt
```

### 4. Configurar as Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto copiando o modelo do `.env.example`:

```bash
copy .env.example .env
```

Abra o arquivo `.env` e configure:

- Os IDs das suas planilhas (já pré-preenchidos com os seus IDs originais).
- A sua chave da API do Gemini (`GEMINI_API_KEY`), que pode ser obtida gratuitamente em: [Google AI Studio](https://aistudio.google.com/).

### 5. Rodar o Painel Streamlit

Inicie a aplicação localmente:

```bash
streamlit run app.py
```

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

- **Abas Customizadas:** Divisão entre Visão Geral (orçamentos e carteira), Desempenho Histórico, Visualização de Extrato de Lançamentos e Consultoria com IA.
- **Modo Demonstração (Fallback inteligente):** O aplicativo carrega dados simulados de altíssima qualidade caso as credenciais reais ainda não tenham sido configuradas. Isso permite testar todos os gráficos e a consultoria da IA instantaneamente!
- **Gráficos Dinâmicos com Plotly:** Gráficos interativos com zoom e exibição de valores nos eixos para facilitar o monitoramento.
- **Benchmarks Nacionais e Internacionais:**
  - **CDI e IPCA:** Coletados diretamente da API do Banco Central do Brasil em tempo real.
  - **Ibovespa e S&P 500:** Coletados do Yahoo Finance (`yfinance`).
- **Inteligência Artificial Gemini:** Diagnóstico sobre sua capacidade de poupança (salário vs gastos), riscos de diversificação e rebalanceamento saudável com base nos seus ativos reais.
