import sqlite3
import os
from pathlib import Path

def migrate():
    # Detect DB path
    db_path = "data/news.db"
    if not os.path.exists(db_path):
        db_path = "ai-news-agent/data/news.db"
    
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}. Skipping migration.")
        return

    print(f"Migrating DB at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add translation_cache column
    try:
        cursor.execute("ALTER TABLE verified_news ADD COLUMN translation_cache JSON DEFAULT '{}'")
        print("✅ Added translation_cache column.")
    except sqlite3.OperationalError:
        print("ℹ️ translation_cache column already exists.")

    # Add audio_url column
    try:
        cursor.execute("ALTER TABLE verified_news ADD COLUMN audio_url VARCHAR")
        print("✅ Added audio_url column.")
    except sqlite3.OperationalError:
        print("ℹ️ audio_url column already exists.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
