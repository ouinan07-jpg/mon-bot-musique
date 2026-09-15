import os
import re
import sqlite3
import logging
import asyncio
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from mutagen.easyid3 import EasyID3

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

user_sent_messages = {}

def init_db():
    conn = sqlite3.connect('music_index.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            artist TEXT,
            title TEXT,
            album TEXT,
            genre TEXT
        )
    ''')
    conn.commit()
    return conn

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salut ! Envoie-moi tes fichiers MP3 pour les indexer.\n\n"
        "Utilise /playlists pour naviguer dans ta musique. 🎵"
    )

def clean_artist_name(artist_string):
    if not artist_string or artist_string == "Inconnu":
        return "Inconnu"
    parts = re.split(r',|&| feat\.| ft\.| x ', artist_string, flags=re.IGNORECASE)
    cleaned_parts = [p.strip() for p in parts if p.strip()]
    return ", ".join(cleaned_parts)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    audio = message.audio or message.document
    if not audio:
        return

    file = await context.bot.get_file(audio.file_id)
    file_bytes = await file.download_as_bytearray()
    
    artist, title, album, genre = "Inconnu", "Inconnu", "Inconnu", "Inconnu"
    try:
        audio_tags = EasyID3(BytesIO(file_bytes))
        raw_artist = audio_tags.get('artist', ['Inconnu'])[0]
        artist = clean_artist_name(raw_artist)
        title = audio_tags.get('title', ['Inconnu'])[0]
        album = audio_tags.get('album', ['Inconnu'])[0]
        genre = audio_tags.get('genre', ['Inconnu'])[0]
    except Exception as e:
        logging.warning(f"Impossible de lire les tags : {e}")

    conn = init_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tracks (file_id, artist, title, album, genre) VALUES (?, ?, ?, ?, ?)",
        (audio.file_id, artist, title, album, genre)
    )
    conn.commit()
    conn.close()

    await message.reply_text(
        f"✅ Ajouté :\n🎤 **Artiste :** {artist}\n🎵 **Titre :** {title}\n💿 **Album :** {album}",
        parse_mode='Markdown'
    )

# --- Fonction utilitaire pour générer le menu des artistes ---
def get_artists_menu():
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT artist FROM tracks")
    raw_artists = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not raw_artists:
        return "Ta bibliothèque est vide. Envoie-moi des MP3 !", None

    grouped_artists = {}
    for raw in raw_artists:
        if not raw or raw == "Inconnu":
            continue
        parts = re.split(r',|&| feat\.| ft\.| x ', raw, flags=re.IGNORECASE)
        for p in parts:
            cleaned = p.strip()
            if cleaned:
                key = cleaned.lower()
                if key not in grouped_artists:
                    grouped_artists[key] = cleaned

    sorted_artists = sorted(grouped_artists.values())
    
    keyboard = []
    for artist in sorted_artists:
        keyboard.append([InlineKeyboardButton(artist, callback_data=f"artist:{artist}")])
    
    return "🎤 **Choisis un artiste :**", InlineKeyboardMarkup(keyboard)

async def playlists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_artists_menu()
    if reply_markup:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    conn = init_db()
    cursor = conn.cursor()

    if data.startswith("artist:"):
        artist_name = data.split(":", 1)[1]
        cursor.execute("SELECT DISTINCT album FROM tracks WHERE artist LIKE ? ORDER BY album", (f'%{artist_name}%',))
        albums = [row[0] for row in cursor.fetchall()]
        conn.close()

        keyboard = []
        keyboard.append([InlineKeyboardButton("🎶 Tout lire", callback_data=f"playall:{artist_name}")])
        for album in albums:
            keyboard.append([InlineKeyboardButton(f"💿 {album}", callback_data=f"album:{artist_name}:{album}")])
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_to_artists")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"🎤 **{artist_name}**\nChoisis un album ou écoute tout :", reply_markup=reply_markup, parse_mode='Markdown')

    elif data.startswith("playall:"):
        artist_name = data.split(":", 1)[1]
        cursor.execute("SELECT file_id, title, album FROM tracks WHERE artist LIKE ? ORDER BY album, title", (f'%{artist_name}%',))
        tracks = cursor.fetchall()
        conn.close()

        if tracks:
            await query.message.reply_text(f"🎵 Envoi de tous les morceaux de **{artist_name}**...")
            sent_msgs = []
            for file_id, title, album in tracks:
                try:
                    msg = await query.message.reply_audio(audio=file_id, title=title, performer=artist_name)
                    sent_msgs.append(msg.message_id)
                    await asyncio.sleep(1)
                except Exception as e:
                    logging.error(f"Erreur envoi {title}: {e}")
            user_sent_messages[user_id] = sent_msgs
        else:
            await query.message.reply_text("Aucun morceau trouvé.")

    elif data.startswith("album:"):
        _, artist_name, album_name = data.split(":", 2)
        cursor.execute("SELECT file_id, title FROM tracks WHERE artist LIKE ? AND album = ? ORDER BY title", (f'%{artist_name}%', album_name))
        tracks = cursor.fetchall()
        conn.close()

        if tracks:
            await query.message.reply_text(f"🎵 Envoi de l'album **{album_name}**...")
            sent_msgs = []
            for file_id, title in tracks:
                try:
                    msg = await query.message.reply_audio(audio=file_id, title=title, performer=artist_name)
                    sent_msgs.append(msg.message_id)
                    await asyncio.sleep(1)
                except Exception as e:
                    logging.error(f"Erreur envoi {title}: {e}")
            user_sent_messages[user_id] = sent_msgs
        else:
            await query.message.reply_text("Aucun morceau trouvé dans cet album.")

    elif data == "back_to_artists":
        # 1. Supprimer les messages audio envoyés précédemment
        if user_id in user_sent_messages:
            for msg_id in user_sent_messages[user_id]:
                try:
                    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
                except Exception as e:
                    logging.warning(f"Impossible de supprimer le message {msg_id}: {e}")
            del user_sent_messages[user_id]
        
        # 2. Remplacer le message actuel par la liste des artistes
        text, reply_markup = get_artists_menu()
        if reply_markup:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text(text)

if __name__ == '__main__':
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'TON_TOKEN_ICI')
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("playlists", playlists))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    
    print("Le bot est en marche...")
    app.run_polling()
