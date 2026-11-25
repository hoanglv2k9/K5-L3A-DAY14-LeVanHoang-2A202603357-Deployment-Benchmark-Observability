"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""


import hashlib
import logging
import time
import uuid

from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent")
WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Enforce a 60-second sliding-window rate limit in Redis for the given API key."""
    limit = max(1, settings.rate_limit_per_minute)
    if r is None:
        logger.warning("Redis unavailable; skipping distributed rate limit check", extra={"event": "rate_limit_skip"})
        return

    now = time.time()
    window_start = now - WINDOW_SECONDS
    key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    redis_key = f"rate_limit:{key_digest}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if int(current_count) >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                oldest_ts = float(oldest[0][1])
                retry_after = max(1, min(WINDOW_SECONDS, int(WINDOW_SECONDS - (now - oldest_ts)) + 1))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({limit} requests per {WINDOW_SECONDS}s)",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            f"Redis error in rate limiter: {exc}",
            extra={"event": "rate_limit_redis_error"},
        )
