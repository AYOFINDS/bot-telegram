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

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "U2CC3E")
LINK_SCONTO = "https://usfans.com/register?ref=U2CC3E"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

album_cache = {}
text_cache = {}

@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    msg = event.message
    chat_id = event.chat_id

    # Se fa parte di un album (gruppo di foto)
    if msg.grouped_id:
        gid = msg.grouped_id
        if gid not in album_cache:
            album_cache[gid] = {
                'chat_id': chat_id,
                'messages': [],
                'timer': None
            }
        
        album_cache[gid]['messages'].append(msg)
        
        if album_cache[gid]['timer']:
            album_cache[gid]['timer'].cancel()
            
        # Finestra di attesa estesa a 30 secondi per raccogliere tutto
        album_cache[gid]['timer'] = asyncio.create_task(process_album(gid))

    # Se è un messaggio di testo con i dati del prodotto
    elif msg.text and ("Article:" in msg.text or "Price:" in msg.text or "spreadsheet" in msg.text.lower()):
        text_cache[chat_id] = msg

    # Foto singola senza album
    elif msg.media:
        await process_and_send([msg], None)

async def process_album(gid):
    try:
        # Aspettiamo ben 30 secondi per essere sicuri al 100% di avere tutte le foto e il testo
        await asyncio.sleep(30.0)
        data = album_cache.pop(gid, None)
        if data:
            chat_id = data['chat_id']
            messages = data['messages']
            text_msg = text_cache.pop(chat_id, None)
            
            await process_and_send(messages, text_msg)
    except asyncio.CancelledError:
        pass

async def download_media_safe(m, idx):
    if not m.media:
        return None
    try:
        file_bytes = await asyncio.wait_for(client.download_media(m.media, file=bytes), timeout=30.0)
        if file_bytes:
            bio = io.BytesIO(file_bytes)
            bio.name = f"photo_{idx}.jpg"
            return bio
    except Exception as e:
        print(f"⚠️ Errore download foto {idx}: {e}")
    return None

async def process_and_send(media_list, text_msg):
    print(f"🚨 ELABORAZIONE POST: {len(media_list)} foto trovate.")
    
    source_text = ""
    entities = []

    if text_msg:
        source_text = getattr(text_msg, 'text', '') or getattr(text_msg, 'message', '') or ""
        entities = text_msg.entities or []

    if not source_text:
        for m in media_list:
            cap = getattr(m, 'caption', '') or ""
            if cap and ("Article:" in cap or "Price:" in cap):
                source_text = cap
                entities = m.caption_entities or []
                break

    if not source_text:
        source_text = "🔍 Article: Prodotto Esclusivo\n💰 Price: N/A"

    article_line = "🔍 Article: Prodotto Esclusivo"
    price_line = "💰 Price: N/A"

    for line in source_text.split('\n'):
        if 'article:' in line.lower():
            article_line = line.strip()
        elif 'price:' in line.lower():
            price_line = line.strip()

    product_link = None
    for entity in entities:
        if hasattr(entity, 'url') and entity.url:
            if 'usfans.com' in entity.url.lower():
                product_link = entity.url
                break

    if not product_link:
        urls = re.findall(r'https?://[^\s]+', source_text)
        for u in urls:
            if 'usfans' in u.lower():
                product_link = u
                break
        if not product_link and urls:
            product_link = urls[0]

    if not product_link:
        product_link = "https://www.usfans.com"

    product_link = re.sub(r'[\?&](ref|affcode)=[^&\s]+', '', product_link)
    if '?' in product_link:
        product_link += f'&affcode={AFFILIATE_TAG}'
    else:
        product_link += f'?affcode={AFFILIATE_TAG}'

    final_text = (
        f"{article_line}\n"
        f"{price_line}\n\n"
        f"🎁 **BONUS BENVENUTO:** Usa i tuoi coupon per risparmiare fino al 40% sul tuo ordine!\n"
        f"🔥 **Batch:** Qualità e dettagli top"
    )

    buttons = [
        [Button.url("🛒 ACQUISTA PRODOTTO", product_link)],
        [Button.url("🎁 ISCRIVITI + 40% DI SCONTO", LINK_SCONTO)]
    ]

    try:
        media_list.sort(key=lambda x: x.id)
        
        tasks = [download_media_safe(m, idx) for idx, m in enumerate(media_list)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await client.send_file(TARGET_CHAT, image_files)
            await client.send_message(TARGET_CHAT, final_text, buttons=buttons)
        else:
            await client.send_message(TARGET_CHAT, final_text, buttons=buttons)
            
        print("✅ POST INVIATO CORRETTAMENTE CON ALBUM COMPLETO, TESTO E TASTI!")
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
            print(f"❌ Errore imprevisto: {e}")
            await asyncio.sleep(10)

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

    asyncio.run(main())
