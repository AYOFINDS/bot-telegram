import os
import re
import asyncio
import io
from flask import Flask
from threading import Thread
from waitress import serve
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)

raw_api_id = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")

if not raw_api_id or not API_HASH or not STRING_SESSION:
    print("❌ ERRORE CRITICO: Mancano le variabili di Railway!")
    exit(1)

API_ID = int(raw_api_id)

raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "U2CC3E")
LINK_SCONTO = f"https://www.usfans.com/register?ref={AFFILIATE_TAG}"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

posts_buffer = {}

def fix_affiliate_link(url, tag=AFFILIATE_TAG):
    if not url:
        return url
    # Se è un link di un agent/store o usfans, puliamo e iniettiamo il tag
    new_url, count = re.subn(r'([?&])(ref|affcode)=[^&\s]+', rf'\1\2={tag}', url)
    if count > 0:
        return new_url
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}affcode={tag}"

@client.on(events.NewMessage)
async def handler(event):
    msg = event.message
    chat = await event.get_chat()
    chat_title = getattr(chat, 'title', getattr(chat, 'username', 'Chat privata'))
    
    target_sources = ["KakobuySpreadsheet6", -1003634367021, 3634367021]
    is_valid = False
    for src in target_sources:
        if str(src) == str(event.chat_id) or (isinstance(src, str) and src.lower() in str(chat_title).lower()):
            is_valid = True
            break

    if not is_valid:
        return

    # Usiamo il grouped_id se è un album, altrimenti l'id del messaggio (ma guardiamo anche i messaggi vicini)
    post_key = msg.grouped_id if msg.grouped_id else msg.id

    if post_key not in posts_buffer:
        posts_buffer[post_key] = {
            'media_list': [],
            'raw_text': "",
            'entities': [],
            'timer': None
        }

    if msg.media:
        posts_buffer[post_key]['media_list'].append(msg)
        cap = getattr(msg, 'caption', '') or ''
        if cap:
            posts_buffer[post_key]['raw_text'] = cap
            posts_buffer[post_key]['entities'] = msg.caption_entities or []

    if msg.text:
        posts_buffer[post_key]['raw_text'] = msg.text
        posts_buffer[post_key]['entities'] = msg.entities or []
        
        # Cerca di accoppiare il testo ai messaggi vicini se arrivano separati
        for offset in [-1, 0, 1]:
            neighbor_key = (msg.id + offset) if not msg.grouped_id else post_key
            if neighbor_key in posts_buffer and not posts_buffer[neighbor_key]['raw_text']:
                posts_buffer[neighbor_key]['raw_text'] = msg.text
                posts_buffer[neighbor_key]['entities'] = msg.entities or []

    if posts_buffer[post_key]['timer']:
        posts_buffer[post_key]['timer'].cancel()

    posts_buffer[post_key]['timer'] = asyncio.create_task(process_post(post_key))

async def process_post(post_key):
    try:
        await asyncio.sleep(4.0) # Aspettiamo 4 secondi per raccogliere foto e testo insieme
        
        data = posts_buffer.pop(post_key, None)
        if not data:
            return

        media_list = data['media_list']
        source_text = data['raw_text']
        entities = data['entities']

        print(f"🚨 ELABORAZIONE POST [Key: {post_key}]: {len(media_list)} foto, Testo: {bool(source_text)}")

        article_line = "Article: Prodotto Esclusivo"
        price_line = "Price: N/A"

        for line in source_text.split('\n'):
            clean_line = line.strip()
            if 'article:' in clean_line.lower():
                article_line = clean_line
            elif 'price:' in clean_line.lower():
                price_line = clean_line

        # Estrazione intelligente del link del prodotto dal testo o dalle entità
        product_link = None
        for entity in entities:
            if hasattr(entity, 'url') and entity.url:
                url_lower = entity.url.lower()
                if 'register' not in url_lower: # Evitiamo il link di registrazione
                    product_link = entity.url
                    break

        if not product_link:
            urls = re.findall(r'https?://[^\s]+', source_text)
            for u in urls:
                if 'register' not in u.lower():
                    product_link = u
                    break

        if not product_link:
            product_link = "https://www.usfans.com"

        product_link = fix_affiliate_link(product_link)

        final_text = (
            f"🎖️ **Official Spreadsheet** 🎖️\n"
            f"✈️ {article_line}\n"
            f"💰 {price_line}\n"
            f"🚚 **Agents:**\n"
            f"🔗 [UsFans]({product_link})\n\n"
            f"✍️ [Register UsFans Here ($820 Coupon)]({LINK_SCONTO}) ✍️\n"
            f"🚨 **Warm Risk Reminder Popup** 🚨"
        )

        media_messages = [m for m in media_list if m.media]
        media_messages.sort(key=lambda x: x.id)

        tasks = [download_media_safe(m, idx) for idx, m in enumerate(media_messages)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await client.send_file(TARGET_CHAT, image_files)
            await client.send_message(TARGET_CHAT, final_text, link_preview=False)
        else:
            await client.send_message(TARGET_CHAT, final_text, link_preview=False)

        print("✅ POST INVIATO CORRETTAMENTE CON DATI E LINK REALE!")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Errore durante l'invio: {e}")

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
