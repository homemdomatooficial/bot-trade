@echo off
echo ========================================
echo   INSTALADOR BOT BINANCE - HOMEM DO MATO
echo ========================================
echo.

:: Verifica se o Python já está instalado
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python não encontrado. Abrindo página de download...
    start https://www.python.org/downloads/windows/
    pause
    exit /b
)

echo Instalando dependências...
python -m pip install --upgrade pip
python -m pip install python-binance telethon python-dotenv

echo.
echo Iniciando o bot...
python main.py

pause
