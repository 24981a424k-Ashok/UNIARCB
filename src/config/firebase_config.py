import os
import json
import threading
import firebase_admin
from firebase_admin import credentials, messaging, auth
from loguru import logger

_firebase_app = None
_init_lock = threading.Lock()

def initialize_firebase():
    """
    Revised Multi-Layer Firebase initialization.
    Order: 1. Service Account JSON (ENV) -> 2. Stable File -> 3. Individual ENV Keys -> 4. Default Credentials.
    """
    global _firebase_app
    with _init_lock:
        if _firebase_app:
            return _firebase_app

        try:
            # 1. Existing App Check
            try:
                _firebase_app = firebase_admin.get_app()
                return _firebase_app
            except ValueError:
                pass

            # 2. PRIORITY: JSON String from ENV (Common in Cloud/Railway)
            service_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            if service_json:
                try:
                    # Strip exterior quotes if accidentally included
                    service_json = service_json.strip()
                    if service_json.startswith('"') and service_json.endswith('"'):
                        service_json = service_json[1:-1]
                    
                    # Fix escaped newlines in the JSON string itself
                    service_json = service_json.replace('\\n', '\n')
                    
                    cred_dict = json.loads(service_json)
                    cred = credentials.Certificate(cred_dict)
                    _firebase_app = firebase_admin.initialize_app(cred)
                    logger.info("Firebase initialized via JSON String in ENV.")
                    return _firebase_app
                except Exception as e:
                    logger.warning(f"JSON String init failed: {e}")

            # 3. SECONDARY: Stable File
            cert_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "service-account.json")
            if os.path.exists(cert_path):
                try:
                    cred = credentials.Certificate(cert_path)
                    _firebase_app = firebase_admin.initialize_app(cred)
                    logger.info(f"Firebase initialized via File: {cert_path}")
                    return _firebase_app
                except Exception as e:
                    logger.warning(f"File init failed: {e}")

            # 4. TERTIARY: Individual ENV Keys
            private_key = os.getenv("FIREBASE_PRIVATE_KEY")
            if private_key:
                try:
                    # Robust Key Cleaning (handles literal \n, quotes, and whitespace)
                    pk = private_key.strip()
                    if pk.startswith('"') and pk.endswith('"'):
                        pk = pk[1:-1]
                    pk = pk.replace('\\n', '\n')
                    
                    # Ensure it has the correct BEGIN/END markers
                    if "BEGIN PRIVATE KEY" not in pk:
                         pk = f"-----BEGIN PRIVATE KEY-----\n{pk}\n-----END PRIVATE KEY-----\n"

                    config = {
                        "type": "service_account",
                        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                        "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                        "private_key": pk,
                        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                        "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
                    }
                    
                    cred = credentials.Certificate(config)
                    _firebase_app = firebase_admin.initialize_app(cred)
                    logger.info("Firebase initialized via Individual ENV Keys.")
                    return _firebase_app
                except Exception as e:
                    logger.warning(f"Individual Key init failed: {e}")

            # 5. FINAL FALLBACK: Native ADC (Railway/Cloud Default)
            try:
                _firebase_app = firebase_admin.initialize_app()
                logger.info("Firebase initialized via Default Credentials.")
                return _firebase_app
            except Exception as e:
                logger.error(f"Default Credentials fallback failed: {e}")

        except Exception as e:
            logger.error(f"CRITICAL: Firebase initialization sequence failed: {e}")
            return None
            
        except Exception as e:
            logger.error(f"CRITICAL: All Firebase init paths failed: {e}")
            return None

def verify_token(id_token: str):
    """
    Verify a Firebase ID token.
    Includes a robust retry mechanism for clock skew (Token used too early).
    """
    import time
    for attempt in range(4): # Increased to 4 attempts
        try:
            # Ensure initialized
            initialize_firebase()
            project_id = os.getenv("FIREBASE_PROJECT_ID")
            if project_id and not os.environ.get("GOOGLE_CLOUD_PROJECT"):
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                os.environ["FIREBASE_PROJECT_ID"] = project_id

            # Verify with the app instance
            # Perfection: Add 5 seconds of clock skew tolerance to prevent "Token used too early" warnings
            return auth.verify_id_token(id_token, app=_firebase_app, clock_skew_seconds=5)
        except Exception as e:
            err_msg = str(e)
            if "Token used too early" in err_msg:
                # Optimized for systems with slight clock skew
                wait_time = 2.0 + (attempt * 2) # Slightly more aggressive wait
                logger.warning(f"Clock skew detected ({err_msg}). Retrying in {wait_time}s... (Attempt {attempt+1}/4)")
                time.sleep(wait_time)
                continue

            
            logger.error(f"Token verification failed: {e}")
            return None
    
    return None


def get_messaging():
    return messaging

def get_auth():
    return auth
