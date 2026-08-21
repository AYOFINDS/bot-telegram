import os
import re
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# ASCOLTA QUALSIASI MESSAGGIO DI QUALSIASI CHAT PER TEST
@client.on(events.NewMessage)
async def handler(event):
    chat = await event.get_chat()
    chat_name = getattr(chat, 'title', '') or getattr(chat, 'username', '') or str(event.chat_id)
    print(f"📩 MESSAGGIO RICEVUTO DA: {chat_name} (ID: {event.chat_id})")

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    print("🧪 BOT IN MODALITÀ TEST - Ascolta tutti i messaggi...")
    client.start()
    client.run_until_disconnected()
