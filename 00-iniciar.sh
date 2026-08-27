#!/bin/bash

# Limpa o console
clear

# Direciona para a pasta onde o script está localizado
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}  Iniciando Ambiente Docker - Investimentos  ${NC}"
echo -e "${BLUE}==============================================${NC}"

# Função para encerrar os containers ao pressionar Ctrl+C
cleanup() {
    echo -e "\n${YELLOW}==============================================${NC}"
    echo -e "${YELLOW}  Encerrando containers Docker...             ${NC}"
    echo -e "${YELLOW}==============================================${NC}"
    if command -v docker >/dev/null 2>&1; then
        docker compose down
    fi
    echo -e "${GREEN}[OK] Containers finalizados com sucesso.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

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

# Carrega a porta definida no .env ou assume 8502
STREAMLIT_PORT=$(grep -E '^STREAMLIT_PORT=' .env 2>/dev/null | cut -d '=' -f2 | tr -d '"' | tr -d "'" | tr -d '\r' | tr -d ' ')
STREAMLIT_PORT=${STREAMLIT_PORT:-8502}
export STREAMLIT_PORT

# Detectar IP Local IPv4 no Linux/WSL
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+')
fi
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="localhost"
fi
export HOST_IP="${LOCAL_IP}"

# Verifica se o usuário solicitou reconstrução forçada (--build ou -b)
FORCE_BUILD=false
if [ "$1" == "--build" ] || [ "$1" == "-b" ]; then
    FORCE_BUILD=true
fi

# Verifica se a imagem Docker já foi construída
IMAGE_ID=$(docker compose images -q app 2>/dev/null)
if [ -z "$IMAGE_ID" ]; then
    IMAGE_ID=$(docker images -q paulo-investimentos-pessoais-app:latest 2>/dev/null)
fi

if [ -z "$IMAGE_ID" ] || [ "$FORCE_BUILD" = true ]; then
    echo -e "\n${BLUE}[INFO] Construindo imagem Docker...${NC}"
    if ! docker compose build app; then
        echo -e "\n${RED}[ERRO] Falha ao construir a imagem Docker. Verifique os logs acima.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[OK] Imagem Docker construída com sucesso!${NC}"
fi

# Sobe os containers em background
echo -e "\n${BLUE}Iniciando container com Docker Compose (Porta: ${STREAMLIT_PORT})...${NC}"
if ! docker compose up -d app; then
    echo -e "\n${RED}[ERRO] Falha ao subir os containers.${NC}"
    exit 1
fi

echo -e "\n${GREEN}==============================================${NC}"
echo -e "${GREEN}  Ambiente iniciado com sucesso!              ${NC}"
echo -e "${GREEN}  Local:   http://localhost:${STREAMLIT_PORT}        ${NC}"
if [ "$HOST_IP" != "localhost" ]; then
    echo -e "${GREEN}  Rede:    http://${HOST_IP}:${STREAMLIT_PORT}        ${NC}"
fi
echo -e "${GREEN}==============================================${NC}"
echo -e "${YELLOW}Exibindo logs do container [Pressione Ctrl+C para encerrar os containers]:${NC}\n"
docker compose logs -f app



