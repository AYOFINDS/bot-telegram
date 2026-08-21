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

# Dizionari di accumulo sicuri
pending_albums = {}
pending_texts = {}

def get_product_emoji(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ['shoe', 'sneaker', 'campus', 'jordan', 'dunk', 'yeezy', 'nike', 'adidas', 'air max', 'travis', 'running', 'slide', 'foam', 'saint laurent']):
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
    msg = event.message
    chat_id = event.chat_id

    # Se fa parte di un album
    if msg.grouped_id:
        gid = msg.grouped_id
        if gid not in pending_albums:
            pending_albums[gid] = {
                'chat_id': chat_id,
                'messages': [],
                'timer': None
            }
        
        pending_albums[gid]['messages'].append(msg)
        
        # Resetta il timer ad ogni nuova foto dell'album che arriva
        if pending_albums[gid]['timer']:
            pending_albums[gid]['timer'].cancel()
            
        pending_albums[gid]['timer'] = asyncio.create_task(process_album_delayed(gid))

    # Se è un messaggio di testo con i dettagli del prodotto
    elif msg.text and ("Article:" in msg.text or "Price:" in msg.text):
        pending_texts[chat_id] = msg

    # Foto singola senza album
    elif msg.media:
        await finalize_and_send([msg], None)

async def process_album_delayed(gid):
    try:
        # Aspetta 5 secondi per raccogliere tutte le foto dell'album
        await asyncio.sleep(5.0)
        data = pending_albums.pop(gid, None)
        if data:
            chat_id = data['chat_id']
            messages = data['messages']
            
            # Preleva il testo associato a questo canale arrivato poco prima o poco dopo
            text_msg = pending_texts.pop(chat_id, None)
            
            await finalize_and_send(messages, text_msg)
    except asyncio.CancelledError:
        pass

async def download_media_safe(m, idx):
    if not m.media:
        return None
    try:
        file_bytes = await asyncio.wait_for(client.download_media(m.media, file=bytes), timeout=25.0)
        if file_bytes:
            bio = io.BytesIO(file_bytes)
            bio.name = f"photo_{idx}.jpg"
            return bio
    except Exception as e:
        print(f"⚠️ Errore download media {idx}: {e}")
    return None

async def finalize_and_send(media_list, text_msg):
    print(f"🚨 ELABORAZIONE POST: {len(media_list)} foto trovate.")
    
    full_text = ""
    entities = []

    # Estrae il testo sia dalle didascalie dei media che dal messaggio di testo separato
    for m in media_list:
        cap = getattr(m, 'caption', '') or ''
        if cap:
            full_text += f"\n{cap}"
            if m.caption_entities:
                entities.extend(m.caption_entities)

    if text_msg:
        txt = getattr(text_msg, 'text', '') or ''
        if txt:
            full_text += f"\n{txt}"
            if text_msg.entities:
                entities.extend(text_msg.entities)

    # Parsing pulito di articolo e prezzo
    article_match = re.search(r'Article:\s*(.*)', full_text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*)', full_text, re.IGNORECASE)

    article_val = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    article_val = re.sub(r'<[^>]*>', '', article_val).split('\n')[0].strip()

    price_val = price_match.group(1).strip() if price_match else "N/A"
    price_val = re.sub(r'<[^>]*>', '', price_val).split('\n')[0].strip()

    # Ricerca del link Usfans o link di riferimento nel messaggio
    usfans_link = None
    for entity in entities:
        if hasattr(entity, 'url') and entity.url:
            if 'usfans' in entity.url.lower():
                usfans_link = entity.url
                break

    if not usfans_link:
        for entity in entities:
            if hasattr(entity, 'url') and entity.url and entity.url.startswith("http"):
                usfans_link = entity.url
                break

    if not usfans_link:
        usfans_link = "https://www.usfans.com"

    emoji = get_product_emoji(article_val)

    # Pulizia e formattazione link affiliato
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
        # Ordina i media per ID corretto
        media_list.sort(key=lambda x: x.id)
        
        tasks = [download_media_safe(m, idx) for idx, m in enumerate(media_list)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await client.send_file(TARGET_CHAT, image_files)
            await client.send_message(TARGET_CHAT, new_text, buttons=buttons)
        else:
            await client.send_message(TARGET_CHAT, new_text, buttons=buttons)
            
        print("✅ POST INVIATO PERFETTAMENTE CON TUTTE LE FOTO E TESTO!")
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
