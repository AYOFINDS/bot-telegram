import os
import re
import threading
import logging
import sqlite3
import asyncio
import io
import time
from datetime import datetime
from flask import Flask
from waitress import serve
from telethon import TelegramClient, events, Button
import tgcrypto

# --- CONFIGURAZIONE LOG E VARIABILI ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

api_id = int(os.environ.get("API_ID", "0"))
api_hash = os.environ.get("API_HASH", "YOUR_API_HASH")
bot_token = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
port = int(os.environ.get("PORT", "8000"))

# ID Admin
ADMIN_IDS = [6636517553] 
DB_PATH = "bot_database.db"

# Canali sorgente da cui catturare i post
SOURCE_CHATS = ["KakobuySpreadsheet6", -1003634367021, 3634367021]

# Chat di destinazione (può essere un ID numerico o un username es. "@tuocanale")
raw_target = os.environ.get("TARGET_CHAT", "").strip()
TARGET_CHAT = int(raw_target) if raw_target.lstrip('-').isdigit() else raw_target

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "U2CC3E")
LINK_SCONTO = f"https://www.usfans.com/register?ref={AFFILIATE_TAG}"

# ------------------------ Buffer Globale per Album/Testo -------------------------
buffers = {}                 # chiave -> dati del buffer
chat_active_buffers = {}     # chat_id -> [lista di chiavi attive]
BUFFER_TIMEOUT = 5.0         # secondi per attendere il messaggio complementare

# --- INIZIALIZZAZIONE CLIENT E FLASK ---
client = TelegramClient("bot_session", api_id, api_hash)
app = Flask(__name__)

# --- GESTIONE DATABASE (SQLite) ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, first_name TEXT, last_seen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats (command TEXT PRIMARY KEY, count INTEGER)''')
    conn.commit()
    conn.close()

def save_user(user_id, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (id, first_name, last_seen) VALUES (?, ?, ?)", (user_id, first_name, datetime.now()))
    conn.commit()
    conn.close()

def increment_stat(command):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO stats (command, count) VALUES (?, 1) ON CONFLICT(command) DO UPDATE SET count = count + 1", (command,))
    conn.commit()
    conn.close()

init_db()

# --- WEB SERVER (Flask per Railway) ---
@app.route('/')
def home():
    return "Bot in esecuzione su Railway!"

# --- HELPERS ---
async def is_admin(event):
    return event.sender_id in ADMIN_IDS

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
        logger.warning(f"Errore download media: {e}")
    return None

async def process_post(key):
    """Elabora il buffer dopo il timeout e invia il post formattato."""
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

    if TARGET_CHAT:
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
        logger.info("Post elaborato e inviato al target con successo!")

# --- COMANDI PRINCIPALI ---
@client.on(events.NewMessage(pattern=r'/start'))
async def start(event):
    save_user(event.sender_id, event.sender.first_name)
    increment_stat("/start")
    await event.respond(
        f"👋 Ciao {event.sender.first_name}!\nBenvenuto nel bot. Cosa posso fare per te?",
        buttons=[
            [Button.inline("📊 Statistiche", b"stats")],
            [Button.url("🌐 Sito Web", "https://www.usfans.com")]
        ]
    )

@client.on(events.NewMessage(pattern=r'/help'))
async def help(event):
    increment_stat("/help")
    await event.respond(
        "📚 **Elenco Comandi:**\n"
        "/start - Avvia il bot\n"
        "/help - Mostra questo aiuto\n"
        "/info - Mostra le tue info\n"
        "/admin - Comandi riservati\n"
    )

@client.on(events.NewMessage(pattern=r'/info'))
async def info(event):
    increment_stat("/info")
    await event.respond(
        f"👤 **Nome:** {event.sender.first_name} {event.sender.last_name or ''}\n"
        f"🆔 **ID Utente:** `{event.sender_id}`\n"
        f"👥 **Chat:** {event.chat_id}"
    )

# --- COMANDI ADMIN ---
@client.on(events.NewMessage(pattern=r'/broadcast'))
async def broadcast(event):
    increment_stat("/broadcast")
    if not await is_admin(event):
        return await event.reply("⛔ Non hai i permessi per questo comando.")
    
    msg = event.raw_text.replace("/broadcast", "").strip()
    if not msg:
        return await event.reply("Uso corretto: /broadcast <messaggio>")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users")
    users = c.fetchall()
    conn.close()
    
    await event.reply(f"📢 Invio il messaggio a {len(users)} utenti...")
    for user in users:
        try:
            await client.send_message(user[0], msg)
            await asyncio.sleep(0.5)
        except:
            pass

@client.on(events.NewMessage(pattern=r'/stats'))
async def stats(event):
    increment_stat("/stats")
    if not await is_admin(event):
        return await event.reply("⛔ Solo admin.")
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT * FROM stats ORDER BY count DESC LIMIT 5")
    top_commands = c.fetchall()
    conn.close()
    
    stats_text = f"📈 **Totale Utenti:** {total_users}\n\n**Comandi più usati:**\n"
    for cmd, cnt in top_commands:
        stats_text += f"• {cmd}: {cnt}\n"
        
    await event.reply(stats_text)

# --- GESTIONE TASTI INLINE ---
@client.on(events.CallbackQuery)
async def callback(event):
    if event.data == b"stats":
        await event.answer("Apertura statistiche...")
        await event.edit("Le statistiche sono state inviate in privato!")

# --- GESTIONE MESSAGGI (Sorgenti + Chat Utenti) ---
@client.on(events.NewMessage)
async def onNewMessage(event):
    if event.out: 
        return

    msg = event.message
    chat_id = event.chat_id
    chat = await event.get_chat()
    chat_title = getattr(chat, 'title', getattr(chat, 'username', 'Chat privata'))

    # Verifica se il messaggio arriva dai canali sorgente configurati
    is_source = any(
        str(src) == str(chat_id) or
        (isinstance(src, str) and src.lower() in str(chat_title).lower())
        for src in SOURCE_CHATS
    )

    if is_source:
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
        return

    # Gestione normale utenti privati / comandi bot
    if event.raw_text.startswith('/'):
        return

    save_user(event.sender_id, event.sender.first_name)
    testo = event.raw_text.lower()

    if "ciao" in testo:
        await event.reply("Ciao! Come stai oggi? 😄")
    else:
        await event.client.send_message(
            event.chat_id, 
            f"Non ho capito il comando: {testo}.\nUsa /help per la lista dei comandi."
        )

# --- TASK ASINCRONI ---
async def daily_task():
    while True:
        await asyncio.sleep(86400)
        now = datetime.now()
        if now.hour == 9:
            await client.send_message(ADMIN_IDS[0], "☀️ Buongiorno! Messaggio automatico giornaliero.")

# --- AVVIO FLASK IN THREAD SEPARATO ---
def run_flask():
    logger.info(f"Avvio server Flask sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)

# --- MAIN ---
async def main():
    await client.start(bot_token=bot_token)
    logger.info("Avvio del Bot Telegram...")
    client.loop.create_task(daily_task())
    await client.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot fermato manualmente.")
    except Exception as e:
        logger.error(f"Errore critico: {e}")
