import os
import sqlite3
import logging
from io import BytesIO
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from mutagen.easyid3 import EasyID3

# --- Configuration ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Initialisation de la base de données
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

# Commande /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salut ! Envoie-moi tes fichiers MP3 et je les rangerai par artiste, album et titre. 🎵"
    )

# Réception d'un fichier audio
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    audio = message.audio or message.document
    if not audio:
        return

    # Télécharger temporairement le fichier pour lire les tags
    file = await context.bot.get_file(audio.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Lire les tags avec mutagen
    artist, title, album, genre = "Inconnu", "Inconnu", "Inconnu", "Inconnu"
    try:
        audio_tags = EasyID3(BytesIO(file_bytes))
        artist = audio_tags.get('artist', ['Inconnu'])[0]
        title = audio_tags.get('title', ['Inconnu'])[0]
        album = audio_tags.get('album', ['Inconnu'])[0]
        genre = audio_tags.get('genre', ['Inconnu'])[0]
    except Exception as e:
        logging.warning(f"Impossible de lire les tags : {e}")

    # Stocker dans la base de données
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tracks (file_id, artist, title, album, genre) VALUES (?, ?, ?, ?, ?)",
        (audio.file_id, artist, title, album, genre)
    )
    conn.commit()
    conn.close()

    await message.reply_text(
        f"✅ Ajouté :\n🎤 **Artiste :** {artist}\n🎵 **Titre :** {title}\n💿 **Album :** {album}\n🎼 **Genre :** {genre}",
        parse_mode='Markdown'
    )

# Commande /artistes
async def list_artists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT artist FROM tracks ORDER BY artist")
    artists = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if artists:
        await update.message.reply_text("🎤 **Artistes disponibles :**\n" + "\n".join(artists), parse_mode='Markdown')
    else:
        await update.message.reply_text("Ta bibliothèque est vide pour le moment.")

# Commande /albums <artiste>
async def list_albums(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Utilisation : /albums <nom de l'artiste>")
        return
    
    artist_name = " ".join(context.args)
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT album FROM tracks WHERE artist LIKE ? ORDER BY album", (f'%{artist_name}%',))
    albums = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if albums:
        await update.message.reply_text(f"💿 **Albums de {artist_name} :**\n" + "\n".join(albums), parse_mode='Markdown')
    else:
        await update.message.reply_text(f"Aucun album trouvé pour l'artiste '{artist_name}'.")

# Commande /ecoute <artiste>
async def listen_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Utilisation : /ecoute <nom de l'artiste>")
        return
    
    artist_name = " ".join(context.args)
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, title FROM tracks WHERE artist LIKE ? ORDER BY title", (f'%{artist_name}%',))
    tracks = cursor.fetchall()
    conn.close()
    
    if tracks:
        await update.message.reply_text(f"🎵 **Morceaux de {artist_name} :**")
        for file_id, title in tracks:
            await context.bot.send_audio(chat_id=update.effective_chat.id, audio=file_id, title=title)
    else:
        await update.message.reply_text(f"Aucun morceau trouvé pour l'artiste '{artist_name}'.")

# --- Point d'entrée principal ---
if __name__ == '__main__':
    # Remplace 'TON_TOKEN_ICI' par le token obtenu via @BotFather
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'TON_TOKEN_ICI')
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("artistes", list_artists))
    app.add_handler(CommandHandler("albums", list_albums))
    app.add_handler(CommandHandler("ecoute", listen_artist))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    
    print("Le bot est en marche...")
    app.run_polling()
