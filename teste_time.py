cat <<EOF > test_time.py
from binance.um_futures import UMFutures
import os

# Carrega suas credenciais do .env
api_key    = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = UMFutures(key=api_key, secret=api_secret)

# Faz a requisição de hora do servidor da Binance
print(client.time())
EOF
