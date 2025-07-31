
from telethon.sync import TelegramClient, events
from dotenv import load_dotenv
import os

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")

with TelegramClient('bot_id_checker', api_id, api_hash) as client:
    @client.on(events.NewMessage)
    async def handler(event):
        chat = await event.get_chat()
        print(f"[DEBUG] Mensagem recebida de: {chat.title} / ID: {event.chat_id}")
    
    print("✅ Aguarde... Envie uma mensagem no grupo e veja o ID aqui.")
    client.run_until_disconnected()
