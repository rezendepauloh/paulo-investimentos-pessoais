@echo off
setlocal enabledelayedexpansion
title Paulo Investimentos - CLI & Ambiente Docker
cd /d "%~dp0"

:: Se executado com parâmetros CLI, processa diretamente
if /i "%~1"=="--start" goto :start_system
if /i "%~1"=="-s" goto :start_system
if /i "%~1"=="--build" goto :start_build
if /i "%~1"=="-b" goto :start_build
if /i "%~1"=="--diagnostico" goto :diagnostico_carteira
if /i "%~1"=="--diag" goto :diagnostico_carteira
if /i "%~1"=="--rebuild" goto :rebuild_docker
if /i "%~1"=="-r" goto :rebuild_docker
if /i "%~1"=="--down" goto :stop_system
if /i "%~1"=="--stop" goto :stop_system
if /i "%~1"=="-d" goto :stop_system
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help

:show_menu
cls
echo ================================================================
echo         PAULO INVESTIMENTOS -- DASHBOARD FINANCEIRO            
echo ================================================================
echo.
echo   Escolha uma opcao:
echo   1 - Iniciar Painel de Investimentos (Streamlit Dashboard)
echo   2 - Reconstruir Docker Compose (--no-cache)
echo   3 - Executar Diagnostico da Carteira Historica
echo   4 - Parar containers (docker compose down)
echo   0 - Sair
echo.
echo ================================================================
set /p "OPCAO=Opcao [0-4]: "

if "%OPCAO%"=="1" goto :start_system
if "%OPCAO%"=="2" goto :rebuild_docker
if "%OPCAO%"=="3" goto :diagnostico_carteira
if "%OPCAO%"=="4" goto :stop_system
if "%OPCAO%"=="0" exit /b 0

echo Opcao invalida.
timeout /t 1 >nul
goto :show_menu

:setup_docker_and_ip
set "LOCAL_IP="
for /f "tokens=4" %%a in ('route print ^| findstr "\<0.0.0.0\>"') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%a"
)
if "%LOCAL_IP%"=="" (
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" /c:"IP Address"') do (
        if not defined LOCAL_IP (
            for /f "tokens=1" %%b in ("%%a") do set "LOCAL_IP=%%b"
        )
    )
)
if "%LOCAL_IP%"=="" set "LOCAL_IP=localhost"

set "PORT=8502"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%i in (".env") do (
        set "KEY=%%i"
        set "VAL=%%j"
        if not "!KEY!"=="" (
            for /f "tokens=* delims= " %%k in ("!KEY!") do set "KEY=%%k"
            if "!KEY!"=="STREAMLIT_PORT" (
                for /f "tokens=* delims= " %%v in ("!VAL!") do set "PORT=%%v"
            )
        )
    )
)
if "%PORT%"=="" set "PORT=8502"
set "PORT=%PORT: =%"
set "PORT=%PORT:"=%"
set "PORT=%PORT:'=%"

where docker >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "DOCKER_CMD=docker compose"
) else (
    where wsl >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "DOCKER_CMD=wsl.exe docker compose"
    ) else (
        echo [ERRO] Nem o Docker para Windows nem o WSL foram encontrados.
        echo Instale o Docker Desktop ou habilite a integracao WSL para continuar.
        pause
        exit /b 1
    )
)
exit /b 0

:start_system
call :setup_docker_and_ip
cls
echo Iniciando Painel de Investimentos (Porta: %PORT% ^| IP: %LOCAL_IP%)...
%DOCKER_CMD% up -d app
timeout /t 2 /nobreak >nul
start http://localhost:%PORT%/
goto :stream_logs

:start_build
call :setup_docker_and_ip
cls
echo Reconstruindo imagem e iniciando Painel de Investimentos...
%DOCKER_CMD% build app
%DOCKER_CMD% up -d app
timeout /t 2 /nobreak >nul
start http://localhost:%PORT%/
goto :stream_logs

:stream_logs
echo ------------------------------------------------------------------------
echo  [C] Limpar Tela  ^|  [R] Reiniciar App  ^|  [B] Navegador  ^|  [Q] Encerrar
echo ------------------------------------------------------------------------
%DOCKER_CMD% logs -f --tail=100 app
echo.
echo Encerrando containers do Paulo Investimentos...
%DOCKER_CMD% down
exit /b 0

:diagnostico_carteira
call :setup_docker_and_ip
cls
echo Executando script de diagnostico da carteira no container...
%DOCKER_CMD% run --rm app python scripts/diagnostico.py
echo.
echo Diagnostico concluido!
pause
goto :show_menu

:rebuild_docker
call :setup_docker_and_ip
cls
echo Reconstruindo imagem Docker Compose (--no-cache)...
%DOCKER_CMD% build --no-cache app
echo.
echo Rebuild concluido!
pause
goto :show_menu

:stop_system
call :setup_docker_and_ip
echo Encerrando containers do Paulo Investimentos...
%DOCKER_CMD% down
echo Containers encerrados com sucesso!
pause
exit /b 0

:show_help
echo Uso: 00-iniciar.cmd [OPCAO]
echo.
echo Opcoes:
echo   --start, -s              Inicia o Painel de Investimentos (Streamlit)
echo   --build, -b              Reconstroi a imagem Docker e inicia
echo   --diagnostico, --diag    Executa o script de diagnostico da carteira
echo   --rebuild, -r            Reconstroi a imagem Docker (--no-cache)
echo   --down, -d               Para os containers do sistema
echo   --help, -h               Exibe esta ajuda
echo   (sem argumentos)         Abre o menu interativo
exit /b 0