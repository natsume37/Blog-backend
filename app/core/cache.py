import redis
from typing import Optional, Any
import json
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    """Singleton Redis Client Wrapper"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True  # Automatically decode bytes to strings
            )
        return cls._instance

    def get_client(self) -> redis.Redis:
        return self.client

    def get(self, key: str) -> Any:
        try:
            value = self.client.get(key)
            if value is None:
                return None
            # Try parsing JSON, but be tolerant: if it's plain string, return as-is
            try:
                return json.loads(value)
            except Exception:
                return value
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        try:
            # Use a safe JSON serializer to handle datetime and other non-serializable types
            def _default_serializer(obj):
                # datetime/date/time -> Human readable format
                try:
                    from datetime import datetime, date, time
                    if isinstance(obj, datetime):
                        return obj.strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(obj, date):
                        return obj.strftime("%Y-%m-%d")
                    if isinstance(obj, time):
                        return obj.strftime("%H:%M:%S")
                except Exception:
                    pass
                # Fallback to string representation
                return str(obj)

            payload = json.dumps(value, default=_default_serializer, ensure_ascii=False)
            self.client.set(key, payload, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
            
    def incr(self, key: str) -> int:
        try:
            return self.client.incr(key)
        except Exception as e:
            logger.error(f"Redis incr error: {e}")
            return 0

redis_client = RedisClient()
