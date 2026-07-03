"""Regression tests for Razorpay verification hardening.

Previous bugs:
- verify trusted body.plan / body.pack_id — the signature covers only
  order_id|payment_id, so paying for 'basic' and verifying with plan='firm'
  granted firm tier for Rs.499.
- No idempotency: replaying one valid verify request granted credits again
  and again.
- verify ran even with an unconfigured gateway (empty secret) — HMAC with an
  empty key is computable by anyone.
- Renewal overwrote plan_expires_at with now+30d, losing remaining days.
"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest

import app.services.razorpay_gateway as gateway
from app.config.settings import settings
from app.models.user import User

TEST_KEY_ID = "rzp_test_realkey"
TEST_SECRET = "rzp_secret_for_tests"

PLAN_NOTES_USER = "payer-1"


def _sig(order_id: str, payment_id: str, secret: str = TEST_SECRET) -> str:
    return hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


@pytest.fixture
def configured_gateway(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", TEST_KEY_ID)
    monkeypatch.setattr(settings, "razorpay_key_secret", TEST_SECRET)


def _order(amount: int, notes: dict) -> dict:
    return {"id": "order_x1", "amount": amount, "currency": "INR", "notes": notes}


def _mock_order(monkeypatch, amount: int, notes: dict) -> None:
    monkeypatch.setattr(gateway, "fetch_order", lambda order_id: _order(amount, notes))


HDRS = {"X-Test-User-Id": PLAN_NOTES_USER}


async def test_verify_rejects_unconfigured_gateway(client_db, monkeypatch):
    client, _ = client_db
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")
    res = await client.post(
        "/api/payments/verify",
        json={
            "order_id": "order_x1",
            "payment_id": "pay_1",
            "signature": _sig("order_x1", "pay_1", ""),
            "plan": "pro",
        },
        headers=HDRS,
    )
    assert res.status_code == 503


async def test_verify_rejects_plan_mismatched_with_order(
    client_db, monkeypatch, configured_gateway
):
    """Order was created (and paid) for basic — verifying with plan='firm' must fail."""
    client, _ = client_db
    _mock_order(monkeypatch, 49900, {"plan": "basic", "user_id": PLAN_NOTES_USER})
    res = await client.post(
        "/api/payments/verify",
        json={
            "order_id": "order_x1",
            "payment_id": "pay_1",
            "signature": _sig("order_x1", "pay_1"),
            "plan": "firm",
        },
        headers=HDRS,
    )
    assert res.status_code == 400


async def test_verify_rejects_other_users_order(
    client_db, monkeypatch, configured_gateway
):
    client, _ = client_db
    _mock_order(monkeypatch, 99900, {"plan": "pro", "user_id": "someone-else"})
    res = await client.post(
        "/api/payments/verify",
        json={
            "order_id": "order_x1",
            "payment_id": "pay_1",
            "signature": _sig("order_x1", "pay_1"),
            "plan": "pro",
        },
        headers=HDRS,
    )
    assert res.status_code == 400


async def test_verify_activates_matching_plan(
    client_db, monkeypatch, configured_gateway
):
    client, sf = client_db
    _mock_order(monkeypatch, 99900, {"plan": "pro", "user_id": PLAN_NOTES_USER})
    res = await client.post(
        "/api/payments/verify",
        json={
            "order_id": "order_x1",
            "payment_id": "pay_1",
            "signature": _sig("order_x1", "pay_1"),
            "plan": "pro",
        },
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "activated"
    async with sf() as session:
        user = await session.get(User, PLAN_NOTES_USER)
        assert user.plan_tier == "pro"
        assert user.plan_expires_at is not None


async def test_verify_replay_does_not_reactivate(
    client_db, monkeypatch, configured_gateway
):
    client, sf = client_db
    _mock_order(monkeypatch, 99900, {"plan": "pro", "user_id": PLAN_NOTES_USER})
    body = {
        "order_id": "order_x1",
        "payment_id": "pay_1",
        "signature": _sig("order_x1", "pay_1"),
        "plan": "pro",
    }
    first = await client.post("/api/payments/verify", json=body, headers=HDRS)
    assert first.json()["status"] == "activated"
    async with sf() as session:
        expiry_after_first = (await session.get(User, PLAN_NOTES_USER)).plan_expires_at

    replay = await client.post("/api/payments/verify", json=body, headers=HDRS)
    assert replay.status_code == 200
    assert replay.json()["status"] == "already_processed"
    async with sf() as session:
        assert (
            await session.get(User, PLAN_NOTES_USER)
        ).plan_expires_at == expiry_after_first


async def test_renewal_extends_from_current_expiry(
    client_db, monkeypatch, configured_gateway
):
    """Renewing 10 days before expiry must not throw away the remaining days."""
    client, sf = client_db
    remaining = datetime.now(timezone.utc) + timedelta(days=10)
    async with sf() as session:
        session.add(
            User(id=PLAN_NOTES_USER, plan_tier="pro", plan_expires_at=remaining)
        )
        await session.commit()

    _mock_order(monkeypatch, 99900, {"plan": "pro", "user_id": PLAN_NOTES_USER})
    res = await client.post(
        "/api/payments/verify",
        json={
            "order_id": "order_x1",
            "payment_id": "pay_renew",
            "signature": _sig("order_x1", "pay_renew"),
            "plan": "pro",
        },
        headers=HDRS,
    )
    assert res.status_code == 200
    async with sf() as session:
        expiry = (await session.get(User, PLAN_NOTES_USER)).plan_expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        # ~40 days out: 10 remaining + 30 purchased
        assert expiry > datetime.now(timezone.utc) + timedelta(days=38)


async def test_credits_verify_rejects_pack_mismatch(
    client_db, monkeypatch, configured_gateway
):
    client, _ = client_db
    _mock_order(
        monkeypatch,
        9900,
        {"pack_id": "pack_1", "credits": 1, "user_id": PLAN_NOTES_USER},
    )
    res = await client.post(
        "/api/payments/credits/verify",
        json={
            "order_id": "order_x1",
            "payment_id": "pay_c1",
            "signature": _sig("order_x1", "pay_c1"),
            "pack_id": "pack_7",
        },
        headers=HDRS,
    )
    assert res.status_code == 400


async def test_credits_replay_does_not_double_grant(
    client_db, monkeypatch, configured_gateway
):
    client, sf = client_db
    _mock_order(
        monkeypatch,
        24900,
        {"pack_id": "pack_3", "credits": 3, "user_id": PLAN_NOTES_USER},
    )
    body = {
        "order_id": "order_x1",
        "payment_id": "pay_c2",
        "signature": _sig("order_x1", "pay_c2"),
        "pack_id": "pack_3",
    }
    first = await client.post("/api/payments/credits/verify", json=body, headers=HDRS)
    assert first.status_code == 200, first.text
    replay = await client.post("/api/payments/credits/verify", json=body, headers=HDRS)
    assert replay.status_code == 200
    assert replay.json()["status"] == "already_processed"
    async with sf() as session:
        user = await session.get(User, PLAN_NOTES_USER)
        assert user.project_credits == 3
