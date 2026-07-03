"""Razorpay gateway helpers — signature verification and order lookup.

Isolated here so routes stay testable (tests monkeypatch fetch_order) and so
signature comparison is timing-safe in exactly one place.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException

from app.config.settings import settings


def is_configured() -> bool:
    return (
        bool(settings.razorpay_key_id)
        and settings.razorpay_key_id != "rzp_test_PLACEHOLDER"
        and bool(settings.razorpay_key_secret)
    )


def require_configured() -> None:
    if not is_configured():
        raise HTTPException(
            503, "Payment gateway not configured. Add Razorpay keys to backend/.env."
        )


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    msg = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(
        settings.razorpay_key_secret.encode(), msg, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_order(order_id: str) -> dict:
    """Fetch the order from Razorpay so verify can bind plan/amount to what
    was actually paid — the payment signature alone covers only
    order_id|payment_id, not the amount or the plan."""
    try:
        import razorpay
    except ImportError as exc:
        raise HTTPException(
            503, "razorpay package not installed. Run: uv add razorpay"
        ) from exc

    client = razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )
    try:
        return client.order.fetch(order_id)
    except Exception as exc:
        raise HTTPException(502, "Could not verify order with Razorpay.") from exc
