import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from src.database.models import SessionLocal, VerifiedNews, Advertisement, Newspaper, ProtocolHistory, SystemConfig
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])
from src.database.session import get_db, SessionLocal
from src.config.settings import ADMIN_EMAIL, ADMIN_PASSWORD
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, BackgroundTasks
import os

# Setup templates
templates = Jinja2Templates(directory="web/templates")

# --- Admin token from environment (NEVER hardcode in source) ---
_ADMIN_TOKEN = os.getenv("ADMIN_JWT_SECRET", os.getenv("ADMIN_SECRET_TOKEN"))
if not _ADMIN_TOKEN:
    import secrets
    _ADMIN_TOKEN = secrets.token_hex(32)
    logger.warning("ADMIN_JWT_SECRET not in env! Generated a random token for this session. Set it in .env for persistence.")

# --- Pydantic Schemas ---
class LoginRequest(BaseModel):
    email: str
    password: str

# --- Authentication ---
# --- Authentication Middleware ---
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
security = HTTPBearer()

async def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # FIXED: Token read from environment, not hardcoded in source
    if not _ADMIN_TOKEN or credentials.credentials != _ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Neural Access Denied: Unauthorized")
    return True

@router.post("/login")
async def admin_login(payload: LoginRequest, db: Session = Depends(get_db)):
    # FIXED: Compare against env-var credentials, no hardcoded fallbacks
    if payload.email == ADMIN_EMAIL and payload.password == ADMIN_PASSWORD:
        log_protocol_action(db, 'auth_success', 'admin', None, f"Admin Login: {payload.email}")
        return {
            "status": "success",
            "token": _ADMIN_TOKEN,  # Read from env, not hardcoded
            "role": "admin"
        }
    
    raise HTTPException(status_code=401, detail="Neural Access Denied: Invalid Credentials")

# --- UI Route ---
@router.get("/dashboard", response_class=HTMLResponse)
async def serve_admin_dashboard(request: Request):
    """Serve the enhanced admin dashboard UI."""
    return templates.TemplateResponse("admin_dashboard_enhanced.html", {"request": request})

# --- Analytics & Stats ---
@router.get("/stats")
async def get_admin_stats(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    """Retrieve high-level system analytics for Play Store launch."""
    from src.database.models import User, VerifiedNews, RawNews, DailyDigest
    from datetime import datetime, timedelta
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    return {
        "status": "success",
        "counts": {
            "users": db.query(User).count(),
            "verified_articles": db.query(VerifiedNews).count(),
            "raw_collected": db.query(RawNews).count(),
            "digests": db.query(DailyDigest).count()
        },
        "engagement": {
            "active_today": db.query(User).filter(User.last_active_date >= today).count(),
            "premium_users": db.query(User).filter(User.subscription_status != "free").count()
        },
        "system": {
            "cycle_status": "Healthy",
            "db_engine": "Neural Edge (SQLite)",
            "uptime_nodes": 12
        }
    }


# --- Audit Helper ---
def log_protocol_action(db: Session, action: str, target: str, target_id: str = None, details: str = None):
    try:
        new_log = ProtocolHistory(
            action=action,
            target_type=target,
            target_id=target_id,
            admin_user="Ashok Reddy", # Superuser
            details=details
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        logger.error(f"Audit Log Failed: {e}")

# --- Pydantic Schemas ---
class AdCreate(BaseModel):
    image_url: str
    caption: Optional[str] = None
    position: str = "mobile"
    target_node: str = "Global"
    target_url: Optional[str] = None
    target_platform: str = "both"

class ArticleCreate(BaseModel):
    title: str
    content: str
    category: str
    sub_category: Optional[str] = None
    country: str = "Global"
    impact_score: int = 5

# --- Article CRUD ---
@router.get("/articles")
async def get_admin_articles(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    articles = db.query(VerifiedNews).order_by(VerifiedNews.created_at.desc()).limit(100).all()
    return articles

@router.post("/articles")
async def create_admin_article(article: ArticleCreate, db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    new_art = VerifiedNews(
        title=article.title,
        content=article.content,
        category=article.category,
        sub_category=article.sub_category,
        country=article.country,
        impact_score=article.impact_score,
        summary_bullets=["Verified manual injection"],
        bias_rating="Neutral",
        credibility_score=10.0,
        sentiment="Neutral",
        impact_tags=[],
        why_it_matters="Manual Admin Update",
        published_at=datetime.utcnow()
    )
    db.add(new_art)
    db.commit()
    db.refresh(new_art)
    log_protocol_action(db, 'deploy', 'article', str(new_art.id), f"Manual Article: {article.title}")
    return {"status": "success", "id": new_art.id}

@router.delete("/articles/{article_id}")
async def delete_admin_article(article_id: int, db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    art = db.query(VerifiedNews).filter(VerifiedNews.id == article_id).first()
    if art:
        title = art.title
        db.delete(art)
        db.commit()
        log_protocol_action(db, 'purge', 'article', str(article_id), f"Purged: {title}")
    return {"status": "purged"}

# --- Ad Management (CRUD) ---
@router.get("/ads")
async def get_admin_ads(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    return db.query(Advertisement).order_by(Advertisement.created_at.desc()).all()

@router.post("/ads")
async def create_admin_ad(ad: AdCreate, db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    new_ad = Advertisement(
        image_url=ad.image_url,
        caption=ad.caption,
        position=ad.position,
        target_node=ad.target_node,
        target_url=ad.target_url,
        target_platform=ad.target_platform
    )
    db.add(new_ad)
    db.commit()
    db.refresh(new_ad)
    log_protocol_action(db, 'deploy', 'ad', str(new_ad.id), f"New Campaign Banner: {ad.caption}")
    return {"status": "success", "id": new_ad.id}

@router.delete("/ads/{ad_id}")
async def delete_admin_ad(ad_id: int, db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    ad = db.query(Advertisement).filter(Advertisement.id == ad_id).first()
    if ad:
        db.delete(ad)
        db.commit()
        log_protocol_action(db, 'purge', 'ad', str(ad_id), "Purged campaign banner")
    return {"status": "purged"}

# --- Source Management ---
@router.get("/newspapers")
async def get_admin_sources(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    return db.query(Newspaper).all()

@router.delete("/newspapers/{source_id}")
async def delete_admin_source(source_id: int, db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    source = db.query(Newspaper).filter(Newspaper.id == source_id).first()
    if source:
        db.delete(source)
        db.commit()
        log_protocol_action(db, 'purge', 'source', str(source_id), f"Unregistered source: {source.name}")
    return {"status": "purged"}

# --- System Audit & History ---
@router.post("/refresh-digest")
async def force_intelligence_sync(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    try:
        from src.scheduler.task_scheduler import run_news_cycle
        import threading
        # Run in background to avoid timeout
        def run_sync():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_news_cycle())
                loop.close()
            except Exception as e:
                logger.error(f"Background Sync Failed: {e}")

        threading.Thread(target=run_sync, daemon=True).start()
        log_protocol_action(db, 'sync_trigger', 'intelligence_nodes', None, "Manual Intelligence Refresh Initiated")
        return {"status": "sync_initiated", "message": "Neural nodes are fetching fresh intelligence."}
    except Exception as e:
        logger.error(f"Sync Trigger Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_admin_history(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    return db.query(ProtocolHistory).order_by(ProtocolHistory.timestamp.desc()).limit(100).all()

# --- Config Management ---
@router.get("/config")
async def get_admin_config(db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    configs = db.query(SystemConfig).all()
    return {c.config_key: c.config_value for c in configs}

@router.post("/config")
async def update_admin_config(payload: Dict[str, str], db: Session = Depends(get_db), auth: bool = Depends(verify_admin)):
    for key, value in payload.items():
        cfg = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        if cfg:
            cfg.config_value = value
        else:
            db.add(SystemConfig(config_key=key, config_value=value))
    db.commit()
    log_protocol_action(db, 'config_update', 'system', None, f"Updated System Parameters: {list(payload.keys())}")
    return {"status": "updated"}
