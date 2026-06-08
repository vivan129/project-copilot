from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.project import UsageLog
from app.models.user import User

# How many generations per month per tier
TIER_LIMITS = {
    "free":   3,
    "pro":    20,
    "expert": 999999,  # unlimited
    "school": 999999,
}


async def check_usage_limit(user: User, action: str, db: AsyncSession) -> None:
    """Raises 429 if user has exceeded their monthly limit for the action."""
    limit = TIER_LIMITS.get(user.subscription_tier, 3)
    if limit >= 999999:
        return  # unlimited tier, skip check

    # Count actions this calendar month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(UsageLog.id))
        .where(UsageLog.user_id == user.id)
        .where(UsageLog.action == action)
        .where(UsageLog.created_at >= month_start)
    )
    count = result.scalar_one()

    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": f"You've used {count}/{limit} generations this month.",
                "upgrade_url": "/pricing",
                "current_tier": user.subscription_tier,
            },
        )


async def log_usage(user: User, action: str, db: AsyncSession, tokens: int = 0, cost: float = 0.0) -> None:
    """Log an action for usage tracking."""
    log = UsageLog(
        user_id=user.id,
        action=action,
        tokens_used=tokens,
        cost_usd=cost,
    )
    db.add(log)
    await db.commit()
