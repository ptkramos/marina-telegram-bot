@echo off
setlocal
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
title Marina Salles Bot - Inicializador Local
cd /d "%~dp0"

echo ===================================================
echo    Iniciando Marina Salles Telegram AI Bot...
echo ===================================================

if not exist venv\Scripts\python.exe (
    echo [INFO] Criando ambiente virtual venv...
    python -m venv venv
    if errorlevel 1 goto failed
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)

echo [INFO] Ativando ambiente virtual...
call venv\Scripts\activate

echo [INFO] Conferindo a preparacao para o soak 3.7.0...
venv\Scripts\python.exe scripts\soak_preflight.py
if errorlevel 1 goto failed

:loop
echo.
echo [INFO] Executando o bot da Marina...
venv\Scripts\python.exe bot.py
if "%errorlevel%"=="2" goto failed
if "%errorlevel%"=="130" exit /b 0
if "%errorlevel%"=="-1073741510" exit /b 0
echo.
echo [INFO] Bot finalizado. Reiniciando processo em 3 segundos...
timeout /t 3 >nul
goto loop

:failed
echo.
echo [ERRO] A inicializacao foi interrompida. Confira a mensagem acima.
pause
exit /b 1
