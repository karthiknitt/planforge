from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base


class ConsumedPayment(Base):
    """One row per Razorpay payment_id that has already granted its benefit.

    The primary-key constraint is the idempotency guard: replaying a captured
    verify request cannot grant a plan or credits twice.
    """

    __tablename__ = "consumed_payments"

    payment_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
