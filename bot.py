import os
import re
import asyncio
import io
from flask import Flask
from threading import Thread
from waitress import serve
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

# 1. Server Web Keep-Alive (Waitress)
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

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "U2CC3E")
LINK_SCONTO = "https://usfans.com/register?ref=U2CC3E"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

# Buffer per unificare foto e messaggi di testo separati
chat_buffers = {}

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

@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    message = event.message
    chat_id = event.chat_id

    if chat_id not in chat_buffers:
        chat_buffers[chat_id] = {
            'messages': [],
            'task': None
        }

    chat_buffers[chat_id]['messages'].append(message)

    # Se arrivano altri elementi (foto o testo) nello stesso canale, si resetta il timer
    if chat_buffers[chat_id]['task'] is not None:
        chat_buffers[chat_id]['task'].cancel()

    chat_buffers[chat_id]['task'] = asyncio.create_task(wait_and_process_chat(chat_id))

async def wait_and_process_chat(chat_id):
    try:
        # Aspetta 5 secondi per essere certi che Telegram abbia consegnato sia le foto che il testo
        await asyncio.sleep(5.0)
        buffer = chat_buffers.pop(chat_id, None)
        if buffer and buffer['messages']:
            await forward_post(buffer['messages'])
    except asyncio.CancelledError:
        pass

async def download_single_media(m, idx):
    if not m.media:
        return None
    try:
        file_bytes = await asyncio.wait_for(client.download_media(m.media, file=bytes), timeout=15.0)
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
    media_messages = []

    # Separa le foto dai testi
    for m in messages:
        if m.media:
            media_messages.append(m)
        
        txt = getattr(m, 'text', '') or getattr(m, 'message', '') or getattr(m, 'caption', '') or getattr(m, 'raw_text', '') or ""
        if len(txt.strip()) > 0:
            full_text += f"\n{txt}"
            if m.entities:
                entities.extend(m.entities)
            elif getattr(m, 'caption_entities', None):
                entities.extend(m.caption_entities)

    article_match = re.search(r'Article:\s*(.*)', full_text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*)', full_text, re.IGNORECASE)

    article_val = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    price_val = price_match.group(1).strip() if price_match else "N/A"

    usfans_link = None

    # Search per link Usfans o in alternativa qualsiasi link nella lista
    for entity in entities:
        if hasattr(entity, 'url') and entity.url:
            url = entity.url
            if 'usfans' in url.lower():
                usfans_link = url
                break

    if not usfans_link:
        for entity in entities:
            if hasattr(entity, 'url') and entity.url and entity.url.startswith("http"):
                usfans_link = entity.url
                break

    if not usfans_link:
        usfans_link = "https://www.usfans.com"

    emoji = get_product_emoji(article_val)

    # Clean & Affiliato
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
        media_messages.sort(key=lambda m: m.id)
        
        tasks = [download_single_media(m, idx) for idx, m in enumerate(media_messages)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await client.send_file(TARGET_CHAT, image_files)
            await client.send_message(TARGET_CHAT, new_text, buttons=buttons)
        else:
            await client.send_message(TARGET_CHAT, new_text, buttons=buttons)
            
        print("✅ POST E LINK AFFILIATI PUBBLICATI CON SUCCESSO!")
    except Exception as e:
        print(f"❌ Errore durante l'invio: {e}")

async def main():
    while True:
        try:
            await client.start()
            print("🚀 Client connesso e pronto 24/7!")
            await client.run_until_disconnected()
            break
        except FloodWaitError as e:
            print(f"⏳ Telegram richiede un'attesa di {e.seconds} secondi. Attendo...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"❌ Errore imprevisto durante l'avvio: {e}")
            await asyncio.sleep(10)

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

    asyncio.run(main())
