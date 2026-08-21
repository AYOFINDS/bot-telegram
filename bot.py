import os
import threading
import logging
from flask import Flask
from waitress import serve
from telethon import TelegramClient, events, Button
import tgcrypto  # Import necessario per velocizzare Telethon

# --- CONFIGURAZIONE ---
logging.basicConfig(level=logging.INFO)
api_id = int(os.environ.get("API_ID", "0"))
api_hash = os.environ.get("API_HASH", "YOUR_API_HASH")
bot_token = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
port = int(os.environ.get("PORT", "8000"))

# --- INIZIALIZZAZIONE OGGETTI (PRIMA DI TUTTO! RISOLVE IL NameError) ---
# Passo 'tgcrypto' esplicitamente per usare le sue performance
client = TelegramClient("bot_session", api_id, api_hash).start(bot_token=bot_token)
app = Flask(__name__)

# --- HELPERS (Funzioni di supporto) ---
def get_user_info(event):
    """Restituisce informazioni formattate sull'utente."""
    user = event.sender
    return f"👤 **Nome:** {user.first_name}\n🆔 **ID:** {user.id}"

def log_message(event):
    """Logga i messaggi sul server (utile per debug)."""
    print(f"Messaggio ricevuto da {event.sender_id}: {event.raw_text}")

# --- WEB SERVER (Flask per Railway) ---
@app.route('/')
def home():
    return "🚀 Bot Telegram Online!"

# --- COMANDI DEL BOT (La tua logica personalizzata va qui) ---
@client.on(events.NewMessage(pattern=r'/start'))
async def start(event):
    await log_message(event)
    await event.respond(
        f"Ciao {event.sender.first_name}! 👋\nSono un bot completo in esecuzione su Railway.",
        buttons=[
            [Button.url("Visita il mio sito", "https://google.com")],
            [Button.inline("📊 Menu Admin", b"admin_menu")]
        ]
    )

@client.on(events.NewMessage(pattern=r'/help'))
async def help(event):
    await event.respond(
        "📚 **Lista Comandi:**\n"
        "/start - Avvia il bot\n"
        "/help - Mostra questo menu\n"
        "/info - Mostra le tue info\n"
        "/admin - Pannello Admin\n\n"
        "Scrivimi qualsiasi cosa e ti risponderò!"
    )

@client.on(events.NewMessage(pattern=r'/info'))
async def info(event):
    info_text = await get_user_info(event)
    await event.respond(f"📄 **Informazioni Utente:**\n{info_text}")

@client.on(events.NewMessage(pattern=r'/admin'))
async def admin(event):
    # Esempio di whitelist ID (Inserisci il tuo ID)
    if event.sender_id == 123456789: 
        await event.respond("⚙️ **Pannello Admin attivato!**", buttons=[[Button.inline("Banna utenti", b"ban")]])
    else:
        await event.respond("⛔ Non hai i permessi per usare questo comando.")

# --- GESTIONE DEI TASTI (Callback Query) ---
@client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data
    if data == b"admin_menu":
        await event.answer("Apertura menu admin...")
        await event.edit("🛠️ Menù Admin selezionato.", buttons=[[Button.inline("Indietro", b"back")]])
    elif data == b"ban":
        await event.answer("Funzione di ban non implementata!")
    elif data == b"back":
        await event.edit("Sei tornato al menu principale.", buttons=[[Button.inline("📊 Admin", b"admin_menu")]])

# --- GESTIONE MESSAGGI NORMALI (La tua funzione onNewMessage) ---
@client.on(events.NewMessage)
async def onNewMessage(event):
    # Ignora i messaggi scritti dal bot stesso
    if event.out:
        return

    await log_message(event)

    # LOGICA PERSONALIZZATA QUI (es. riconoscimento testo, comandi custom)
    testo = event.raw_text
    
    if "ciao" in testo.lower():
        await event.reply("Ciao! Come stai? 😄")
    elif "come stai" in testo.lower():
        await event.reply("Sto benissimo, grazie di avermelo chiesto!")
    else:
        # Usa sempre 'event.client' per massima sicurezza
        await event.client.send_message(event.chat_id, f"Hai scritto: {testo}")

# --- AVVIO SERVER FLASK IN THREAD SEPARATO ---
def run_flask():
    print(f"🌐 Server Flask in ascolto sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)

# --- AVVIO PRINCIPALE ---
if __name__ == "__main__":
    # 1. Avvia Flask
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. Avvia Bot
    print("🤖 Avvio del Bot Telegram...")
    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("Bot fermato manualmente.")
    except Exception as e:
        print(f"❌ Errore critico nel bot: {e}")
        client.disconnect()
