
import asyncio
import logging
from src.database.models import SessionLocal
from src.digest.generator import DigestGenerator

logging.basicConfig(level=logging.INFO)

async def main():
    db = SessionLocal()
    generator = DigestGenerator()
    print("Re-generating daily digest with new category mapping...")
    await generator.create_daily_digest(db)
    print("Digest generation complete.")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
