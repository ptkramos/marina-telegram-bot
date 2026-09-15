@echo off
title Marina Seltin Bot - Inicializador Local
cd /d "%~dp0"

echo ===================================================
echo    Iniciando Marina Seltin Telegram AI Bot...
echo ===================================================

if not exist venv (
    echo [INFO] Criando ambiente virtual venv...
    python -m venv venv
)

echo [INFO] Ativando ambiente virtual...
call venv\Scripts\activate

echo [INFO] Verificando dependencias...
pip install -r requirements.txt --quiet

:loop
echo.
echo [INFO] Executando o bot da Marina...
python bot.py
echo.
echo [INFO] Bot finalizado. Reiniciando processo em 3 segundos...
timeout /t 3 >nul
goto loop
