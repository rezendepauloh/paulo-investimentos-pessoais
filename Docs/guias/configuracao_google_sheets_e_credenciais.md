# Configuração de Credenciais & Google Sheets

> **Objetivo:** Instruções para criação de Conta de Serviço na Google Cloud Platform e parametrização do arquivo `.env`.

---

## 1. Como Obter a Chave da Conta de Serviço (`credentials.json`)

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie ou selecione o projeto do aplicativo.
3. Ative as seguintes APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Navegue até **IAM e Administração** ➔ **Contas de Serviço**.
5. Crie uma nova conta de serviço e gere uma chave no formato **JSON**.
6. Renomeie o arquivo baixado para `credentials.json` e salve-o na pasta:
   ```text
   data/credentials.json
   ```
7. **Importante:** Abra cada planilha do Google Sheets que será sincronizada e compartilhe com o e-mail da conta de serviço (com permissão de *Editor*).

---

## 2. Configuração do Arquivo `.env` e Segurança Fail-Closed

Copie o modelo de exemplo e restrinja a leitura imediatamente:

```bash
cp .env.example .env
chmod 600 .env
chmod 600 data/credentials.json
```

Parâmetros fundamentais:
- `SPREADSHEET_BUDGET_ID_<ANO>`: ID da planilha de orçamento do ano correspondente.
- `SPREADSHEET_ORDERS_ID`: ID da planilha contendo o histórico de compras e vendas de ativos.
- `GEMINI_API_KEY`: Chave de API do Google Gemini obtida no [Google AI Studio](https://aistudio.google.com/).
- `REQUIRE_AUTH`: Mantenha `true` (padrão Fail-Closed — obrigatório em produção).
- `DASHBOARD_AUTH_PASSWORD_HASH`: Hash PBKDF2-HMAC-SHA256 da senha do painel (gere via `python3 -c "from src.utils.security import hash_password_pbkdf2; print(hash_password_pbkdf2('SUA_SENHA'))"`).
- `DASHBOARD_SESSION_SECRET`: Segredo HMAC aleatório (`python3 -c "import secrets; print(secrets.token_hex(32))"`).
- `ALLOWED_HOSTS`: Lista de cabeçalhos `Host` autorizados (ex: `localhost,127.0.0.1`).
- `STREAMLIT_PORT`: Porta local da interface web (padrão: `8502`, bind em `127.0.0.1`).
- `PLUGGY_CLIENT_ID` / `PLUGGY_CLIENT_SECRET`: Credenciais para Open Finance (opcional).
- `HOMELAB_HOST` / `HOMELAB_USER` / `HOMELAB_DEST_DIR`: Obrigatórios quando utilizar deploy remoto (`./00-iniciar.sh --deploy`).

