import os
import re
import asyncio
import io
from flask import Flask
from threading import Thread
from waitress import serve
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# 1. Server Web Keep-Alive (Waitress Production WSGI)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)

# 2. Configurazione Variabili
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "U2CC3E")
LINK_SCONTO = "https://usfans.com/register?ref=U2CC3E"

user_client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

album_buffers = {}

def get_product_emoji(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ['shoe', 'sneaker', 'campus', 'jordan', 'dunk', 'yeezy', 'nike', 'adidas', 'air max', 'travis', 'running', 'slide', 'foam']):
        return "👟"
    elif any(k in t for k in ['cap', 'hat', 'berretto', 'cappellino']):
        return "🧢"
    elif any(k in t for k in ['watch', 'orologio', 'rolex']):
        return "⌚"
    elif any(k in t for k in ['hoodie', 'jacket', 'zipper', 'felpa', 'giacca', 'coat', 'fleece', 'puffer']):
        return "🧥"
    elif any(k in t for k in ['tee', 't-shirt', 'shirt', 'maglietta']):
        return "👕"
    elif any(k in t for k in ['pants', 'shorts', 'trousers', 'pantaloni', 'jeans']):
        return "👖"
    elif any(k in t for k in ['bag', 'backpack', 'borsa', 'zaino', 'wallet', 'louis']):
        return "👜"
    return "🛍️"

@user_client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    message = event.message
    
    if message.grouped_id:
        gid = message.grouped_id
        
        if gid not in album_buffers:
            album_buffers[gid] = {
                'messages': [],
                'task': None
            }
        
        album_buffers[gid]['messages'].append(message)
        
        if album_buffers[gid]['task'] is not None:
            album_buffers[gid]['task'].cancel()
            
        album_buffers[gid]['task'] = asyncio.create_task(wait_and_process_album(gid))
    else:
        await forward_post([message])

async def wait_and_process_album(gid):
    try:
        await asyncio.sleep(4.0)
        buffer = album_buffers.pop(gid, None)
        if buffer and buffer['messages']:
            await forward_post(buffer['messages'])
    except asyncio.CancelledError:
        pass

async def download_single_media(m, idx):
    if not m.media:
        return None
    try:
        file_bytes = await asyncio.wait_for(user_client.download_media(m.media, file=bytes), timeout=15.0)
        if file_bytes:
            bio = io.BytesIO(file_bytes)
            bio.name = f"photo_{idx}.jpg"
            return bio
    except Exception as e:
        print(f"⚠️ Errore download foto {idx}: {e}")
    return None

async def forward_post(messages):
    print(f"🚨 ELABORAZIONE POST ({len(messages)} elementi)...")
    
    full_text = ""
    entities = []

    for m in messages:
        txt = m.text or m.message or m.raw_text or ""
        if len(txt.strip()) > 0:
            full_text = txt
            entities = m.entities or []
            break

    if not full_text:
        print("❌ Nessun testo trovato nell'album. Interruzione.")
        return

    article_match = re.search(r'Article:\s*(.*)', full_text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*)', full_text, re.IGNORECASE)

    article_val = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    price_val = price_match.group(1).strip() if price_match else "N/A"

    emoji = get_product_emoji(article_val)

    usfans_link = None
    
    for entity in entities:
        if hasattr(entity, 'url') and entity.url:
            offset = entity.offset
            length = entity.length
            entity_text = full_text[offset:offset+length].lower()
            
            if 'usfans' in entity_text or 'usfans.com' in entity.url.lower():
                usfans_link = entity.url
                break

    if not usfans_link:
        for entity in entities:
            if hasattr(entity, 'url') and entity.url and 'usfans' in entity.url.lower():
                usfans_link = entity.url
                break

    if not usfans_link:
        usfans_link = "https://www.usfans.com"

    usfans_link = re.sub(r'[\?&](ref|affcode)=[^&\s]+', '', usfans_link)
    
    if '?' in usfans_link:
        usfans_link += f'&affcode={AFFILIATE_TAG}'
    else:
        usfans_link += f'?affcode={AFFILIATE_TAG}'

    new_text = (
        f"{emoji} **Article: {article_val}**\n"
        f"💰 **Price: {price_val}**\n\n"
        f"🎁 **BONUS BENVENUTO:** Usa i tuoi coupon per risparmiare fino al 40% sul tuo ordine!\n"
        f"🔥 **Batch:** Qualità e dettagli top"
    )

    buttons = [
        [Button.url("🛒 ACQUISTA PRODOTTO", usfans_link)],
        [Button.url("🎁 ISCRIVITI + 40% DI SCONTO", LINK_SCONTO)]
    ]

    try:
        messages.sort(key=lambda m: m.id)
        
        tasks = [download_single_media(m, idx) for idx, m in enumerate(messages)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await bot_client.send_file(TARGET_CHAT, image_files)
            await bot_client.send_message(TARGET_CHAT, new_text, buttons=buttons)
        else:
            await bot_client.send_message(TARGET_CHAT, new_text, buttons=buttons)
            
        print("✅ ALBUM E LINK AFFILIATI PUBBLICATI CON SUCCESSO!")
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
