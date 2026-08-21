import os
import re
import asyncio
import io
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import InputMediaPhoto

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

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "U2CC3E")
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
    elif any(k in t for k in ['watch', 'orologio', 'rolex']):
        return "⌚"
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
    await asyncio.sleep(3.0)
    messages = media_groups.pop(gid, [])
    if messages:
        await forward_post(messages)

async def forward_post(messages):
    print(f"🚨 ELABORAZIONE POST ({len(messages)} elementi)...")
    
    # 1. Recupero Testo ed Entità
    full_text = ""
    entities = []
    for m in messages:
        if m.text:
            full_text = m.text
            entities = m.entities or []
            break

    if not full_text:
        return

    # 2. Estrazione Titolo e Prezzo avanzata
    title = "Prodotto Esclusivo"
    price = "N/A"

    title_match = re.search(r'(?:Article|Product|Titolo|Prodotto):\s*(.*)', full_text, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        # Prende la prima riga di testo valida come titolo
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        if lines:
            title = lines[0]

    price_match = re.search(r'(?:Price|Prezzo):\s*([€$]?\s*\d+[\.,]?\d*)', full_text, re.IGNORECASE)
    if price_match:
        price = price_match.group(1).strip().replace('€', '').replace('$', '')
    else:
        num_match = re.search(r'(\d+[\.,]\d{2})', full_text)
        if num_match:
            price = num_match.group(1)

    emoji = get_product_emoji(title)

    # 3. Estrazione Link Prodotto Completo
    usfans_link = None
    
    if entities:
        for entity in entities:
            if hasattr(entity, 'url') and entity.url:
                if 'usfans' in entity.url.lower() or 'kakobuy' in entity.url.lower() or 'http' in entity.url.lower():
                    usfans_link = entity.url
                    break

    if not usfans_link:
        urls = re.findall(r'https?://[^\s]+', full_text)
        if urls:
            usfans_link = urls[0]

    if not usfans_link:
        usfans_link = "https://usfans.com"

    # Sostituzione/Inserimento del Tag Affiliato nell'URL specifico
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
        image_files = []
        messages.sort(key=lambda m: m.id)

        for idx, m in enumerate(messages):
            if m.media:
                file_bytes = await user_client.download_media(m.media, file=bytes)
                if file_bytes:
                    bio = io.BytesIO(file_bytes)
                    bio.name = f"photo_{idx}.jpg"
                    image_files.append(bio)

        if image_files:
            # Invio album foto
            await bot_client.send_file(
                TARGET_CHAT, 
                image_files
            )
            # Invio messaggio formattato con i pulsanti attivi subito sotto
            await bot_client.send_message(
                TARGET_CHAT,
                new_text,
                buttons=buttons
            )
        else:
            await bot_client.send_message(TARGET_CHAT, new_text, buttons=buttons)
            
        print("✅ POST, LINK COMPLETI E BOTTONI PUBBLICATI CON SUCCESSO!")
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
