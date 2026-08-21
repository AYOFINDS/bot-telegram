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
LINK_SCONTO = f"https://usfans.com/register?ref={AFFILIATE_TAG}"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

albums_buffer = {}

@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    msg = event.message
    group_id = msg.grouped_id if msg.grouped_id else f"single_{msg.id}"

    if group_id not in albums_buffer:
        albums_buffer[group_id] = {
            'messages': [],
            'caption': "",
            'entities': [],
            'timer': None
        }

    albums_buffer[group_id]['messages'].append(msg)
    
    cap = getattr(msg, 'caption', '') or ''
    if cap:
        albums_buffer[group_id]['caption'] = cap
        albums_buffer[group_id]['entities'] = msg.caption_entities or []

    if albums_buffer[group_id]['timer']:
        albums_buffer[group_id]['timer'].cancel()

    albums_buffer[group_id]['timer'] = asyncio.create_task(process_album(group_id))

async def process_album(group_id):
    try:
        await asyncio.sleep(3.0)
        
        data = albums_buffer.pop(group_id, None)
        if not data:
            return

        messages = data['messages']
        source_text = data['caption']
        entities = data['entities']

        print(f"🚨 ELABORAZIONE ALBUM: {len(messages)} elementi trovati.")

        article_line = "Article: Prodotto Esclusivo"
        price_line = "Price: N/A"

        for line in source_text.split('\n'):
            clean_line = line.strip()
            if 'article:' in clean_line.lower():
                article_line = clean_line
            elif 'price:' in clean_line.lower():
                price_line = clean_line

        # Estrazione intelligente del link del prodotto UsFans (evitando il link di registrazione)
        product_link = None
        
        # 1. Cerca prima nelle entità Telegram
        for entity in entities:
            if hasattr(entity, 'url') and entity.url:
                url_lower = entity.url.lower()
                if 'usfans' in url_lower and 'register' not in url_lower:
                    product_link = entity.url
                    break

        # 2. Se non trovato nelle entità, cerca nel testo con regex
        if not product_link:
            urls = re.findall(r'https?://[^\s]+', source_text)
            for u in urls:
                u_lower = u.lower()
                if 'usfans' in u_lower and 'register' not in u_lower:
                    product_link = u
                    break
            
            # Se c'è un qualsiasi altro link valido (es. Weidian/Taobao), prendiamo quello come fallback
            if not product_link:
                for u in urls:
                    if 'register' not in u.lower():
                        product_link = u
                        break

        # Fallback finale se proprio non trova nulla
        if not product_link:
            product_link = "https://www.usfans.com"

        # Pulizia e iniezione del codice affiliato sul link del prodotto
        product_link = re.sub(r'[\?&](ref|affcode)=[^&\s]+', '', product_link)
        if '?' in product_link:
            product_link += f'&affcode={AFFILIATE_TAG}'
        else:
            product_link += f'?affcode={AFFILIATE_TAG}'

        # Formattazione finale del messaggio
        final_text = (
            f"🎖️ **Official Spreadsheet** 🎖️\n"
            f"✈️ {article_line}\n"
            f"💰 {price_line}\n"
            f"🚚 **Agents:**\n"
            f"🔗 [UsFans]({product_link})\n\n"
            f"✍️ [Register UsFans Here ($820 Coupon)]({LINK_SCONTO}) ✍️\n"
            f"🚨 **Warm Risk Reminder Popup** 🚨"
        )

        media_messages = [m for m in messages if m.media]
        media_messages.sort(key=lambda x: x.id)

        tasks = [download_media_safe(m, idx) for idx, m in enumerate(media_messages)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await client.send_file(TARGET_CHAT, image_files)
            await client.send_message(TARGET_CHAT, final_text, link_preview=False)
        else:
            await client.send_message(TARGET_CHAT, final_text, link_preview=False)

        print("✅ ALBUM INVIATO CORRETTAMENTE CON LINK PRODOTTO CORRETTO!")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Errore durante l'invio dell'album: {e}")

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
