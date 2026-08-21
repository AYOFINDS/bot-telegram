import os
import re
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# 1. Server Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Variabili
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG")
SOURCE_CHANNEL = -1003634367021
LINK_SCONTO = "https://t.me/+DiuD1AbxY8thYzg0"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# Funzione per aggiungere il tag affiliato a tutti i link USFans
def convert_links(text):
    if not text:
        return text
    
    def replace_url(match):
        url = match.group(0)
        if 'usfans' in url.lower():
            if 'affcode=' in url:
                return re.sub(r'(affcode=)[^&\s]+', f'affcode={AFFILIATE_TAG}', url)
            elif '?' in url:
                return f"{url}&affcode={AFFILIATE_TAG}"
            else:
                return f"{url}?affcode={AFFILIATE_TAG}"
        return url

    return re.sub(r'https?://[^\s]+', replace_url, text)

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    print(" Nuovo messaggio rilevato nel canale sorgente!")
    message = event.message
    caption_or_text = message.text or ""

    # Elabora il testo inserendo il tuo tag sugli eventuali link presenti
    new_text = convert_links(caption_or_text)

    # Bottoni base sotto al messaggio
    buttons = [
        [Button.url("🎁 ISCRIVITI + 40% DI SCONTO", LINK_SCONTO)]
    ]

    try:
        if message.media:
            await client.send_file(TARGET_CHAT, message.media, caption=new_text, buttons=buttons)
        else:
            await client.send_message(TARGET_CHAT, new_text, buttons=buttons)
        print(" Messaggio inoltrato con successo!")
    except Exception as e:
        print(f" Errore durante l'invio del messaggio: {e}")

# 4. Avvio
if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Bot avviato e in ascolto senza filtri restrittivi!")
    
    client.start()
    client.run_until_disconnected()
