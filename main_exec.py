#!/usr/bin/env python3

import os
import re
import emoji
import math
import asyncio
from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient, events
from binance.um_futures import UMFutures
from binance.error import ClientError

# ─────────── CONFIGURAÇÃO ───────────
API_ID             = int(os.getenv('API_ID', '27677366'))
API_HASH           = os.getenv('API_HASH', '3c15d5e237f3fef52f68fc6c27130735')
PHONE              = os.getenv('PHONE', '+5567991155053')
BINANCE_API_KEY    = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
SIGNALS_GROUP_ID   = int(os.getenv('SIGNALS_GROUP_ID', '-4845548770'))

if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    raise RuntimeError("Faltando BINANCE_API_KEY ou BINANCE_API_SECRET no .env")

# ─────────── INICIALIZAÇÃO ───────────
client = TelegramClient('bot_session', API_ID, API_HASH)
fut    = UMFutures(key=BINANCE_API_KEY, secret=BINANCE_API_SECRET)

# ─── Estado global ───
stop_order_ids   = {}
entry_prices_map = {}
original_sides   = {}

# ─── Helpers ───
def remove_emojis(text: str) -> str:
    return emoji.replace_emoji(text, replace='')

# ─── Parser de sinal ───
def parse_message(text: str):
    text = remove_emojis(text)
    lines = [l.strip() for l in text.splitlines()]
    symbol = side = None
    leverage = 1
    entry = None
    tps = []
    stop = None
    entry_block = tp_block = stop_block = False

    for ln in lines:
        if not ln or ln.lower().startswith('exchanges:'):
            continue

        # Símbolo
        m = re.search(r'#([A-Z0-9]+)/USDT', ln)
        if m:
            symbol = m.group(1) + 'USDT'
            continue

        # Lado
        if 'Signal Type' in ln:
            m = re.search(r'\b(Long|Short)\b', ln, re.IGNORECASE)
            if m:
                side = 'BUY' if m.group(1).lower()=='long' else 'SELL'
            continue

        # Alavancagem
        if 'Leverage' in ln:
            m = re.search(r'(\d+)[xх]', ln)
            if m:
                leverage = int(m.group(1))
            continue

        # Entry
        if ln.lower().startswith('entry targets'):
            entry_block = True
            continue
        if entry_block:
            try: entry = float(ln)
            except: pass
            entry_block = False
            continue

        # TPs
        if ln.lower().startswith('take-profit targets'):
            tp_block = True
            continue
        if tp_block:
            if ln.startswith('🚀'):
                continue
            m = re.search(r'\d+\)\s*([\d.]+)', ln)
            if m:
                tps.append(float(m.group(1)))
                continue
            tp_block = False

        # Stop
        if 'STOP' in ln.upper():
            stop_block = True
            continue
        if stop_block:
            try: stop = float(ln)
            except: pass
            stop_block = False
            continue

    if None in (symbol, side, entry, stop) or not tps:
        return None

    return {
        'symbol': symbol,
        'side': side,
        'leverage': leverage,
        'entry': entry,
        'tps': tps,
        'stop': stop
    }

# ─── Ajuste de precisão ───
def adjust_precision(symbol: str, value: float, value_type: str='price') -> float:
    info = fut.exchange_info()
    si = next(s for s in info['symbols'] if s['symbol']==symbol)
    ftype = 'PRICE_FILTER' if value_type=='price' else 'LOT_SIZE'
    filt  = next(f for f in si['filters'] if f['filterType']==ftype)
    step  = float(filt['tickSize'] if value_type=='price' else filt['stepSize'])
    prec  = int(-math.floor(math.log10(step)))
    if value_type=='quantity':
        q = math.floor(value/step)*step
        return round(q, prec)
    return round(value, prec)

def get_balance() -> float:
    return float(next(x for x in fut.balance() if x['asset']=='USDT')['balance'])

def get_min_quantity(symbol: str) -> float:
    si = next(s for s in fut.exchange_info()['symbols'] if s['symbol']==symbol)
    return float(next(f for f in si['filters'] if f['filterType']=='LOT_SIZE')['minQty'])

# ─── Main ───────
async def main():
    await client.start(PHONE)
    print('🤖 Bot pronto. Aguardando sinais…')

    @client.on(events.NewMessage(chats=SIGNALS_GROUP_ID))
    async def handler(event):
        parsed = parse_message(event.raw_text)
        if not parsed:
            print('⚠️ Fora do padrão:', event.raw_text)
            return
        print('✅ Sinal válido:', parsed)

        # 1) Ajusta alavancagem
        fut.change_leverage(symbol=parsed['symbol'], leverage=parsed['leverage'])

        # 2) Calcula qty
        balance    = get_balance()
        margin     = min(balance * 0.01, 30)
        entry_price= adjust_precision(parsed['symbol'], parsed['entry'], 'price')
        raw_qty    = (margin * parsed['leverage']) / entry_price
        qty        = max(adjust_precision(parsed['symbol'], raw_qty, 'quantity'),
                         get_min_quantity(parsed['symbol']))
        print(f'▶ Qty calculada: {qty} (margem US$ {margin:.2f}, lev {parsed["leverage"]}x)')

        # 3) Cria ordem de entrada
        mark      = float(fut.mark_price(symbol=parsed['symbol'])['markPrice'])
        side      = parsed['side']
        threshold = entry_price * 0.002  # 0.2%
        try:
            if side == 'BUY':
                if mark >= entry_price - threshold:
                    entry = fut.new_order(
                        symbol=parsed['symbol'],
                        side='BUY',
                        type='MARKET',
                        quantity=qty
                    )
                    print(f'▶ Entrada BUY MARKET (id {entry["orderId"]}) @ {mark}')
                else:
                    entry = fut.new_order(
                        symbol=parsed['symbol'],
                        side='BUY',
                        type='STOP_MARKET',
                        stopPrice=str(entry_price),
                        quantity=qty
                    )
                    print(f'▶ Entrada BUY STOP_MARKET (i_
