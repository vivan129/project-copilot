"""
Stripe subscription endpoints:
  POST /subscriptions/checkout      → create Stripe Checkout session
  POST /subscriptions/portal        → customer billing portal
  POST /subscriptions/webhook       → Stripe webhook handler
  GET  /subscriptions/status        → current user's tier + usage
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.core.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.project import UsageLog

logger = logging.getLogger(__name__)
router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY

TIER_PRICE_MAP = {
    settings.STRIPE_PRO_PRICE_ID:    "pro",
    settings.STRIPE_EXPERT_PRICE_ID: "expert",
    settings.STRIPE_SCHOOL_PRICE_ID: "school",
}

TIER_LIMITS = {"free": 2, "pro": 20, "expert": 999999, "school": 999999}


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str = ""
    cancel_url: str  = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/checkout")
async def create_checkout(
    req: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout session and return the URL."""
    if req.price_id not in TIER_PRICE_MAP:
        raise HTTPException(400, "Invalid price ID")

    frontend = settings.FRONTEND_URL.rstrip("/")
    success_url = req.success_url or f"{frontend}/dashboard?upgraded=1"
    cancel_url  = req.cancel_url  or f"{frontend}/pricing"

    try:
        # Get or create Stripe customer
        customer_id = current_user.stripe_customer_id
        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=current_user.name or current_user.email,
                metadata={"user_id": str(current_user.id)},
            )
            customer_id = customer.id
            current_user.stripe_customer_id = customer_id
            await db.commit()

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": req.price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"user_id": str(current_user.id), "price_id": req.price_id},
            allow_promotion_codes=True,
        )
        return {"url": session.url, "session_id": session.id}

    except stripe.StripeError as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(502, f"Stripe error: {e.user_message or str(e)}")


@router.post("/portal")
async def customer_portal(
    current_user: User = Depends(get_current_user),
):
    """Redirect to Stripe customer portal to manage subscription."""
    if not current_user.stripe_customer_id:
        raise HTTPException(400, "No active subscription found")

    frontend = settings.FRONTEND_URL.rstrip("/")
    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{frontend}/dashboard",
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        raise HTTPException(502, str(e))


@router.get("/status")
async def subscription_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current tier, usage this month, and limit."""
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count(UsageLog.id))
        .where(UsageLog.user_id == current_user.id)
        .where(UsageLog.action == "generate")
        .where(UsageLog.created_at >= month_start)
    )
    used  = result.scalar_one()
    tier  = current_user.subscription_tier
    limit = TIER_LIMITS.get(tier, 2)

    return {
        "tier":       tier,
        "used":       used,
        "limit":      limit,
        "unlimited":  limit >= 999999,
        "remaining":  max(0, limit - used) if limit < 999999 else 999999,
        "resets_at":  (month_start + timedelta(days=32)).replace(day=1).isoformat(),
        "stripe_customer_id": current_user.stripe_customer_id,
        "subscription_expires_at": (
            current_user.subscription_expires_at.isoformat()
            if current_user.subscription_expires_at else None
        ),
    }


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events — upgrades/downgrades users automatically."""
    body = await request.body()

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(500, "Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature")
    except Exception as e:
        raise HTTPException(400, f"Webhook parse error: {e}")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook: %s", event_type)

    # ── Checkout completed → upgrade user ────────────────────────────────────
    if event_type == "checkout.session.completed":
        user_id  = data.get("metadata", {}).get("user_id")
        price_id = data.get("metadata", {}).get("price_id")
        new_tier = TIER_PRICE_MAP.get(price_id)

        if user_id and new_tier:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.subscription_tier = new_tier
                user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=32)
                if data.get("customer"):
                    user.stripe_customer_id = data["customer"]
                await db.commit()
                logger.info("Upgraded user %s → %s", user.email, new_tier)

    # ── Subscription deleted → downgrade to free ─────────────────────────────
    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            result = await db.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.subscription_tier = "free"
                user.subscription_expires_at = None
                await db.commit()
                logger.info("Downgraded user %s → free (subscription cancelled)", user.email)

    # ── Payment failed → warn (keep tier for grace period) ───────────────────
    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        logger.warning("Payment failed for customer %s", customer_id)
        # Grace period: keep tier, Stripe will retry. After 3 failures
        # Stripe fires subscription.deleted which downgrades them.

    return JSONResponse({"received": True})
