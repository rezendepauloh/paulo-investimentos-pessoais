# Guia de Instalação e Deploy via Docker Compose

> **Objetivo:** Instruções passo a passo para execução do ambiente de desenvolvimento (WSL/Linux) e produção (Servidor Homelab / Dockge).

---

## 1. Pré-Requisitos e Hardening Local

- **Docker Engine & Docker Compose** (ou Docker Desktop com WSL2 no Windows).
- Arquivo de configuração `.env` preenchido a partir de `.env.example` e protegido com permissão restrita:
  ```bash
  cp .env.example .env
  chmod 600 .env
  ```
- Defina autenticação obrigatória em modo **Fail-Closed** (`REQUIRE_AUTH=true`, `DASHBOARD_AUTH_PASSWORD_HASH`, `DASHBOARD_SESSION_SECRET`) e configure `ALLOWED_HOSTS`.
- Credenciais da Google Cloud (`credentials.json`) inseridas na pasta `data/` com permissão `chmod 600`.
- O contêiner executa como usuário não-privilegiado (`appuser` UID `10001`), com `no-new-privileges:true`, `cap_drop: [ALL]` e bind padrão restrito a `127.0.0.1` (`BIND_ADDRESS=127.0.0.1`).

---

## 2. Inicialização Rápida no WSL / Linux

Para iniciar o contêiner de desenvolvimento com portas e permissões configuradas:

```bash
chmod 755 00-iniciar.sh
./00-iniciar.sh
```

Ou diretamente via Docker Compose:

```bash
docker compose up -d --build
```

A aplicação estará disponível localmente em: **`http://127.0.0.1:8502`** (ou na porta definida em `STREAMLIT_PORT`).

> **Nota sobre permissões do host:** Caso execuções antigas como `root` tenham deixado `data/` ou `logs/` com propriedade `root:root`, corrija no host antes de iniciar o contêiner `appuser` (UID `10001`):
> ```bash
> sudo chown -R 10001:10001 data logs
> chmod 750 data logs
> chmod 600 data/credentials.json data/*.db
> ```

---

## 3. Comandos Úteis do Docker

| Ação | Comando |
| :--- | :--- |
| **Visualizar Logs** | `docker compose logs -f` |
| **Parar Serviços** | `docker compose down` |
| **Reiniciar Aplicação** | `docker compose restart` |
| **Executar Suíte de Testes** | `./00-iniciar.sh --test` |
| **Acessar Terminal do Contêiner** | `docker compose exec app bash` |

---

## 4. Deploy no Servidor de Produção (Homelab / Dockge)

1. Garanta que `.env` possua `HOMELAB_HOST`, `HOMELAB_USER`, `HOMELAB_DEST_DIR`, `REQUIRE_AUTH=true`, `DASHBOARD_AUTH_PASSWORD_HASH` e `DASHBOARD_SESSION_SECRET` (o launcher aborta em **Fail-Closed** caso qualquer item esteja ausente).
2. Execute a opção `6` via `./00-iniciar.sh --deploy` para sincronizar o código e recriar o contêiner com a nova build:
   ```bash
   ./00-iniciar.sh --deploy
   ```
3. Como `docker-compose.server.yml` realiza bind em `127.0.0.1:${PORT:-8094}`, acesse com segurança através de **túnel SSH** ou Proxy Reverso com TLS:
   ```bash
   ssh -L 8094:127.0.0.1:8094 <HOMELAB_USER>@<HOMELAB_HOST>
   ```
4. Caso prefira sincronizar manualmente no servidor remoto após `rsync`/`scp`:
   ```bash
   chmod 750 . data logs && chmod 600 .env data/credentials.json
   docker compose -f docker-compose.server.yml up -d --build --force-recreate app
   ```
