from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uvicorn

app = FastAPI()

# Autoriser le site web à communiquer avec l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/tracks")
def get_tracks():
    conn = sqlite3.connect('music_index.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, artist, title, album, file_id FROM tracks")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "artist": r[1], "title": r[2], "album": r[3], "file_id": r[4]} for r in rows]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
