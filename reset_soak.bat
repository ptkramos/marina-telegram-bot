@echo off
REM Reset completo do soak — banco zerado, canon preservado.
REM Uso:
REM   reset_soak.bat              -> dry-run (mostra o que faria)
REM   reset_soak.bat --apply      -> executa (com backup automatico)

cd /d "%~dp0"
call venv\Scripts\python.exe scripts\reset_soak.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Falha no reset. Verifique se o bot esta parado e o venv esta configurado.
    pause
    exit /b 1
)
echo.
pause
