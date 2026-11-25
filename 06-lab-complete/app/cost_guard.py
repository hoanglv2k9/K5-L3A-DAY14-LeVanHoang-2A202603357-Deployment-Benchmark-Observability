"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent")

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_keys() -> tuple[str, str]:
    now_utc = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now_utc.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now_utc.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Verify total LLM spend in Redis is under daily and monthly budgets before calling LLM."""
    if r is None:
        logger.warning("Redis unavailable; skipping budget check", extra={"event": "budget_check_skip"})
        return

    daily_key, monthly_key = _budget_keys()
    try:
        daily_raw, monthly_raw = r.mget(daily_key, monthly_key)
        daily_spend = float(daily_raw or 0.0)
        monthly_spend = float(monthly_raw or 0.0)
    except Exception as exc:
        logger.warning(f"Redis error reading LLM spend: {exc}", extra={"event": "budget_redis_error"})
        return

    if daily_spend >= settings.daily_budget_usd or monthly_spend >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="LLM budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Compute request cost from token counts and accumulate totals atomically in Redis."""
    cost_usd = (
        (max(0, input_tokens) / 1000.0) * PRICE_INPUT_PER_1K
        + (max(0, output_tokens) / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is None:
        return cost_usd

    daily_key, monthly_key = _budget_keys()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost_usd)
        pipe.expire(daily_key, 86400 * 2)
        pipe.incrbyfloat(monthly_key, cost_usd)
        pipe.expire(monthly_key, 86400 * 35)
        pipe.execute()
    except Exception as exc:
        logger.warning(f"Redis error recording LLM spend: {exc}", extra={"event": "cost_record_redis_error"})
    return cost_usd
