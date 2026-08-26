@echo off
title Paulo Investimentos - Docker Dev
echo ========================================================
echo   Iniciando Ambiente Docker via WSL...
echo ========================================================
wsl bash -c "cd $(wslpath '%~dp0') && chmod +x 00-iniciar.sh && ./00-iniciar.sh"
pause