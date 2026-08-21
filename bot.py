import os
import re
import asyncio
import io
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# 1. Server Web Keep-Alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Configurazione Variabili
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG")
LINK_SCONTO = "https://t.me/+DiuD1AbxY8thYzg0"

user_client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

media_groups = {}

def get_product_emoji(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ['shoe', 'sneaker', 'campus', 'jordan', 'dunk', 'yeezy', 'nike', 'adidas', 'travis', 'running', 'slide', 'foam']):
        return "👟"
    elif any(k in t for k in ['cap', 'hat', 'berretto', 'cappellino']):
        return "🧢"
    elif any(k in t for k in ['hoodie', 'jacket', 'zipper', 'felpa', 'giacca', 'coat', 'fleece', 'puffer']):
        return "🧥"
    elif any(k in t for k in ['tee', 't-shirt', 'shirt', 'maglietta']):
        return "👕"
    elif any(k in t for k in ['pants', 'shorts', 'trousers', 'pantaloni', 'jeans']):
        return "👖"
    elif any(k in t for k in ['bag', 'backpack', 'borsa', 'zaino', 'wallet']):
        return "👜"
    return "🛍️"

@user_client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    message = event.message
    
    if message.grouped_id:
        gid = message.grouped_id
        if gid not in media_groups:
            media_groups[gid] = []
            asyncio.create_task(process_album(gid))
        media_groups[gid].append(message)
    else:
        await forward_post([message])

async def process_album(gid):
    await asyncio.sleep(2.5)
    messages = media_groups.pop(gid, [])
    if messages:
        await forward_post(messages)

async def forward_post(messages):
    print(f"🚨 ELABORAZIONE POST ({len(messages)} elementi)...")
    
    # Ricerca del testo in tutti i messaggi dell'album
    full_text = ""
    entities = []
    for m in messages:
        if m.text:
            full_text = m.text
            entities = m.entities or []
            break

    # Estrazione Titolo e Prezzo (gestisce sia 'Article:' sia 'Product:')
    article_match = re.search(r'(?:Article|Product):\s*(.*)', full_text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*)', full_text, re.IGNORECASE)

    title = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    price = price_match.group(1).strip() if price_match else "N/A"

    emoji = get_product_emoji(title)

    # Estrazione Link USFans
    usfans_link = None
    if entities:
        for entity in entities:
            if hasattr(entity, 'url') and entity.url and 'usfans' in entity.url.lower():
                usfans_link = entity.url
                break

    if not usfans_link:
        url_search = re.search(r'https?://[^\s]*usfans[^\s]*', full_text)
        if url_search:
            usfans_link = url_search.group(0)

    if not usfans_link:
        usfans_link = "https://usfans.com"

    # Applicazione Tag Affiliato
    if 'affcode=' in usfans_link:
        usfans_link = re.sub(r'(affcode=)[^&\s]+', f'affcode={AFFILIATE_TAG}', usfans_link)
    elif '?' in usfans_link:
        usfans_link += f'&affcode={AFFILIATE_TAG}'
    else:
        usfans_link += f'?affcode={AFFILIATE_TAG}'

    new_text = (
        f"{emoji} **{title}**\n"
        f"💰 **Prezzo: {price}€**\n\n"
        f"🎁 **BONUS BENVENUTO:** Usa i tuoi coupon per risparmiare fino al 40% sul tuo ordine!\n"
        f"🔥 **Batch:** Qualità e dettagli top"
    )

    buttons = [
        [Button.url("🛒 ACQUISTA PRODOTTO", usfans_link)],
        [Button.url("🎁 ISCRIVITI + 40% DI SCONTO", LINK_SCONTO)]
    ]

    try:
        # Download e conversione in memoria come immagini .jpg
        image_files = []
        for idx, m in enumerate(messages):
            if m.media:
                file_bytes = await user_client.download_media(m.media, file=bytes)
                if file_bytes:
                    bio = io.BytesIO(file_bytes)
                    bio.name = f"photo_{idx}.jpg"
                    image_files.append(bio)

        if image_files:
            # 1. Invia l'album con le foto vere
            await bot_client.send_file(
                TARGET_CHAT, 
                image_files
            )
            # 2. Invia la scheda testo con i pulsanti subito sotto
            await bot_client.send_message(
                TARGET_CHAT,
                new_text,
                buttons=buttons
            )
        else:
            await bot_client.send_message(TARGET_CHAT, new_text, buttons=buttons)
            
        print("✅ ALBUM E SCHEDA CON BOTTONI PUBBLICATI CON SUCCESSO!")
    except Exception as e:
        print(f"❌ Errore durante l'invio: {e}")

async def main():
    await bot_client.start(bot_token=BOT_TOKEN)
    await user_client.start()
    print("🚀 Bot e User Session connessi e pronti!")
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

    asyncio.run(main())
