import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db import get_db
from app.models.user import User

router = APIRouter()

PLAN_AMOUNTS = {"basic": 49900, "pro": 99900, "firm": 299900}  # paise

CREDIT_PACKS: dict[str, dict[str, int]] = {
    "pack_1": {"credits": 1, "price_paise": 9900},
    "pack_3": {"credits": 3, "price_paise": 24900},
    "pack_7": {"credits": 7, "price_paise": 49900},
}


def _get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


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


@router.post("/payments/order")
async def create_order(
    body: OrderRequest,
    user_id: str = Depends(_get_user_id),
) -> dict:
    if body.plan not in PLAN_AMOUNTS:
        raise HTTPException(400, "Invalid plan. Choose 'basic', 'pro', or 'firm'.")

    if not settings.razorpay_key_id or settings.razorpay_key_id == "rzp_test_PLACEHOLDER":
        raise HTTPException(503, "Payment gateway not configured. Add Razorpay keys to backend/.env.")

    try:
        import razorpay
    except ImportError:
        raise HTTPException(503, "razorpay package not installed. Run: uv add razorpay")

    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    order = client.order.create({
        "amount": PLAN_AMOUNTS[body.plan],
        "currency": "INR",
        "notes": {"plan": body.plan, "user_id": user_id},
    })
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "key_id": settings.razorpay_key_id,
    }


@router.post("/payments/verify")
async def verify_payment(
    body: VerifyRequest,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.plan not in PLAN_AMOUNTS:
        raise HTTPException(400, "Invalid plan. Choose 'basic', 'pro', or 'firm'.")

    # Verify Razorpay signature
    msg = f"{body.order_id}|{body.payment_id}".encode()
    expected = hmac.new(
        settings.razorpay_key_secret.encode(), msg, hashlib.sha256
    ).hexdigest()
    if expected != body.signature:
        raise HTTPException(400, "Invalid payment signature.")

    # Activate plan
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        # Insert a minimal row so we can track plan tier
        user = User(id=user_id)
        db.add(user)

    user.plan_tier = body.plan
    user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    await db.commit()

    return {"status": "activated", "plan": body.plan}


@router.post("/payments/credits/order")
async def create_credits_order(
    body: CreditOrderRequest,
    user_id: str = Depends(_get_user_id),
) -> dict:
    if body.pack_id not in CREDIT_PACKS:
        raise HTTPException(400, f"Invalid pack_id. Choose one of: {', '.join(CREDIT_PACKS)}")

    if not settings.razorpay_key_id or settings.razorpay_key_id == "rzp_test_PLACEHOLDER":
        raise HTTPException(503, "Payment gateway not configured. Add Razorpay keys to backend/.env.")

    try:
        import razorpay
    except ImportError:
        raise HTTPException(503, "razorpay package not installed. Run: uv add razorpay")

    pack = CREDIT_PACKS[body.pack_id]
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    order = client.order.create({
        "amount": pack["price_paise"],
        "currency": "INR",
        "notes": {"pack_id": body.pack_id, "credits": pack["credits"], "user_id": user_id},
    })
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "key_id": settings.razorpay_key_id,
        "credits": pack["credits"],
    }


@router.post("/payments/credits/verify")
async def verify_credits_payment(
    body: CreditVerifyRequest,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.pack_id not in CREDIT_PACKS:
        raise HTTPException(400, "Invalid pack_id.")

    # Verify Razorpay signature
    msg = f"{body.order_id}|{body.payment_id}".encode()
    expected = hmac.new(
        settings.razorpay_key_secret.encode(), msg, hashlib.sha256
    ).hexdigest()
    if expected != body.signature:
        raise HTTPException(400, "Invalid payment signature.")

    pack = CREDIT_PACKS[body.pack_id]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id)
        db.add(user)

    user.project_credits = (user.project_credits or 0) + pack["credits"]
    await db.commit()

    return {
        "status": "credits_added",
        "pack_id": body.pack_id,
        "credits_added": pack["credits"],
        "total_credits": user.project_credits,
    }
