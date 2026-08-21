import os
import re
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG")
SOURCE_CHANNEL = "KakobuySpreadsheet6"
LINK_SCONTO = "https://t.me/+DiuD1AbxY8thYzg0"

client = TelegramClient('bot_session', API_ID, API_HASH)

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    message = event.message
    text = message.text or ""
    
    article_match = re.search(r'Article:\s*(.*)', text)
    price_match = re.search(r'Price:\s*(.*)', text)
    
    title = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    price = price_match.group(1).strip() if price_match else "N/A"

    usfans_link = None
    if message.entities:
        for entity in message.entities:
            if hasattr(entity, 'url') and entity.url:
                if 'usfans' in entity.url.lower():
                    usfans_link = entity.url
                    break
    
    if not usfans_link:
        url_search = re.search(r'https?://[^\s]*usfans[^\s]*', text)
        if url_search:
            usfans_link = url_search.group(0)

    if not usfans_link:
        usfans_link = "https://usfans.com"

    if 'affcode=' in usfans_link:
        usfans_link = re.sub(r'(affcode=)[^&\s]+', f'affcode={AFFILIATE_TAG}', usfans_link)
    elif '?' in usfans_link:
        usfans_link += f'&affcode={AFFILIATE_TAG}'
    else:
        usfans_link += f'?affcode={AFFILIATE_TAG}'

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

    if message.media:
        await client.send_file(TARGET_CHAT, message.media, caption=new_text, buttons=buttons)
    else:
        await client.send_message(TARGET_CHAT, new_text, buttons=buttons)

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Bot avviato con Server Web...")
    client.start(bot_token=BOT_TOKEN)
    client.run_until_disconnected()
