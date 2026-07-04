from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.models.payment import ConsumedPayment
from app.models.user import User
from app.services import razorpay_gateway as gateway

router = APIRouter()

PLAN_AMOUNTS = {"basic": 49900, "pro": 99900, "firm": 299900}  # paise

CREDIT_PACKS: dict[str, dict[str, int]] = {
    "pack_1": {"credits": 1, "price_paise": 9900},
    "pack_3": {"credits": 3, "price_paise": 24900},
    "pack_7": {"credits": 7, "price_paise": 49900},
}

PLAN_DURATION_DAYS = 30


class OrderRequest(BaseModel):
    plan: str


class VerifyRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str
    plan: str


class CreditOrderRequest(BaseModel):
    pack_id: str


class CreditVerifyRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str
    pack_id: str


def _validate_paid_order(
    body_order_id: str,
    expected_amount: int,
    expected_notes: dict[str, str],
) -> None:
    """Bind the verify request to what the order was actually created for.

    The Razorpay signature covers only order_id|payment_id — without this
    check a client can pay for the cheapest plan and claim the priciest.
    """
    order = gateway.fetch_order(body_order_id)
    if order.get("amount") != expected_amount:
        raise HTTPException(400, "Order amount does not match the claimed purchase.")
    notes = order.get("notes") or {}
    for key, expected in expected_notes.items():
        if notes.get(key) != expected:
            raise HTTPException(400, "Order was not created for this purchase.")


async def _consume_payment(
    db: AsyncSession, payment_id: str, user_id: str, purpose: str
) -> bool:
    """Record the payment as processed. Returns False if already consumed."""
    existing = await db.get(ConsumedPayment, payment_id)
    if existing is not None:
        return False
    db.add(ConsumedPayment(payment_id=payment_id, user_id=user_id, purpose=purpose))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    return True


@router.post("/payments/order")
async def create_order(
    body: OrderRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    if body.plan not in PLAN_AMOUNTS:
        raise HTTPException(400, "Invalid plan. Choose 'basic', 'pro', or 'firm'.")

    gateway.require_configured()

    try:
        import razorpay
    except ImportError:
        raise HTTPException(503, "razorpay package not installed. Run: uv add razorpay")

    client = razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )
    order = client.order.create(
        {
            "amount": PLAN_AMOUNTS[body.plan],
            "currency": "INR",
            "notes": {"plan": body.plan, "user_id": user_id},
        }
    )
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "key_id": settings.razorpay_key_id,
    }


@router.post("/payments/verify")
async def verify_payment(
    body: VerifyRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.plan not in PLAN_AMOUNTS:
        raise HTTPException(400, "Invalid plan. Choose 'basic', 'pro', or 'firm'.")

    gateway.require_configured()

    if not gateway.verify_signature(body.order_id, body.payment_id, body.signature):
        raise HTTPException(400, "Invalid payment signature.")

    _validate_paid_order(
        body.order_id,
        expected_amount=PLAN_AMOUNTS[body.plan],
        expected_notes={"plan": body.plan, "user_id": user_id},
    )

    if not await _consume_payment(db, body.payment_id, user_id, f"plan:{body.plan}"):
        return {"status": "already_processed", "plan": body.plan}

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id)
        db.add(user)

    now = datetime.now(timezone.utc)
    base = now
    if user.plan_tier == body.plan and user.plan_expires_at is not None:
        current = user.plan_expires_at
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        # Same-plan renewal keeps the remaining days
        if current > now:
            base = current

    user.plan_tier = body.plan
    user.plan_expires_at = base + timedelta(days=PLAN_DURATION_DAYS)
    await db.commit()

    return {"status": "activated", "plan": body.plan}


@router.post("/payments/credits/order")
async def create_credits_order(
    body: CreditOrderRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    if body.pack_id not in CREDIT_PACKS:
        raise HTTPException(
            400, f"Invalid pack_id. Choose one of: {', '.join(CREDIT_PACKS)}"
        )

    gateway.require_configured()

    try:
        import razorpay
    except ImportError:
        raise HTTPException(503, "razorpay package not installed. Run: uv add razorpay")

    pack = CREDIT_PACKS[body.pack_id]
    client = razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )
    order = client.order.create(
        {
            "amount": pack["price_paise"],
            "currency": "INR",
            "notes": {
                "pack_id": body.pack_id,
                "credits": pack["credits"],
                "user_id": user_id,
            },
        }
    )
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "key_id": settings.razorpay_key_id,
        "credits": pack["credits"],
    }


@router.post("/payments/credits/verify")
async def verify_credits_payment(
    body: CreditVerifyRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.pack_id not in CREDIT_PACKS:
        raise HTTPException(400, "Invalid pack_id.")

    gateway.require_configured()

    if not gateway.verify_signature(body.order_id, body.payment_id, body.signature):
        raise HTTPException(400, "Invalid payment signature.")

    pack = CREDIT_PACKS[body.pack_id]
    _validate_paid_order(
        body.order_id,
        expected_amount=pack["price_paise"],
        expected_notes={"pack_id": body.pack_id, "user_id": user_id},
    )

    if not await _consume_payment(
        db, body.payment_id, user_id, f"credits:{body.pack_id}"
    ):
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return {
            "status": "already_processed",
            "pack_id": body.pack_id,
            "total_credits": user.project_credits if user else 0,
        }

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id, project_credits=0)
        db.add(user)
        await db.flush()

    # Atomic increment — no read-modify-write race between concurrent verifies
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            project_credits=func.coalesce(User.project_credits, 0) + pack["credits"]
        )
    )
    await db.commit()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    return {
        "status": "credits_added",
        "pack_id": body.pack_id,
        "credits_added": pack["credits"],
        "total_credits": user.project_credits,
    }
