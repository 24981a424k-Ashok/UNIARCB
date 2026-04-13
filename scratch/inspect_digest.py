
from src.database.models import SessionLocal, DailyDigest
import json

db = SessionLocal()
latest = db.query(DailyDigest).order_by(DailyDigest.date.desc()).first()
if latest:
    print(f"Digest ID: {latest.id}, Date: {latest.date}")
    content = latest.content_json
    print("Categories present in content['categories']:")
    if "categories" in content:
        for cat, stories in content["categories"].items():
            print(f"- {cat}: {len(stories)} stories")
    else:
        print("No 'categories' key in content_json")
    
    print("\nKeys in content_json:")
    print(list(content.keys()))
else:
    print("No DailyDigest found in DB")
db.close()
