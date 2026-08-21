import os
import re
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# 1. Server Web per Keep-Alive su Railway
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Configurazione Variabili d'Ambiente
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG")
LINK_SCONTO = "https://t.me/+DiuD1AbxY8thYzg0"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# ID o Username del canale da cui copiare
SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    # Ignora le immagini secondarie degli album di foto
    if event.message.grouped_id and not event.message.text:
        return

    print("🚨 NUOVO POST INTERCETTATO DAL CANALE SORGENTE!")
    message = event.message
    text = message.text or ""

    # Estrazione Titolo e Prezzo
    article_match = re.search(r'Article:\s*(.*)', text)
    price_match = re.search(r'Price:\s*(.*)', text)

    title = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    price = price_match.group(1).strip() if price_match else "N/A"

    # Estrazione Link USFans
    usfans_link = None
    if message.entities:
        for entity in message.entities:
            if hasattr(entity, 'url') and entity.url and 'usfans' in entity.url.lower():
                usfans_link = entity.url
                break

    if not usfans_link:
        url_search = re.search(r'https?://[^\s]*usfans[^\s]*', text)
        if url_search:
            usfans_link = url_search.group(0)

    if not usfans_link:
        usfans_link = "https://usfans.com"

    # Applicazione del Tag Affiliato
    if 'affcode=' in usfans_link:
        usfans_link = re.sub(r'(affcode=)[^&\s]+', f'affcode={AFFILIATE_TAG}', usfans_link)
    elif '?' in usfans_link:
        usfans_link += f'&affcode={AFFILIATE_TAG}'
    else:
        usfans_link += f'?affcode={AFFILIATE_TAG}'

    # Testo formattato finale
    new_text = (
        f"🧢 **{title}**\n"
        f"💰 **Prezzo: {price}€**\n\n"
        f"🎁 **BONUS BENVENUTO:** Usa i tuoi coupon per risparmiare fino al 40% sul tuo ordine!\n"
        f"🔥 **Batch:** Qualità e dettagli top"
    )

    buttons = [
        [Button.url("🛒 ACQUISTA PRODOTTO", usfans_link)],
        [Button.url("🎁 ISCRIVITI + 40% DI SCONTO", LINK_SCONTO)]
    ]

    try:
        if message.media:
            await client.send_file(TARGET_CHAT, message.media, caption=new_text, buttons=buttons)
        else:
            await client.send_message(TARGET_CHAT, new_text, buttons=buttons)
        print("✅ POST INVIATO CON SUCCESSO SUL TUO CANALE!")
    except Exception as e:
        print(f"❌ Errore durante l'invio al canale: {e}")

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

    print("🚀 Bot avviato e pronto ad inoltrare i post in automatico!")
    client.start()
    client.run_until_disconnected()
