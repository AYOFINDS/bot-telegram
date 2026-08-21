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

# Memoria unificata per raccogliere album e testo correlato dello stesso post
active_posts = {}

@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    msg = event.message
    chat_id = event.chat_id

    # Chiave univoca per identificare il flusso del canale
    key = chat_id

    if key not in active_posts:
        active_posts[key] = {
            'media_list': [],
            'raw_text': "",
            'entities': [],
            'timer': None
        }

    # Se il messaggio ha delle foto (album o foto singola)
    if msg.media:
        active_posts[key]['media_list'].append(msg)
        # Se c'è una didascalia nella foto, salviamola
        cap = getattr(msg, 'caption', '') or ''
        if cap and ('Article:' in cap or 'Price:' in cap):
            active_posts[key]['raw_text'] = cap
            active_posts[key]['entities'] = msg.caption_entities or []

    # Se il messaggio è un blocco di testo separato (quello con Article e Price)
    if msg.text and ('Article:' in msg.text or 'Price:' in msg.text or 'spreadsheet' in msg.text.lower()):
        active_posts[key]['raw_text'] = msg.text
        active_posts[key]['entities'] = msg.entities or []

    # Resetta o avvia il timer di aggregazione (10 secondi di respiro per raccogliere tutto)
    if active_posts[key]['timer']:
        active_posts[key]['timer'].cancel()

    active_posts[key]['timer'] = asyncio.create_task(process_accumulated_post(key))

async def process_accumulated_post(key):
    try:
        # Aspettiamo 10 secondi per assicurarci che siano arrivate tutte le foto e il testo del post
        await asyncio.sleep(10.0)
        
        data = active_posts.pop(key, None)
        if not data:
            return

        media_list = data['media_list']
        source_text = data['raw_text']
        entities = data['entities']

        if not media_list and not source_text:
            return

        print(f"🚨 ELABORAZIONE POST AGGREGATO: {len(media_list)} foto trovate.")

        # Estrazione precisa di articolo e prezzo
        article_line = "🔍 Article: Prodotto Esclusivo"
        price_line = "💰 Price: N/A"

        for line in source_text.split('\n'):
            if 'article:' in line.lower():
                article_line = line.strip()
            elif 'price:' in line.lower():
                price_line = line.strip()

        # Ricerca del link Usfans nelle entità o nel testo
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

        # Sostituzione del codice affiliato con il tuo U2CC3E
        product_link = re.sub(r'[\?&](ref|affcode)=[^&\s]+', '', product_link)
        if '?' in product_link:
            product_link += f'&affcode={AFFILIATE_TAG}'
        else:
            product_link += f'?affcode={AFFILIATE_TAG}'

        # Struttura fissa finale richiesta
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

        # Filtra solo i messaggi multimediali validi
        media_messages = [m for m in media_list if m.media]
        media_messages.sort(key=lambda x: x.id)

        # Scarica le foto in modo sicuro
        tasks = [download_media_safe(m, idx) for idx, m in enumerate(media_messages)]
        downloaded = await asyncio.gather(*tasks)
        image_files = [f for f in downloaded if f is not None]

        if image_files:
            await client.send_file(TARGET_CHAT, image_files)
            await client.send_message(TARGET_CHAT, final_text, buttons=buttons)
        else:
            await client.send_message(TARGET_CHAT, final_text, buttons=buttons)

        print("✅ POST INVIATO ALLA PERFEZIONE!")

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
