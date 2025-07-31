@echo off
REM — Ajuste estes valores se você não estiver usando .env —
set API_ID=27677366
set API_HASH=3c15d5e237f3fef52f68fc6c27130735
set PHONE=+5567991155053
set BINANCE_API_KEY=8M1yjHlS5ve5zfkDS3aSNhqgjEmhx6NO29nCUVv3SDSw0SMxSNXJxBV3gPZj5GJS
set BINANCE_API_SECRET=Td4kJzT4TybgTMIYIis6HqIAHgGBDKmLgJDZ3YWanCTUO2VFnGmehTqCVmsKtuLe
set SIGNALS_GROUP_ID=-4845548770

REM Vai para o diretório do .bat e roda o bot
cd /d "%~dp0"
python main_exec.py

pause
