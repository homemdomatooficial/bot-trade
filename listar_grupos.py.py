from telethon.sync import TelegramClient

API_ID   = 27677366
API_HASH = '3c15d5e237f3fef52f68fc6c27130735'
PHONE    = '+5567991155053'

with TelegramClient('tmp_session', API_ID, API_HASH) as client:
    client.start(PHONE)
    for dialog in client.iter_dialogs():
        print(f"{dialog.name!r} -> {dialog.id}")
