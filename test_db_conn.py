import os
import sqlalchemy
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[ERROR] DATABASE_URL not set in .env")
    exit(1)

try:
    print(f"Testing connection...")
    engine = sqlalchemy.create_engine(db_url, connect_args={'connect_timeout': 5})
    conn = engine.connect()
    conn.close()
    print("[SUCCESS] Database connection works!")
except Exception as e:
    print(f"[FAILED] {e}")
