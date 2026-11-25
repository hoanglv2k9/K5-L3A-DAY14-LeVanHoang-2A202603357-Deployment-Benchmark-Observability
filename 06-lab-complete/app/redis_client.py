"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Yêu cầu:
  • Đọc REDIS_URL từ config
  • App vẫn phải KHỞI ĐỘNG ĐƯỢC khi Redis chưa sẵn sàng (đừng ping Redis lúc import)
  • redis_healthy() dùng cho GET /ready: Redis không kết nối được → False
"""

import redis

from app.config import settings


def _create_client():
    """Create a Redis client without blocking or failing at module import time."""
    if not settings.redis_url:
        return None
    try:
        return redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    except Exception:
        return None


r = _create_client()


def redis_healthy() -> bool:
    """Return True if Redis responds to PING, False otherwise."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
