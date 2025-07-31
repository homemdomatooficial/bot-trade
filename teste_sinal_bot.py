
from trade_executor import executar_trade

def process_signal(msg):
    # Simula o processamento de um sinal no formato padrão do grupo
    if "#SOL/USDT" in msg and "Entry" in msg:
        direcao = "LONG"
        entrada = 162.00
        tps = [165.00, 167.00, 170.00, 175.00]
        simbolo = "SOLUSDT"
        alavancagem = 20
        executar_trade(simbolo, direcao, entrada, tps, alavancagem)

# Simula uma mensagem vinda do grupo de sinais
fake_msg = """🔥 #SOL/USDT (Long📈, x20)
Entry - 162.00
Take-Profit:
🥉 165.00 (40% of profit)
🥈 167.00 (60% of profit)
🥇 170.00 (80% of profit)
🚀 175.00 (100% of profit)
"""

process_signal(fake_msg)
