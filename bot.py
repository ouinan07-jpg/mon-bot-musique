import os
import sqlite3
import logging
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from mutagen.easyid3 import EasyID3

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

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

# --- Indexation des fichiers ---
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
        artist = audio_tags.get('artist', ['Inconnu'])[0]
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

# --- Navigation Playlist ---
async def playlists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT artist FROM tracks ORDER BY artist")
    artists = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not artists:
        await update.message.reply_text("Ta bibliothèque est vide. Envoie-moi des MP3 !")
        return

    keyboard = []
    for artist in artists:
        keyboard.append([InlineKeyboardButton(artist, callback_data=f"artist:{artist}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎤 **Choisis un artiste :**", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    conn = init_db()
    cursor = conn.cursor()

    if data.startswith("artist:"):
        artist_name = data.split(":", 1)[1]
        cursor.execute("SELECT DISTINCT album FROM tracks WHERE artist = ? ORDER BY album", (artist_name,))
        albums = [row[0] for row in cursor.fetchall()]
        conn.close()

        keyboard = []
        for album in albums:
            keyboard.append([InlineKeyboardButton(album, callback_data=f"album:{artist_name}:{album}")])
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_to_artists")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"💿 **Albums de {artist_name} :**", reply_markup=reply_markup, parse_mode='Markdown')

    elif data.startswith("album:"):
        _, artist_name, album_name = data.split(":", 2)
        cursor.execute("SELECT id, title FROM tracks WHERE artist = ? AND album = ? ORDER BY title", (artist_name, album_name))
        tracks = cursor.fetchall()
        conn.close()

        keyboard = []
        for track_id, title in tracks:
            keyboard.append([InlineKeyboardButton(f"▶️ {title}", callback_data=f"track:{track_id}")])
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data=f"artist:{artist_name}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"🎵 **Morceaux de l'album {album_name} :**", reply_markup=reply_markup, parse_mode='Markdown')

    elif data.startswith("track:"):
        track_id = data.split(":", 1)[1]
        cursor.execute("SELECT file_id, title, artist FROM tracks WHERE id = ?", (track_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            file_id, title, artist = result
            await query.message.reply_audio(audio=file_id, title=title, performer=artist)
        else:
            await query.message.reply_text("Morceau introuvable.")

    elif data == "back_to_artists":
        conn.close()
        await playlists(update, context)

# --- Point d'entrée ---
if __name__ == '__main__':
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'TON_TOKEN_ICI')
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("playlists", playlists))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    
    print("Le bot est en marche...")
    app.run_polling()
