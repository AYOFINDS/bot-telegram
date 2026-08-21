import os
import threading
import logging
import sqlite3
import asyncio
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

# Inserisci qui il tuo vero ID Telegram
ADMIN_IDS = [123456789] 
DB_PATH = "bot_database.db"

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

# --- COMANDI PRINCIPALI ---
@client.on(events.NewMessage(pattern=r'/start'))
async def start(event):
    save_user(event.sender_id, event.sender.first_name)
    increment_stat("/start")
    await event.respond(
        f"👋 Ciao {event.sender.first_name}!\nBenvenuto nel bot. Cosa posso fare per te?",
        buttons=[
            [Button.inline("📊 Statistiche", b"stats")],
            [Button.url("🌐 Sito Web", "https://www.example.com")]
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
        "/admin - Comandi riservati (se sei admin)\n\n"
        "Scrivimi una parola chiave (es. 'ciao') per una risposta personalizzata!"
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
    elif event.data == b"altro":
        await event.answer("Funzione in sviluppo!")

# --- GESTIONE MESSAGGI NORMALI ---
@client.on(events.NewMessage)
async def onNewMessage(event):
    if event.out: 
        return

    save_user(event.sender_id, event.sender.first_name)
    testo = event.raw_text.lower()

    if "ciao" in testo:
        await event.reply("Ciao! Come stai oggi? 😄")
    elif "come stai" in testo:
        await event.reply("Sto molto bene, grazie! Il server è stabile e il database funziona.")
    elif event.photo:
        await event.reply("📸 Bella foto! L'ho salvata.")
    elif event.document:
        await event.reply("📄 Ho ricevuto il tuo file. Lo sto processando...")
    elif event.message.sticker:
        await event.reply("😆 Bello sticker!")
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
            await client.send_message(ADMIN_IDS[0], "☀️ Buongiorno! Questo è il messaggio automatico giornaliero.")

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
