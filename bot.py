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

SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

buffers = {}
chat_active_buffers = {}
BUFFER_TIMEOUT = 5.0

def fix_affiliate_link(url, tag=AFFILIATE_TAG):
    if not url:
        return url
    new_url, count = re.subn(r'([?&])(ref|affcode)=[^&\s]+', rf'\1\2={tag}', url)
    if count > 0:
        return new_url
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}affcode={tag}"

async def download_media_safe(msg, idx):
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
    try:
        await asyncio.sleep(BUFFER_TIMEOUT)
    except asyncio.CancelledError:
        return

    data = buffers.pop(key, None)
    if not data:
        return

    chat_id = data['chat_id']
    if chat_id in chat_active_buffers and key in chat_active_buffers[chat_id]:
        chat_active_buffers[chat_id].remove(key)
        if not chat_active_buffers[chat_id]:
            del chat_active_buffers[chat_id]

    media_list = data['media_list']
    source_text = data['text'] or ""
    entities = data['entities'] or []

    article_line = "Article: Prodotto Esclusivo"
    price_line = "Price: N/A"
    for line in source_text.split('\n'):
        clean = line.strip()
        if 'article:' in clean.lower():
            article_line = clean
        elif 'price:' in clean.lower():
            price_line = clean

    product_link = None
    for entity in entities:
        if hasattr(entity, 'url') and entity.url:
            if 'register' not in entity.url.lower():
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
    tasks = [download_media_safe(m, i) for i, m in enumerate(media_messages)]
    downloaded = await asyncio.gather(*tasks)
    image_files = [f for f in downloaded if f is not None]

    if image_files:
        await client.send_file(
            TARGET_CHAT,
            image_files,
            album=True,
            caption=final_text,
            link_preview=False
        )
    else:
        await client.send_message(TARGET_CHAT, final_text, link_preview=False)

@client.on(events.NewMessage)
async def handler(event):
    msg = event.message
    chat_id = event.chat_id
    chat = await event.get_chat()
    chat_title = getattr(chat, 'title', getattr(chat, 'username', 'Chat privata'))

    is_valid = any(
        str(src) == str(chat_id) or
        (isinstance(src, str) and src.lower() in str(chat_title).lower())
        for src in SOURCE_CHATS
    )
    if not is_valid:
        return

    has_media = msg.media is not None
    has_text = msg.text is not None and msg.text.strip() != ""

    if not has_media and not has_text:
        return

    now = time.time()
    grouped_id = msg.grouped_id if has_media else None
    if not has_media and has_text:
        key = "text_" + str(msg.id)
    elif has_media and grouped_id:
        key = grouped_id
    else:
        key = msg.id

    if key in buffers:
        buffer = buffers[key]
        if has_media:
            buffer['media_list'].append(msg)
        if has_text:
            buffer['text'] = msg.text
            buffer['entities'] = msg.entities or []
        if buffer['timer']:
            buffer['timer'].cancel()
        buffer['timer'] = asyncio.create_task(process_post(key))
        buffer['timestamp'] = now
        return

    if has_media and grouped_id:
        active_keys = chat_active_buffers.get(chat_id, [])
        for other_key in active_keys:
            other = buffers.get(other_key)
            if not other:
                continue
            if now - other['timestamp'] > BUFFER_TIMEOUT:
                continue
            if not other['media_list'] and other['text']:
                other['media_list'].append(msg)
                del buffers[other_key]
                buffers[grouped_id] = other
                if chat_id in chat_active_buffers:
                    chat_active_buffers[chat_id].remove(other_key)
                    chat_active_buffers[chat_id].append(grouped_id)
                if other['timer']:
                    other['timer'].cancel()
                other['timer'] = asyncio.create_task(process_post(grouped_id))
                other['timestamp'] = now
                return

        new_buffer = {
            'media_list': [msg],
            'text': msg.caption or "",
            'entities': msg.caption_entities or [],
            'timer': None,
            'timestamp': now,
            'chat_id': chat_id
        }
        buffers[grouped_id] = new_buffer
        new_buffer['timer'] = asyncio.create_task(process_post(grouped_id))
        chat_active_buffers.setdefault(chat_id, []).append(grouped_id)
        return

    if has_text and not has_media:
        active_keys = chat_active_buffers.get(chat_id, [])
        for other_key in active_keys:
            other = buffers.get(other_key)
            if not other:
                continue
            if now - other['timestamp'] > BUFFER_TIMEOUT:
                continue
            if other['media_list'] and not other['text']:
                other['text'] = msg.text
                other['entities'] = msg.entities or []
                if other['timer']:
                    other['timer'].cancel()
                other['timer'] = asyncio.create_task(process_post(other_key))
                other['timestamp'] = now
                return

        new_buffer = {
            'media_list': [],
            'text': msg.text,
            'entities': msg.entities or [],
            'timer': None,
            'timestamp': now,
            'chat_id': chat_id
        }
        buffers[key] = new_buffer
        new_buffer['timer'] = asyncio.create_task(process_post(key))
        chat_active_buffers.setdefault(chat_id, []).append(key)

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
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    asyncio.run(main())
