import os
# Suppress TensorFlow oneDNN info logs
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import sys
import asyncio
import logging

# ---------------------------------------------------------------
# PATH SETUP: Allow imports from THIS backend folder
# ---------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# The frontend templates are now hosted locally in the backend for cloud deployment
TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates")
STATIC_DIR    = os.path.join(BACKEND_DIR, "static")

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse
from starlette.responses import JSONResponse
from loguru import logger

# Silence noisy external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

from src.config import settings
from src.scheduler.task_scheduler import start_scheduler

from src.delivery.web_dashboard import router as dashboard_router
from src.delivery.user_retention import router as retention_router
from src.delivery.admin_portal import router as admin_router

# Configure logging
try:
    log_dir = os.path.join("data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(os.path.join(log_dir, "app.log"), rotation="500 MB", level="INFO")
except Exception as e:
    print(f"File logging disabled due to error: {e}")

from src.database.models import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI News Intelligence Agent (Backend)...")
    logger.info(f"Templates Directory: {TEMPLATES_DIR}")
    logger.info(f"Static Directory: {STATIC_DIR}")

    if not settings.OPENAI_API_KEYS:
        logger.warning("MISSING CRITICAL KEYS: OPENAI_API_KEYS.")
    if not settings.GROQ_API_KEYS:
        logger.warning("MISSING CRITICAL KEYS: GROQ_API_KEYS.")
    if not os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") and not os.path.exists("service-account.json"):
        logger.warning("No Firebase credentials found.")

    init_db()
    logger.info("Database initialized.")

    from src.config.firebase_config import initialize_firebase
    initialize_firebase()

    def _background_startup_tasks():
        try:
            from seed_newspapers import seed_newspapers
            seed_newspapers()
        except Exception as e:
            logger.error(f"Newspaper seeding failed: {e}")

        try:
            from src.utils.fix_data import fix_data
            fix_data()
        except Exception as e:
            logger.error(f"Data fix failed: {e}")

        try:
            from src.database.models import SessionLocal, VerifiedNews, SystemConfig
            db_cfg = SessionLocal()
            if db_cfg.query(SystemConfig).count() == 0:
                logger.info("Initializing SystemConfig defaults...")
                defaults = [
                    SystemConfig(config_key="show_scholarships", config_value="true"),
                    SystemConfig(config_key="show_exams", config_value="true"),
                    SystemConfig(config_key="show_admissions", config_value="true"),
                    SystemConfig(config_key="show_career", config_value="true"),
                    SystemConfig(config_key="maintenance_mode", config_value="false"),
                    SystemConfig(config_key="app_version", config_value="1.0.0"),
                ]
                db_cfg.add_all(defaults)
                db_cfg.commit()
            db_cfg.close()
        except Exception as e:
            logger.error(f"SystemConfig seeding failed: {e}")

        db_news = SessionLocal()
        try:
            if db_news.query(VerifiedNews).count() == 0:
                logger.info("Cold Start Detected: Triggering immediate background news cycle...")
                from src.scheduler.task_scheduler import run_news_cycle
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_news_cycle())
                loop.close()
            else:
                logger.info("Database has data. Waiting for scheduled cycle.")
        except Exception as e:
            logger.error(f"Failed to auto-trigger news cycle: {e}")
        finally:
            db_news.close()

    import threading
    threading.Thread(target=_background_startup_tasks, daemon=True).start()

    scheduler = start_scheduler()
    logger.info("Scheduler started.")

    yield

    logger.info("Shutting down...")
    if scheduler:
        scheduler.shutdown()


app = FastAPI(title="AI News Intelligence Agent - Backend", lifespan=lifespan)

# --- CORS: Allow the frontend to connect ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files from the frontend folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------------------------------------------------------------
# IMPORTANT: Patch the template directory used by web_dashboard.py
# This must happen BEFORE including the routers
# ---------------------------------------------------------------
import src.delivery.web_dashboard as _wd
_wd.templates = Jinja2Templates(directory=TEMPLATES_DIR)
import src.delivery.admin_portal as _ap
_ap.templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include Routers
app.include_router(retention_router)
app.include_router(dashboard_router)
app.include_router(admin_router)


@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    skip_paths = ["/api/admin", "/admin", "/static", "/health", "/favicon.ico"]
    if any(request.url.path.startswith(path) for path in skip_paths):
        return await call_next(request)
    try:
        from src.database.models import SessionLocal, SystemConfig
        db = SessionLocal()
        mode = db.query(SystemConfig).filter(SystemConfig.config_key == "maintenance_mode").first()
        is_maintenance = mode and mode.config_value.lower() == "true"
        db.close()
        if is_maintenance:
            return HTMLResponse(content="""
                <!DOCTYPE html><html><head><title>Maintenance</title></head>
                <body style="background:#020617;color:white;font-family:sans-serif;text-align:center;padding:4rem;">
                <h1>Neural Maintenance</h1>
                <p>We'll be back online within minutes.</p></body></html>
            """, status_code=503)
    except Exception as e:
        logger.error(f"Maintenance check failed: {e}")
    return await call_next(request)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(STATIC_DIR, "favicon.png"))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "mode": "separated-backend"}


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "run-once":
            logger.info("Running manual news cycle...")
            from src.scheduler.task_scheduler import run_news_cycle
            asyncio.run(run_news_cycle())
        elif command == "init-db":
            from src.utils.init_db import init_db
            init_db()
        else:
            logger.error(f"Unknown command: {command}")
    else:
        port = int(os.environ.get("PORT", 8000))
        logger.info(f"Launching backend server on port {port}...")
        uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
