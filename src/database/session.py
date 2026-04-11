from sqlalchemy.orm import Session
from src.database.models import SessionLocal

def get_db():
    """
    Dependency to get a database session.
    Used by FastAPI routes for automated cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
