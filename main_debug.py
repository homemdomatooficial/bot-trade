import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient, events

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
channel_id = int(os.getenv("TELEGRAM_CHANNEL"))

with TelegramClient("bot_debug", api_id, api_hash) as client:
    print("🔍 Bot de debug iniciado. Escutando mensagens...")

    @client.on(events.NewMessage(chats=channel_id))
    async def handler(event):
        mensagem = event.raw_text
        print(f"[DEBUG] Mensagem recebida:\n{mensagem}\n{'-'*40}")

    client.run_until_disconnected()
