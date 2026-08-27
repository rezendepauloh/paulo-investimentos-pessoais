#!/bin/bash

# Limpa o console
clear

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}  Iniciando Ambiente Docker - Investimentos  ${NC}"
echo -e "${BLUE}==============================================${NC}"


# Verifica se o Docker daemon está ativo
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}[ERRO] O Docker daemon não está rodando no WSL/Host.${NC}"
    echo -e "${YELLOW}Inicie o Docker Desktop ou o serviço Docker e tente novamente.${NC}"
    exit 1
fi

# Verifica se o arquivo .env existe
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}[AVISO] Arquivo .env não encontrado.${NC}"
    if [ -f ".env.example" ]; then
        echo -e "${BLUE}Copiando .env.example para .env...${NC}"
        cp .env.example .env
        echo -e "${GREEN}[OK] .env criado a partir de .env.example.${NC}"
    fi
fi

# Carrega a porta definida no .env ou assume 8501
STREAMLIT_PORT=$(grep -E '^STREAMLIT_PORT=' .env | cut -d '=' -f2 | tr -d '"' | tr -d "'" | tr -d '\r')
STREAMLIT_PORT=${STREAMLIT_PORT:-8501}

# Função para encerrar os containers ao pressionar Ctrl+C
cleanup() {
    echo -e "\n${YELLOW}Encerrando containers Docker...${NC}"
    docker compose down
    echo -e "${GREEN}Containers finalizados com sucesso.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Build e inicialização dos containers (sempre reconstrói se houver alterações)
echo -e "\n${BLUE}Verificando alterações e subindo container com Docker Compose (Porta: ${STREAMLIT_PORT})...${NC}"
docker compose up -d --build

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}==============================================${NC}"
    echo -e "${GREEN}  Ambiente iniciado com sucesso!              ${NC}"
    echo -e "${GREEN}  Acesse: http://localhost:${STREAMLIT_PORT}           ${NC}"
    echo -e "${GREEN}==============================================${NC}"
    echo -e "${YELLOW}Exibindo logs do container [Pressione Ctrl+C para encerrar os containers]:${NC}\n"
    docker compose logs -f
else
    echo -e "\n${RED}[ERRO] Falha ao subir os containers.${NC}"
    exit 1
fi


