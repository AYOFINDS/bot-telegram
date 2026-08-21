import os
import re
import asyncio
import io
import time
from flask import Flask
from threading import Thread
from waitress import serve
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

# ----------------------------- Flask -----------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot attivo 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)

# -------------------------- Config -------------------------------
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

# Canali sorgente: possono essere username (stringa) o ID (int)
SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

# ------------------------ Buffer Globale -------------------------
buffers = {}                 # chiave -> dati del buffer
chat_active_buffers = {}     # chat_id -> [lista di chiavi attive]
BUFFER_TIMEOUT = 5.0         # secondi per attendere il messaggio complementare

# -------------------------- Funzioni -----------------------------
def fix_affiliate_link(url, tag=AFFILIATE_TAG):
    """Aggiunge o sostituisce il parametro affcode/ref con il tag affiliato."""
    if not url:
        return url
    new_url, count = re.subn(r'([?&])(ref|affcode)=[^&\s]+', rf'\1\2={tag}', url)
    if count > 0:
        return new_url
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}affcode={tag}"

async def download_media_safe(msg, idx):
    """Scarica un media in bytes con timeout."""
    if not msg.media:
        return None
    try:
        file_bytes = await asyncio.wait_for(
            client.download_media(msg.media, file=bytes),
            timeout=30.0
        )
        if file_bytes:
            bio = io.BytesIO(file_bytes)
            bio.name = f"photo_{idx}.jpg"
            return bio
    except Exception as e:
        print(f"⚠️ Errore download media: {e}")
    return None

async def process_post(key):
    """Elabora il buffer dopo il timeout o al momento dell'unione."""
    try:
        await asyncio.sleep(BUFFER_TIMEOUT)  # attesa per eventuali messaggi complementari
    except asyncio.CancelledError:
        # Il timer è stato cancellato perché il buffer è stato unito a un altro
        return

    # Recupera e rimuovi il buffer
    data = buffers.pop(key, None)
    if not data:
        return

    # Rimuovi la chiave dalla lista attiva del chat
    chat_id = data['chat_id']
    if chat_id in chat_active_buffers and key in chat_active_buffers[chat_id]:
        chat_active_buffers[chat_id].remove(key)
        if not chat_active_buffers[chat_id]:
            del chat_active_buffers[chat_id]

    media_list = data['media_list']
    source_text = data['text'] or ""
    entities = data['entities'] or []

    # Estrai Article e Price
    article_line = "Article: Prodotto Esclusivo"
    price_line = "Price: N/A"

    for line in source_text.split('\n'):
        clean = line.strip()
        if 'article:' in clean.lower():
            article_line = clean
        elif 'price:' in clean.lower():
            price_line = clean

    # Estrai il link del prodotto (escludendo quelli di registrazione)
    product_link = None
    # 1) Dai link nelle entities (più affidabile)
    for entity in entities:
        if hasattr(entity, 'url') and entity.url:
            if 'register' not in entity.url.lower():
                product_link = entity.url
                break
    # 2) Se non trovato, cerca con regex
    if not product_link:
        urls = re.findall(r'https?://[^\s]+', source_text)
        for u in urls:
            if 'register' not in u.lower():
                product_link = u
                break
    # 3) Fallback
    if not product_link:
        product_link = "https://www.usfans.com"

    product_link = fix_affiliate_link(product_link)

    # Costruzione del messaggio finale
    final_text = (
        f"🎖️ **Official Spreadsheet** 🎖️\n"
        f"✈️ {article_line}\n"
        f"💰 {price_line}\n"
        f"🚚 **Agents:**\n"
        f"🔗 [UsFans]({product_link})\n\n"
        f"✍️ [Register UsFans Here ($820 Coupon)]({LINK_SCONTO}) ✍️\n"
        f"🚨 **Warm Risk Reminder Popup** 🚨"
    )

    # Scarica le foto
    media_messages = [m for m in media_list if m.media]
    media_messages.sort(key=lambda x: x.id)  # ordine di arrivo
    tasks = [download_media_safe(m, i) for i, m in enumerate(media_messages)]
    downloaded = await asyncio.gather(*tasks)
    image_files = [f for f in downloaded if f is not None]

    # Invio
    if image_files:
        await client.send_file(TARGET_CHAT, image_files, album=True)
        await client.send_message(TARGET_CHAT, final_text, link_preview=False)
    else:
        await client.send_message(TARGET_CHAT, final_text, link_preview=False)

# -------------------------- Handler ------------------------------
@client.on(events.NewMessage)
async def handler(event):
    msg = event.message
    chat_id = event.chat_id
    chat = await event.get_chat()
    chat_title = getattr(chat, 'title', getattr(chat, 'username', 'Chat privata'))

    # Verifica se il canale è nella lista sorgente
    is_valid = False
    for src in SOURCE_CHATS:
        if str(src) == str(chat_id) or (isinstance(src, str) and src.lower() in str(chat_title).lower()):
            is_valid = True
            break
    if not is_valid:
        return

    # Determina se il messaggio ha media e/o testo
    has_media = msg.media is not None
    has_text = msg.text is not None and msg.text.strip() != ""

    # Se non ha né media né testo, ignora
    if not has_media and not has_text:
        return

    # Chiave univoca per il buffer
    if has_media and msg.grouped_id:
        key = msg.grouped_id
    elif has_media:
        key = msg.id  # singola foto (non album)
    else:
        key = "text_" + str(msg.id)  # messaggio di solo testo

    # Se esiste già un buffer con questa chiave (es. altri media dello stesso album)
    if key in buffers:
        buffer = buffers[key]
        if has_media:
            buffer['media_list'].append(msg)
        if has_text:
            buffer['text'] = msg.text
            buffer['entities'] = msg.entities or []
        # Reset del timer (perché abbiamo nuovi dati)
        if buffer['timer']:
            buffer['timer'].cancel()
        buffer['timer'] = asyncio.create_task(process_post(key))
        buffer['timestamp'] = time.time()
        return

    # Cerca un buffer attivo nello stesso chat a cui unire questo messaggio
    now = time.time()
    active_keys = chat_active_buffers.get(chat_id, [])
    merged = False

    for other_key in active_keys:
        if other_key == key:
            continue
        other = buffers.get(other_key)
        if not other:
            continue
        # Deve essere stato creato entro BUFFER_TIMEOUT
        if now - other['timestamp'] > BUFFER_TIMEOUT:
            continue

        # Condizioni di unione:
        # - se abbiamo media e l'altro buffer non ha ancora media
        # - oppure se abbiamo testo e l'altro buffer non ha ancora testo
        if has_media and not other['media_list']:
            # uniamo il media all'altro buffer
            other['media_list'].append(msg)
            if has_text:  # se il media ha anche caption, la usiamo come testo
                other['text'] = msg.text
                other['entities'] = msg.entities or []
            merged = True
        elif has_text and not other['text']:
            # uniamo il testo all'altro buffer
            other['text'] = msg.text
            other['entities'] = msg.entities or []
            merged = True

        if merged:
            # Reset del timer dell'altro buffer
            if other['timer']:
                other['timer'].cancel()
            other['timer'] = asyncio.create_task(process_post(other_key))
            other['timestamp'] = time.time()
            break

    if merged:
        return

    # Nessun buffer compatibile trovato: crea un nuovo buffer
    new_buffer = {
        'media_list': [msg] if has_media else [],
        'text': msg.text if has_text else "",
        'entities': msg.entities or [],
        'timer': None,
        'timestamp': now,
        'chat_id': chat_id
    }
    buffers[key] = new_buffer
    new_buffer['timer'] = asyncio.create_task(process_post(key))
    chat_active_buffers.setdefault(chat_id, []).append(key)

# -------------------------- Main --------------------------------
async def main():
    while True:
        try:
            await client.start()
            await client.run_until_disconnected()
            break
        except FloodWaitError as e:
            print(f"⏳ FloodWait: aspetto {e.seconds} secondi")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"❌ Errore client: {e}")
            await asyncio.sleep(10)

if __name__ == '__main__':
    # Avvia Flask in un thread separato
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    # Avvia il client Telethon
    asyncio.run(main())
