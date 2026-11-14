#!/usr/bin/env bash
# =======================================================================
#       PAULO INVESTIMENTOS PESSOAIS — CLI & AMBIENTE DOCKER
# =======================================================================

cd "$(dirname "$0")" || exit 1

# Paleta de Cores ANSI
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_CYAN="\033[36m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"
C_MAGENTA="\033[35m"
C_GRAY="\033[90m"

# Verifica se o Docker daemon está ativo
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo -e "${C_RED}[ERRO] O Docker daemon não está rodando.${C_RESET}"
        echo -e "${C_YELLOW}Inicie o Docker Desktop ou o serviço Docker e tente novamente.${C_RESET}"
        exit 1
    fi
}

detect_ip() {
    LOCAL_IP=""
    # 1. Se estiver no WSL, tenta obter o IP do adaptador de rede Windows real
    if [ -f /proc/sys/fs/binfmt_misc/WSLInterop ] || [ -n "$WSL_DISTRO_NAME" ]; then
        if command -v powershell.exe >/dev/null 2>&1; then
            WIN_IP=$(powershell.exe -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { (\$_.IPAddress -like '192.168.*' -or \$_.IPAddress -like '10.*') -and \$_.IPAddress -notlike '192.168.56.*' -and \$_.InterfaceAlias -notlike '*Virtual*' -and \$_.InterfaceAlias -notlike '*vEthernet*' } | Select-Object -ExpandProperty IPAddress -First 1)" 2>/dev/null | tr -d '\r\n')
            if [ -n "$WIN_IP" ]; then
                LOCAL_IP="$WIN_IP"
            fi
        fi
    fi

    # 2. Se não detectou ou está em Linux nativo, usa hostname -I
    if [ -z "$LOCAL_IP" ]; then
        if command -v hostname >/dev/null 2>&1; then
            LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        fi

        if [ -z "$LOCAL_IP" ] || [ "$LOCAL_IP" = "127.0.0.1" ]; then
            if command -v ip >/dev/null 2>&1; then
                LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+')
            fi
        fi
    fi

    # 3. Fallback
    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP="localhost"
    fi

    export HOST_IP="${LOCAL_IP}"
}

read_env_var() {
    local key="$1"
    local val="${!key:-}"
    if [ -z "$val" ] && [ -f ".env" ]; then
        val=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" .env | tail -n 1 | cut -d '=' -f 2- | tr -d ' "\r\n' | tr -d "'")
    fi
    printf '%s' "$val"
}

validate_port() {
    local p="$1"
    [[ "$p" =~ ^[0-9]{2,5}$ ]] && [ "$p" -ge 1 ] && [ "$p" -le 65535 ]
}

load_env_file() {
    if [ ! -f ".env" ]; then
        echo -e "${C_YELLOW}[AVISO] Arquivo .env não encontrado.${C_RESET}"
        if [ -f ".env.example" ]; then
            echo -e "${C_CYAN}Copiando .env.example para .env (modo restrito chmod 600)...${C_RESET}"
            umask 077
            cp .env.example .env
            chmod 600 .env
            echo -e "${C_GREEN}[OK] .env criado a partir de .env.example com permissão 600.${C_RESET}"
        fi
    fi

    if [ -f .env ]; then
        chmod 600 .env 2>/dev/null || true
        local env_port
        env_port=$(read_env_var "PORT")
        if [ -z "$env_port" ]; then
            env_port=$(read_env_var "STREAMLIT_PORT")
        fi
        if [ -n "$env_port" ]; then
            if ! validate_port "$env_port"; then
                echo -e "${C_RED}❌ PORT inválida detectada no .env: '$env_port'. Abortando (Fail-Closed).${C_RESET}"
                exit 1
            fi
            PORT="$env_port"
        fi
    fi
    PORT="${PORT:-8502}"
    if ! validate_port "$PORT"; then
        echo -e "${C_RED}❌ PORT inválida: '$PORT'. Abortando (Fail-Closed).${C_RESET}"
        exit 1
    fi
    export PORT="$PORT"
    export STREAMLIT_PORT="$PORT"
}

open_browser() {
    local port="${1:-$PORT}"
    local url="http://localhost:${port}/"
    if [ -f /proc/sys/fs/binfmt_misc/WSLInterop ] || [ -n "$WSL_DISTRO_NAME" ]; then
        if command -v cmd.exe >/dev/null 2>&1; then
            cmd.exe /c start "$url" >/dev/null 2>&1 &
            return
        elif command -v powershell.exe >/dev/null 2>&1; then
            powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1 &
            return
        fi
    fi

    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
    elif command -v gnome-open >/dev/null 2>&1; then
        gnome-open "$url" >/dev/null 2>&1 &
    fi
}

cleanup() {
    trap - INT TERM EXIT
    # Restaura cursor caso tenha sido ocultado
    tput cnorm 2>/dev/null
    # Desativa scrolling region caso ativa
    local rows
    rows=$(tput lines 2>/dev/null || echo 24)
    printf "\033[1;%dr" "$rows" 2>/dev/null
    printf "\033[%d;1H\n" "$rows" 2>/dev/null

    echo ""
    echo -e "${C_YELLOW}Encerrando containers do Paulo Investimentos...${C_RESET}"
    if command -v docker >/dev/null 2>&1; then
        docker compose down
    fi
    echo -e "${C_GREEN}[OK] Containers finalizados com sucesso.${C_RESET}"
    exit 0
}

# Desenha a barra fixa no rodapé da janela do terminal
render_bottom_toolbar() {
    local rows
    rows=$(tput lines 2>/dev/null || echo 24)
    local cols
    cols=$(tput cols 2>/dev/null || echo 80)
    local sep_len=$(( cols - 2 ))
    [ "$sep_len" -lt 10 ] && sep_len=70

    # Salva posição do cursor e desce para as duas últimas linhas
    tput sc 2>/dev/null
    printf "\033[%d;1H" $(( rows - 1 ))
    echo -ne "${C_GRAY}─${C_RESET}"
    printf "${C_GRAY}%%0.s─${C_RESET}" $(seq 1 "$sep_len")
    printf "\033[K\n"
    printf " ${C_BOLD}[c]${C_RESET} ${C_YELLOW}Limpar Logs${C_RESET} | ${C_BOLD}[r]${C_RESET} ${C_CYAN}Reiniciar App${C_RESET} | ${C_BOLD}[b]${C_RESET} ${C_GREEN}Navegador${C_RESET} | ${C_BOLD}[q]${C_RESET} ${C_RED}Encerrar${C_RESET}\033[K"
    tput rc 2>/dev/null
}

setup_terminal_split() {
    local rows
    rows=$(tput lines 2>/dev/null || echo 24)
    # Define a região de rolagem (scrolling region) da linha 1 até (rows - 2)
    # Assim, os logs nunca sobrescrevem as duas linhas de baixo!
    printf "\033[1;%dr" $(( rows - 2 )) 2>/dev/null
    render_bottom_toolbar
}

stream_interactive_logs() {
    local LOG_PID=""

    # Configura a tela dividida com barra fixa no rodapé
    setup_terminal_split

    # Trata redimensionamento de janela (SIGWINCH)
    trap 'setup_terminal_split' WINCH

    # Inicia streaming dos logs do container dentro da área de rolagem
    docker compose logs -f --tail=100 app &
    LOG_PID=$!

    # Loop de escuta de comandos de teclado em tempo real
    while kill -0 "$LOG_PID" 2>/dev/null; do
        if read -r -s -n 1 -t 1 key; then
            case "$key" in
                c|C)
                    clear
                    setup_terminal_split
                    ;;
                r|R)
                    kill "$LOG_PID" 2>/dev/null
                    clear
                    echo -e "${C_YELLOW}Reiniciando serviço app...${C_RESET}"
                    docker compose restart app
                    clear
                    setup_terminal_split
                    docker compose logs -f --tail=50 app &
                    LOG_PID=$!
                    ;;
                b|B)
                    open_browser "$PORT"
                    ;;
                q|Q)
                    kill "$LOG_PID" 2>/dev/null
                    cleanup
                    ;;
            esac
        fi
    done

    wait "$LOG_PID" 2>/dev/null
}

start_system() {
    local force_build="${1:-false}"
    check_docker
    load_env_file
    detect_ip

    clear
    echo -e "${C_CYAN}${C_BOLD}==============================================================${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}   Iniciando Painel de Investimentos (Porta: ${PORT} | IP: ${HOST_IP})   ${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}==============================================================${C_RESET}"

    # Checa se precisa de build
    IMAGE_ID=$(docker compose images -q app 2>/dev/null)
    if [ -z "$IMAGE_ID" ]; then
        IMAGE_ID=$(docker images -q paulo-investimentos-pessoais-app:latest 2>/dev/null)
    fi

    if [ -z "$IMAGE_ID" ] || [ "$force_build" = true ]; then
        echo -e "${C_YELLOW}Construindo imagem Docker Compose...${C_RESET}"
        if ! docker compose build app; then
            echo -e "${C_RED}[ERRO] Falha ao construir a imagem Docker.${C_RESET}"
            exit 1
        fi
        echo -e "${C_GREEN}[OK] Imagem construída com sucesso!${C_RESET}"
    fi

    if ! docker compose up -d app; then
        echo -e "${C_RED}[ERRO] Falha ao subir os containers do Paulo Investimentos.${C_RESET}"
        exit 1
    fi

    echo -e "\n${C_GREEN}Ambiente iniciado com sucesso!${C_RESET}"
    echo -e "  ${C_GREEN}Local:${C_RESET}   http://localhost:${PORT}/"
    if [ "$HOST_IP" != "localhost" ]; then
        echo -e "  ${C_GREEN}Rede:${C_RESET}    http://${HOST_IP}:${PORT}/"
    fi
    echo ""

    open_browser "$PORT"
    trap cleanup INT TERM EXIT

    stream_interactive_logs
}

diagnostico_carteira() {
    check_docker
    load_env_file
    clear
    echo -e "${C_CYAN}Executando script de diagnóstico da carteira no container...${C_RESET}"
    docker compose run --rm \
        -v "$(pwd)/scripts:/app/scripts:ro" \
        app python scripts/diagnostico.py
    echo ""
    echo -e "${C_GREEN}Diagnóstico concluído!${C_RESET}"
    read -p "Pressione ENTER para voltar ao menu..." dummy
}

rodar_testes() {
    check_docker
    load_env_file
    clear
    echo -e "${C_CYAN}Executando Suíte de Testes Automatizados no container...${C_RESET}"
    local -a TEST_VOLUMES=(-v "$(pwd)/tests:/app/tests:ro" -v "$(pwd)/scripts:/app/scripts:ro")
    if [ -d "$(pwd)/temp" ]; then
        TEST_VOLUMES+=(-v "$(pwd)/temp:/app/temp:ro")
    fi
    for host_cfg in Dockerfile docker-compose.yml docker-compose.server.yml .gitignore .dockerignore .env.example 00-iniciar.sh 00-iniciar.cmd; do
        if [ -f "$(pwd)/${host_cfg}" ]; then
            TEST_VOLUMES+=(-v "$(pwd)/${host_cfg}:/app/${host_cfg}:ro")
        fi
    done
    docker compose run --rm "${TEST_VOLUMES[@]}" app python tests/run_all.py
    local status=$?
    echo ""
    if [ $status -eq 0 ]; then
        echo -e "${C_GREEN}Suíte de testes finalizada com sucesso!${C_RESET}"
    else
        echo -e "${C_RED}Foram encontrados erros na execução dos testes.${C_RESET}"
    fi
    if [ -t 0 ]; then
        read -p "Pressione ENTER para voltar ao menu..." dummy
    fi
    return "$status"
}

rebuild_docker() {
    check_docker
    clear
    echo -e "${C_MAGENTA}Reconstruindo imagem Docker Compose (--no-cache)...${C_RESET}"
    docker compose build --no-cache app
    echo ""
    echo -e "${C_GREEN}Rebuild concluído com sucesso!${C_RESET}"
    read -p "Pressione ENTER para voltar ao menu..." dummy
}

stop_system() {
    check_docker
    echo -e "${C_YELLOW}Encerrando containers do Paulo Investimentos...${C_RESET}"
    docker compose down
    echo -e "${C_GREEN}Containers encerrados com sucesso!${C_RESET}"
}

deploy_homelab() {
    clear
    echo -e "${C_CYAN}${C_BOLD}==============================================================${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}   🚀 DEPLOY REMOTO NO HOMELAB (MODO FAIL-CLOSED)            ${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}==============================================================${C_RESET}"
    echo ""

    if [ ! -f ".env" ]; then
        echo -e "${C_RED}❌ Erro Fail-Closed: Arquivo .env obrigatório não encontrado.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi

    load_env_file

    local HOST USER PORT_SSH DEST_DIR SSH_KEY SERVER_APP_PORT REQ_AUTH_VAL AUTH_HASH_VAL AUTH_PLAIN_VAL SESSION_SECRET_VAL
    HOST=$(read_env_var "HOMELAB_HOST")
    USER=$(read_env_var "HOMELAB_USER")
    PORT_SSH=$(read_env_var "HOMELAB_PORT")
    PORT_SSH="${PORT_SSH:-22}"
    DEST_DIR=$(read_env_var "HOMELAB_DEST_DIR")
    SSH_KEY=$(read_env_var "HOMELAB_SSH_KEY")
    SSH_KEY="${SSH_KEY:-~/.ssh/id_ed25519}"
    SSH_KEY="${SSH_KEY/#\~/$HOME}"
    SERVER_APP_PORT=$(read_env_var "HOMELAB_PORT_APP")
    SERVER_APP_PORT="${SERVER_APP_PORT:-8094}"
    REQ_AUTH_VAL=$(read_env_var "REQUIRE_AUTH")
    AUTH_HASH_VAL=$(read_env_var "DASHBOARD_AUTH_PASSWORD_HASH")
    AUTH_PLAIN_VAL=$(read_env_var "DASHBOARD_ACCESS_PASSWORD")
    SESSION_SECRET_VAL=$(read_env_var "DASHBOARD_SESSION_SECRET")

    # Trava Fail-Closed: nunca deploya sem variáveis essenciais válidas ou com senha de painel ausente
    if [ -z "$HOST" ] || [ -z "$USER" ] || [ -z "$DEST_DIR" ]; then
        echo -e "${C_RED}❌ Erro Fail-Closed: HOMELAB_HOST, HOMELAB_USER e HOMELAB_DEST_DIR são obrigatórios no .env.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi

    if [[ ! "$HOST" =~ ^[a-zA-Z0-9._-]+$ ]] || [[ ! "$USER" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        echo -e "${C_RED}❌ Erro Fail-Closed: HOMELAB_HOST ou HOMELAB_USER contém caracteres inválidos.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi

    if [[ ! "$DEST_DIR" =~ ^/[a-zA-Z0-9._/-]+$ ]] || [[ "$DEST_DIR" == *".."* ]]; then
        echo -e "${C_RED}❌ Erro Fail-Closed: HOMELAB_DEST_DIR inválido ou com path traversal: ${DEST_DIR}${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi

    if ! validate_port "$PORT_SSH" || ! validate_port "$SERVER_APP_PORT"; then
        echo -e "${C_RED}❌ Erro Fail-Closed: HOMELAB_PORT ou HOMELAB_PORT_APP inválido.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi

    if [ "${REQ_AUTH_VAL,,}" = "false" ] || { [ -z "$AUTH_HASH_VAL" ] && [ -z "$AUTH_PLAIN_VAL" ]; } || [ ${#SESSION_SECRET_VAL} -lt 16 ]; then
        echo -e "${C_RED}❌ Erro Fail-Closed: Deploy remoto bloqueado sem REQUIRE_AUTH=true, DASHBOARD_AUTH_PASSWORD_HASH e DASHBOARD_SESSION_SECRET (>= 16 chars).${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi

    local -a SSH_OPTS=(-p "${PORT_SSH}" -o StrictHostKeyChecking=accept-new)
    local -a SCP_OPTS=(-P "${PORT_SSH}" -o StrictHostKeyChecking=accept-new)
    if [ -f "$SSH_KEY" ]; then
        chmod 600 "$SSH_KEY" 2>/dev/null || true
        SSH_OPTS+=(-i "$SSH_KEY")
        SCP_OPTS+=(-i "$SSH_KEY")
    fi

    local RSYNC_SSH_CMD
    printf -v RSYNC_SSH_CMD '%q ' ssh "${SSH_OPTS[@]}"

    local SAFE_DEST_DIR
    printf -v SAFE_DEST_DIR '%q' "${DEST_DIR}"

    # 1. Testar conectividade (Ping)
    echo -e "${C_YELLOW}[1/5] Verificando conectividade com o servidor (${HOST})...${C_RESET}"
    if ! ping -c 1 -W 2 "$HOST" >/dev/null 2>&1; then
        echo -e "${C_RED}❌ Não foi possível alcançar ${HOST}. Verifique se o servidor está ligado e conectado na rede.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi
    echo -e "${C_GREEN}✅ Servidor ${HOST} respondendo perfeitamente!${C_RESET}"
    echo ""

    # 2. Criar diretório remoto com permissões restritas (menor privilégio)
    echo -e "${C_YELLOW}[2/5] Garantindo diretório da stack no servidor (${DEST_DIR})...${C_RESET}"
    ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "mkdir -p ${SAFE_DEST_DIR}/data ${SAFE_DEST_DIR}/logs && chmod 750 ${SAFE_DEST_DIR} ${SAFE_DEST_DIR}/data ${SAFE_DEST_DIR}/logs"
    if [ $? -ne 0 ]; then
        echo -e "${C_RED}❌ Falha na comunicação SSH com ${USER}@${HOST}.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi
    echo -e "${C_GREEN}✅ Diretório e pastas de persistência preparados com segurança!${C_RESET}"
    echo ""

    # 3. Sincronizar arquivos via Rsync (com exclusões seguras)
    echo -e "${C_YELLOW}[3/5] Enviando código-fonte e assets via rsync...${C_RESET}"
    rsync -avz \
        -e "$RSYNC_SSH_CMD" \
        --exclude '.git' \
        --exclude '.venv' \
        --exclude '__pycache__' \
        --exclude '.pytest_cache' \
        --exclude 'logs' \
        --exclude 'scratch' \
        --exclude 'temp' \
        --exclude '.env' \
        --exclude 'data' \
        --exclude 'docker-compose.yml' \
        --exclude 'docker-compose.server.yml' \
        ./ "${USER}@${HOST}:${DEST_DIR}/"

    if [ $? -ne 0 ]; then
        echo -e "${C_RED}❌ Erro durante a transferência rsync.${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi
    echo -e "${C_GREEN}✅ Código-fonte sincronizado com sucesso!${C_RESET}"
    echo ""

    # 4. Configurar docker-compose.yml, credenciais e .env de produção no servidor
    echo -e "${C_YELLOW}[4/5] Configurando docker-compose e .env de produção no servidor...${C_RESET}"

    if [ -f "data/credentials.json" ]; then
        echo -e "${C_CYAN}Enviando data/credentials.json para o servidor (chmod 600)...${C_RESET}"
        scp "${SCP_OPTS[@]}" "data/credentials.json" "${USER}@${HOST}:${DEST_DIR}/data/credentials.json"
        ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "chmod 600 ${SAFE_DEST_DIR}/data/credentials.json"
    fi

    # Prepara arquivo temporário seguro com umask 077 e cleanup automático
    local TEMP_PROD_ENV
    TEMP_PROD_ENV=$(umask 077 && mktemp)
    trap 'rm -f "$TEMP_PROD_ENV"' RETURN
    cp .env "$TEMP_PROD_ENV"
    chmod 600 "$TEMP_PROD_ENV"

    if grep -q '^PORT=' "$TEMP_PROD_ENV"; then
        sed -i "s/^PORT=.*/PORT=${SERVER_APP_PORT}/" "$TEMP_PROD_ENV"
    else
        echo "PORT=${SERVER_APP_PORT}" >> "$TEMP_PROD_ENV"
    fi

    if grep -q '^STREAMLIT_PORT=' "$TEMP_PROD_ENV"; then
        sed -i "s/^STREAMLIT_PORT=.*/STREAMLIT_PORT=${SERVER_APP_PORT}/" "$TEMP_PROD_ENV"
    fi

    scp "${SCP_OPTS[@]}" "$TEMP_PROD_ENV" "${USER}@${HOST}:${DEST_DIR}/.env"
    ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "chmod 600 ${SAFE_DEST_DIR}/.env"
    rm -f "$TEMP_PROD_ENV"

    if [ -f "docker-compose.server.yml" ]; then
        scp "${SCP_OPTS[@]}" "docker-compose.server.yml" "${USER}@${HOST}:${DEST_DIR}/docker-compose.yml"
    else
        echo -e "${C_RED}❌ Arquivo docker-compose.server.yml não encontrado!${C_RESET}"
        read -p "Pressione ENTER para voltar ao menu..." dummy
        return 1
    fi
    echo -e "${C_GREEN}✅ Arquivos de ambiente e stack compose configurados!${C_RESET}"
    echo ""

    # 5. Executar Build e Up no Docker do servidor remoto
    echo -e "${C_YELLOW}[5/5] Reiniciando aplicação com a nova build no servidor remoto...${C_RESET}"
    ssh -t "${SSH_OPTS[@]}" "${USER}@${HOST}" "cd ${SAFE_DEST_DIR} && (docker compose up -d --build app || sudo docker compose up -d --build app)"

    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${C_GREEN}${C_BOLD}🎉 DEPLOY CONCLUÍDO COM SUCESSO NO HOMELAB!${C_RESET}"
        echo -e "Para acessar com segurança (bind 127.0.0.1), abra um túnel SSH:"
        echo -e "  ${C_CYAN}ssh -L ${SERVER_APP_PORT}:127.0.0.1:${SERVER_APP_PORT} ${USER}@${HOST}${C_RESET}"
    else
        echo -e "${C_RED}❌ Ocorreu um erro ao iniciar a stack no servidor remoto.${C_RESET}"
    fi
    echo ""
    read -p "Pressione [Enter] para voltar ao menu..." dummy
}

show_menu() {
    clear
    echo -e "${C_CYAN}${C_BOLD}╔══════════════════════════════════════════════════════════════╗${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║         PAULO INVESTIMENTOS — DASHBOARD FINANCEIRO           ║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║                                                              ║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_BOLD}Escolha uma opção:${C_RESET}                                          ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_GREEN}1${C_RESET} - Iniciar Painel de Investimentos (Streamlit)             ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_GREEN}2${C_RESET} - Reconstruir Imagem Docker (--no-cache)                  ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_GREEN}3${C_RESET} - Executar Diagnóstico da Carteira Histórica              ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_GREEN}4${C_RESET} - 🧪 Executar Suíte de Testes Automatizados               ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_GREEN}5${C_RESET} - Parar containers (docker compose down)                  ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_MAGENTA}6${C_RESET} - 🚀 Deploy no Mini PC (Dockge / Homelab)                 ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}║${C_RESET}  ${C_RED}0${C_RESET} - Sair                                                    ${C_CYAN}${C_BOLD}║${C_RESET}"
    echo -e "${C_CYAN}${C_BOLD}╚══════════════════════════════════════════════════════════════╝${C_RESET}"
    echo ""
    read -p "Opção [0-6]: " opcao
    case "$opcao" in
        1) start_system false ;;
        2) rebuild_docker; show_menu ;;
        3) diagnostico_carteira; show_menu ;;
        4) rodar_testes; show_menu ;;
        5) stop_system ;;
        6) deploy_homelab; show_menu ;;
        0) exit 0 ;;
        *) echo -e "${C_RED}Opção inválida.${C_RESET}"; sleep 1; show_menu ;;
    esac
}

case "$1" in
    --start|-s)
        start_system false
        ;;
    --build|-b)
        start_system true
        ;;
    --diagnostico|--diag)
        diagnostico_carteira
        ;;
    --test|--tests|-t)
        rodar_testes
        ;;
    --rebuild|-r)
        rebuild_docker
        ;;
    --down|--stop|-d)
        stop_system
        ;;
    --deploy|-dp)
        deploy_homelab
        ;;
    --help|-h)
        echo "Uso: ./00-iniciar.sh [OPÇÃO]"
        echo ""
        echo "Opções:"
        echo "  --start, -s              Inicia o Painel de Investimentos"
        echo "  --build, -b              Reconstrói a imagem e inicia"
        echo "  --diagnostico, --diag    Executa o script de diagnóstico da carteira"
        echo "  --test, --tests, -t      Executa a suíte de testes automatizados"
        echo "  --rebuild, -r            Reconstrói a imagem Docker (--no-cache)"
        echo "  --down, -d               Para os containers do sistema"
        echo "  --deploy, -dp            Executa deploy no Mini PC (Dockge / Homelab)"
        echo "  --help, -h               Exibe esta ajuda"
        echo "  (sem argumentos)         Abre o menu interativo"
        ;;
    *)
        show_menu
        ;;
esac

