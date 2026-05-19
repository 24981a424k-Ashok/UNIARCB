import redis
import json
import logging
import asyncio
from typing import Any, Optional
from datetime import datetime, timedelta
from src.config import settings

logger = logging.getLogger(__name__)

class RedisCacheManager:
    def __init__(self):
        self.redis_client = None
        self.is_active = False
        # High-fidelity in-memory cache as backup and local-first store
        self.in_memory_fallback = {}  # key -> {"data": val, "expires_at": datetime}
        self._init_redis()

    def _init_redis(self):
        if not settings.REDIS_URL:
            logger.info("REDIS_URL environment variable is empty. Caching runs in in-memory fallback mode.")
            return

        try:
            # Parse connection URL with robust connection timeout config
            self.redis_client = redis.from_url(
                settings.REDIS_URL, 
                decode_responses=True, 
                socket_connect_timeout=3,
                socket_keepalive=True
            )
            # Test connection
            self.redis_client.ping()
            self.is_active = True
            logger.info("Successfully connected to the remote Redis cache node.")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Degrading gracefully to in-memory fallback caching.")
            self.redis_client = None
            self.is_active = False

    def _run_sync(self, func, *args, **kwargs):
        """Helper to execute synchronous blocking redis calls in a thread pool executor to avoid blocking FastAPI event loop."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def get(self, key: str) -> Optional[Any]:
        """Asynchronously get value from cache with silent graceful fallbacks."""
        # 1. If Redis is inactive, check in-memory cache
        if not self.is_active or not self.redis_client:
            entry = self.in_memory_fallback.get(key)
            if entry:
                if entry["expires_at"] > datetime.utcnow():
                    return entry["data"]
                else:
                    del self.in_memory_fallback[key]
            return None

        # 2. Query Redis via executor
        try:
            val = await self._run_sync(self.redis_client.get, key)
            if val is not None:
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            return None
        except Exception as e:
            logger.error(f"Redis GET failed for key '{key}': {e}. Falling back to local memory.")
            # Fall back to local memory check in case connection dropped
            entry = self.in_memory_fallback.get(key)
            if entry and entry["expires_at"] > datetime.utcnow():
                return entry["data"]
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Asynchronously write to cache with a specified TTL."""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        # Always maintain the in-memory fallback for local consistency
        self.in_memory_fallback[key] = {"data": value, "expires_at": expires_at}

        if not self.is_active or not self.redis_client:
            return True

        try:
            serialized = json.dumps(value, default=str)
            await self._run_sync(self.redis_client.setex, key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis SET failed for key '{key}': {e}. Keeping in local memory.")
            return False

    async def delete(self, key: str) -> bool:
        """Asynchronously invalidate a key from all caching layers."""
        if key in self.in_memory_fallback:
            del self.in_memory_fallback[key]

        if not self.is_active or not self.redis_client:
            return True

        try:
            await self._run_sync(self.redis_client.delete, key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE failed for key '{key}': {e}")
            return False

    async def clear_pattern(self, pattern: str) -> bool:
        """Asynchronously invalidate all keys matching a specific pattern (e.g. 'uniarc:*')."""
        # Clear matching local in-memory keys
        normalized_pattern = pattern.replace("*", "")
        for k in list(self.in_memory_fallback.keys()):
            if normalized_pattern in k:
                del self.in_memory_fallback[k]

        if not self.is_active or not self.redis_client:
            return True

        try:
            keys = await self._run_sync(self.redis_client.keys, pattern)
            if keys:
                # Delete keys concurrently
                await self._run_sync(self.redis_client.delete, *keys)
            return True
        except Exception as e:
            logger.error(f"Redis clear_pattern failed for '{pattern}': {e}")
            return False

# Export a single global instance for application-wide sharing
redis_cache = RedisCacheManager()
