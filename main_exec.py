#!/usr/bin/env python3

import os
import re
import emoji
import math
import asyncio
from telethon import TelegramClient, events
from binance.um_futures import UMFutures
from binance.error import ClientError

# ─────────── AUTOCARGA DE .env ───────────
# Carrega variáveis do .env automaticamente
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# ─────────── CONFIGURAÇÃO ───────────
API_ID             = int(os.getenv('API_ID', '27677366'))
API_HASH           = os.getenv('API_HASH', '3c15d5e237f3fef52f68fc6c27130735')
PHONE              = os.getenv('PHONE', '+5567991155053')
BINANCE_API_KEY    = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
SIGNALS_GROUP_ID   = int(os.getenv('SIGNALS_GROUP_ID', '-4845548770'))

# Valida chaves obrigatórias
if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    raise RuntimeError("Faltando BINANCE_API_KEY ou BINANCE_API_SECRET no .env")

# ─────────── INICIALIZAÇÃO ───────────
client = TelegramClient('bot_session', API_ID, API_HASH)
fut    = UMFutures(key=BINANCE_API_KEY, secret=BINANCE_API_SECRET)

# Armazena SLs, preços e side original
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

        m = re.search(r'#([A-Z0-9]+)/USDT', ln)
        if m:
            symbol = m.group(1) + 'USDT'
            continue

        if 'Signal Type' in ln:
            m = re.search(r'\b(Long|Short)\b', ln, re.IGNORECASE)
            side = 'BUY' if m and m.group(1).lower()=='long' else ('SELL' if m else side)
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
            try: entry = float(ln)
            except: pass
            entry_block = False
            continue

        if ln.lower().startswith('take-profit targets'):
            tp_block = True
            continue
        if tp_block:
            m = re.search(r'\d+\)\s*([\d.]+)', ln)
            if m:
                val = float(m.group(1))
                if val>0:
                    tps.append(val)
                continue
            tp_block = False

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
        'stop': stop,
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

# ─── Filtros de conta ───
def get_balance() -> float:
    return float(next(x for x in fut.balance() if x['asset']=='USDT')['balance'])

def get_min_quantity(symbol: str) -> float:
    si = next(s for s in fut.exchange_info()['symbols'] if s['symbol']==symbol)
    return float(next(f for f in si['filters'] if f['filterType']=='LOT_SIZE')['minQty'])

def get_tick(symbol: str) -> float:
    si = next(s for s in fut.exchange_info()['symbols'] if s['symbol']==symbol)
    return float(next(f for f in si['filters'] if f['filterType']=='PRICE_FILTER')['tickSize'])

# ─── Main ───────
async def main():
    await client.start(PHONE)
    print('🤖 Bot pronto. Aguardando sinais…')

    @client.on(events.NewMessage(chats=SIGNALS_GROUP_ID))
    async def handler(event):
        txt = event.raw_text

        # 0) Ajuste Break-Even (TP3)
        if re.search(r'#([A-Z0-9]+)/USDT\s+Take-profit target 3\s+✅', txt):
            sym = re.search(r'#([A-Z0-9]+)/USDT', txt).group(1)+'USDT'
            print(f'🔔 Ajustando BE para {sym}')
            if sym in stop_order_ids:
                try:
                    fut.cancel_order(symbol=sym, orderId=stop_order_ids[sym])
                    print(f'▶ SL cancelado para {sym}')
                except ClientError as e:
                    print('❌', e)
            if sym in entry_prices_map and sym in original_sides:
                ep  = entry_prices_map[sym]
                sp  = adjust_precision(sym, ep, 'price')
                opp = 'SELL' if original_sides[sym]=='BUY' else 'BUY'
                try:
                    newsl = fut.new_order(
                        symbol=sym,
                        side=opp,
                        type='STOP_MARKET',
                        stopPrice=str(sp),
                        closePosition=True,
                        reduceOnly=True
                    )
                    stop_order_ids[sym] = newsl['orderId']
                    print(f'▶ Novo SL BE @ {sp}')
                except ClientError as e:
                    print('❌', e)
            return

        # 1) Sinal de entrada
        parsed = parse_message(txt)
        if not parsed:
            print('⚠️ Fora do padrão:', txt)
            return
        print('✅ Sinal válido:', parsed)

        # Ajusta alavancagem
        fut.change_leverage(symbol=parsed['symbol'], leverage=parsed['leverage'])

        # Calcular quantidade
        bal    = get_balance()
        margin = min(bal * 0.01, 30)
        ep     = adjust_precision(parsed['symbol'], parsed['entry'], 'price')
        rawq   = (margin * parsed['leverage']) / ep
        qty    = max(
            adjust_precision(parsed['symbol'], rawq, 'quantity'),
            get_min_quantity(parsed['symbol'])
        )
        print(f'▶ Qty: {qty} (margem US$ {margin:.2f}, lev {parsed["leverage"]}x)')

        # Escolha de tipo de ordem de entrada
        th    = ep * 0.0005
        markp = float(fut.mark_price(symbol=parsed['symbol'])['markPrice'])
        side  = parsed['side']
        opp   = 'SELL' if side=='BUY' else 'BUY'
        try:
            if side=='BUY':
                if markp >= ep - th:
                    ent = fut.new_order(symbol=parsed['symbol'], side='BUY', type='MARKET', quantity=qty)
                    print(f'▶ BUY MARKET @ {markp}')
                else:
                    ent = fut.new_order(
                        symbol=parsed['symbol'],
                        side='BUY',
                        type='STOP',
                        quantity=qty,
                        price=str(ep),
                        stopPrice=str(ep),
                        timeInForce='GTC'
                    )
                    print(f'▶ BUY STOP-LIMIT @ {ep}')
            else:
                if markp <= ep + th:
                    ent = fut.new_order(symbol=parsed['symbol'], side='SELL', type='MARKET', quantity=qty)
                    print(f'▶ SELL MARKET @ {markp}')
                else:
                    ent = fut.new_order(
                        symbol=parsed['symbol'],
                        side='SELL',
                        type='STOP',
                        quantity=qty,
                        price=str(ep),
                        stopPrice=str(ep),
                        timeInForce='GTC'
                    )
                    print(f'▶ SELL STOP-LIMIT @ {ep}')
            entry_prices_map[parsed['symbol']] = ep
            original_sides[parsed['symbol']]   = side
        except ClientError as e:
            print('❌ Erro na entrada:', e)
            return

        # SL com retry para -2021
        sp = adjust_precision(parsed['symbol'], parsed['stop'], 'price')
        try:
            sl = fut.new_order(
                symbol=parsed['symbol'],
                side=opp,
                type='STOP_MARKET',
                stopPrice=str(sp),
                closePosition=True,
                reduceOnly=True
            )
        except ClientError as e:
            if e.code == -2021:
                tick = get_tick(parsed['symbol'])
                sp   = sp + tick if side=='BUY' else sp - tick
                sp   = adjust_precision(parsed['symbol'], sp, 'price')
                try:
                    sl = fut.new_order(
                        symbol=parsed['symbol'],
                        side=opp,
                        type='STOP_MARKET',
                        stopPrice=str(sp),
                        closePosition=True,
                        reduceOnly=True
                    )
                    print(f'▶ SL ajustado @ {sp}')
                except ClientError as e2:
                    print('❌ SL falhou após ajuste:', e2)
                    sl = None
            else:
                print('❌ Erro ao agendar SL:', e)
                sl = None
        if sl:
            stop_order_ids[parsed['symbol']] = sl['orderId']
            print(f'▶ SL agendado @ {sp}')

        # Agendar TPs 1–6
        rem = qty
        for i, tv in enumerate(parsed['tps'][:6], start=1):
            qli = adjust_precision(parsed['symbol'], rem * 0.2, 'quantity')
            if qli <= 0:
                break
            tp_p = adjust_precision(parsed['symbol'], tv, 'price')
            try:
                fut.new_order(
                    symbol=parsed['symbol'],
                    side=opp,
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=str(tp_p),
                    quantity=qli,
                    reduceOnly=True
                )
                print(f'▶ TP{i} @ {tp_p} qty {qli}')
                rem -= qli
            except ClientError as e:
                print(f'❌ Erro TP{i}:', e)

    await client.run_until_disconnected()

if __name__=='__main__':
    asyncio.run(main())
