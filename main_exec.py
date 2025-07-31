#!/usr/bin/env python3

import os
import re
import emoji
import math
import asyncio
from telethon import TelegramClient, events
from binance.um_futures import UMFutures
from binance.error import ClientError

# ─────────── CONFIGURAÇÃO ───────────
API_ID             = int(os.getenv('API_ID', '27677366'))
API_HASH           = os.getenv('API_HASH', '3c15d5e237f3fef52f68fc6c27130735')
PHONE              = os.getenv('PHONE', '+5567991155053')
BINANCE_API_KEY    = os.getenv('BINANCE_API_KEY', 'YOUR_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', 'YOUR_SECRET')
SIGNALS_GROUP_ID   = int(os.getenv('SIGNALS_GROUP_ID', '-4845548770'))

# ─────────── INICIALIZAÇÃO ───────────
client = TelegramClient('bot_session', API_ID, API_HASH)
fut    = UMFutures(key=BINANCE_API_KEY, secret=BINANCE_API_SECRET)

# Armazena SLs, preços de entrada e side original
stop_order_ids = {}
entry_prices_map = {}
original_sides = {}

# ─── Helpers ───
def remove_emojis(text: str) -> str:
    return emoji.replace_emoji(text, replace='')

# ─── Parser de sinal ───
def parse_message(text: str):
    text = remove_emojis(text)
    lines = text.splitlines()
    symbol = side = None
    leverage = 1
    entry = None
    tps = []
    stop = None
    entry_block = tp_block = stop_block = False
    for line in lines:
        ln = line.strip()
        if not ln or ln.lower().startswith('exchanges:'):
            continue
        m = re.search(r'#([A-Z0-9]+)/USDT', ln)
        if m:
            symbol = m.group(1) + 'USDT'
            continue
        if 'Signal Type' in ln:
            m = re.search(r'\b(Long|Short)\b', ln, re.IGNORECASE)
            if m:
                side = 'BUY' if m.group(1).lower()=='long' else 'SELL'
            continue
        if 'Leverage' in ln:
            m = re.search(r'(\d+)[xх]', ln)
            if m:
                leverage = int(m.group(1))
            continue
        if ln.lower().startswith('entry targets'):
            entry_block = True
            continue
        if entry_block:
            try:
                entry = float(ln)
            except:
                pass
            entry_block = False
            continue
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
        if 'STOP' in ln.upper():
            stop_block = True
            continue
        if stop_block:
            try:
                stop = float(ln)
            except:
                pass
            stop_block = False
            continue
    if None in (symbol, side, entry, stop) or not tps:
        return None
    return {'symbol': symbol, 'side': side, 'leverage': leverage, 'entry': entry, 'tps': tps, 'stop': stop}

# ─── Ajuste de precisão ───
def adjust_precision(symbol: str, value: float, value_type: str = 'price') -> float:
    info = fut.exchange_info()
    si = next(s for s in info['symbols'] if s['symbol']==symbol)
    filt_type = 'PRICE_FILTER' if value_type=='price' else 'LOT_SIZE'
    filt = next(f for f in si['filters'] if f['filterType']==filt_type)
    step = float(filt['tickSize'] if value_type=='price' else filt['stepSize'])
    prec = int(-math.floor(math.log10(step)))
    if value_type=='quantity':
        q = math.floor(value/step)*step
        return round(q, prec)
    return round(value, prec)

# ─── Saldo e minQty ───
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
        text = event.raw_text
        # 0) Detecta apenas "Take-profit target 3 ✅"
        m_tp3 = re.search(r'#([A-Z0-9]+)/USDT\s+Take-profit target 3\s+✅', text)
        if m_tp3:
            symbol = m_tp3.group(1) + 'USDT'
            print(f'🔔 Comando Take-profit target 3 recebido para {symbol}')
            # Cancela SL atual
            if symbol in stop_order_ids:
                try:
                    fut.cancel_order(symbol=symbol, orderId=stop_order_ids[symbol])
                    print(f'▶ Stop-loss cancelado para {symbol} (id {stop_order_ids[symbol]})')
                except ClientError as e:
                    print('❌ Erro ao cancelar SL:', e)
            # Cria novo SL break-even
            if symbol in entry_prices_map and symbol in original_sides:
                entry_p = entry_prices_map[symbol]
                sl_price = adjust_precision(symbol, entry_p, 'price')
                opposite = 'SELL' if original_sides[symbol]=='BUY' else 'BUY'
                try:
                    new_sl = fut.new_order(
                        symbol=symbol,
                        side=opposite,
                        type='STOP_MARKET',
                        stopPrice=str(sl_price),
                        closePosition=True
                    )
                    stop_order_ids[symbol] = new_sl['orderId']
                    print(f'▶ Novo stop-loss break-even @ {sl_price} (id {new_sl["orderId"]})')
                except ClientError as e:
                    print('❌ Erro ao agendar novo SL:', e)
            return

        # 1) Processa sinal de entrada normalmente
        parsed = parse_message(text)
        if not parsed:
            print('⚠️ Fora do padrão:', text)
            return
        print('✅ Sinal válido:', parsed)

        # Ajusta alavancagem
        fut.change_leverage(symbol=parsed['symbol'], leverage=parsed['leverage'])

        # Calcula qty
        balance = get_balance()
        margin = min(balance * 0.01, 30)
        entry_price = adjust_precision(parsed['symbol'], parsed['entry'], 'price')
        raw_qty = (margin * parsed['leverage']) / entry_price
        qty = max(adjust_precision(parsed['symbol'], raw_qty, 'quantity'), get_min_quantity(parsed['symbol']))
        print(f'▶ Qty calculada: {qty} (margem US$ {margin:.2f}, lev {parsed["leverage"]}x)')

        # Cria ordem de entrada com proximidade de 0.05%
        threshold = entry_price * 0.0005  # 0.05%
        mark = float(fut.mark_price(symbol=parsed['symbol'])['markPrice'])
        side = parsed['side']
        try:
            if side=='BUY':
                if mark >= entry_price - threshold:
                    entry = fut.new_order(symbol=parsed['symbol'], side='BUY', type='MARKET', quantity=qty)
                    print(f'▶ Entrada BUY MARKET (id {entry["orderId"]}) @ {mark}')
                else:
                    entry = fut.new_order(
                        symbol=parsed['symbol'], side='BUY', type='STOP',
                        quantity=qty, price=str(entry_price), stopPrice=str(entry_price), timeInForce='GTC'
                    )
                    print(f'▶ Entrada BUY STOP-LIMIT (id {entry["orderId"]}) @{entry_price}')
            else:
                if mark <= entry_price + threshold:
                    entry = fut.new_order(symbol=parsed['symbol'], side='SELL', type='MARKET', quantity=qty)
                    print(f'▶ Entrada SELL MARKET (id {entry["orderId"]}) @ {mark}')
                else:
                    entry = fut.new_order(
                        symbol=parsed['symbol'], side='SELL', type='STOP',
                        quantity=qty, price=str(entry_price), stopPrice=str(entry_price), timeInForce='GTC'
                    )
                    print(f'▶ Entrada SELL STOP-LIMIT (id {entry["orderId"]}) @{entry_price}')
            entry_id = entry['orderId']
        except ClientError as e:
            print('❌ Erro na entrada:', e)
            return

        # Agenda SL sempre STOP_MARKET e armazena
        opposite = 'SELL' if side=='BUY' else 'BUY'
        sl_price = adjust_precision(parsed['symbol'], parsed['stop'], 'price')
        try:
            sl = fut.new_order(symbol=parsed['symbol'], side=opposite, type='STOP_MARKET', stopPrice=str(sl_price), closePosition=True)
            print(f'▶ STOP-LOSS agendado @ {sl_price} (id {sl["orderId"]})')
            stop_order_ids[parsed['symbol']] = sl['orderId']
            entry_prices_map[parsed['symbol']] = entry_price
            original_sides[parsed['symbol']] = side
        except ClientError as e:
            print('❌ Erro ao agendar SL:', e)

        # Agenda apenas TPs 1 a 6
        remaining = qty
        for i, tpv in enumerate(parsed['tps'], start=1):
            if i>6:
                print(f'⚠️ Ignorando TP{i} (fechamento manual)')
                continue
            sell_qty = adjust_precision(parsed['symbol'], remaining*0.2, 'quantity')
            if sell_qty<=0:
                continue
            tp_price = adjust_precision(parsed['symbol'], tpv, 'price')
            try:
                fut.new_order(symbol=parsed['symbol'], side=opposite, type='TAKE_PROFIT_MARKET', stopPrice=str(tp_price), quantity=sell_qty, reduceOnly=True)
                print(f'▶ TP{i} agendado @ {tp_price} qty {sell_qty} (rest {remaining})')
                remaining -= sell_qty
            except ClientError as e:
                print(f'❌ Erro TP{i}:', e)

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
