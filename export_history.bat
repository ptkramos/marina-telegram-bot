@echo off
REM Exporta a conversa recente da Marina para scratchpad/conversation_export_*.txt
REM Uso:
REM   export_history.bat              -> ultimas 48h
REM   export_history.bat --hours 12   -> ultimas 12h
REM   export_history.bat --last 200   -> ultimos 200 turnos

cd /d "%~dp0"
call venv\Scripts\python.exe scripts\export_conversation_history.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Falha no export. Verifique se o venv esta configurado.
    pause
    exit /b 1
)
echo.
echo Arquivo pronto em scratchpad\ ^; copie e cole aqui na conversa quando o Claude pedir.
pause
