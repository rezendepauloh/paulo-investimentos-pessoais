# Guia de Instalação e Deploy via Docker Compose

> **Objetivo:** Instruções passo a passo para execução do ambiente de desenvolvimento (WSL/Linux) e produção (Servidor Homelab / Dockge).

---

## 1. Pré-Requisitos

- **Docker Engine & Docker Compose** (ou Docker Desktop com WSL2 no Windows).
- Arquivo de configuração de ambiente `.env` preenchido a partir de `.env.example`.
- Credenciais da Google Cloud (`credentials.json`) inseridas na pasta `data/`.

---

## 2. Inicialização Rápida no WSL / Linux

Para iniciar o contêiner de desenvolvimento com portas e permissões configuradas:

```bash
chmod +x 00-iniciar.sh
./00-iniciar.sh
```

Ou diretamente via Docker Compose:

```bash
docker compose up -d --build
```

A aplicação estará disponível em: **`http://localhost:8502`** (ou na porta definida em `STREAMLIT_PORT`).

---

## 3. Comandos Úteis do Docker

| Ação | Comando |
| :--- | :--- |
| **Visualizar Logs** | `docker compose logs -f` |
| **Parar Serviços** | `docker compose down` |
| **Reiniciar Aplicação** | `docker compose restart` |
| **Acessar Terminal do Contêiner** | `docker compose exec paulo-investimentos-app bash` |

---

## 4. Deploy no Servidor de Produção (Homelab / Dockge)

Para rodar em ambiente servidor contínuo com reinicialização automática (`restart: unless-stopped`):

```bash
docker compose -f docker-compose.server.yml up -d
```

