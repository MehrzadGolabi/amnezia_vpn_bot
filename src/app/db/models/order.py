import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.models.base import Base, TimestampMixin


class OrderStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_RECEIPT = "awaiting_receipt"
    RECEIPT_SUBMITTED = "receipt_submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVISIONING = "provisioning"
    FULFILLED = "fulfilled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    public_order_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vpn_server_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vpn_servers.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False)

    price_amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency_snapshot: Mapped[str] = mapped_column(String(8), nullable=False)
    payment_instructions_snapshot: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[OrderStatus] = mapped_column(String(32), default=OrderStatus.AWAITING_RECEIPT, nullable=False, index=True)

    receipt_telegram_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    receipt_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    receipt_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    receipt_media_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    receipt_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="orders")
    subscription: Mapped[Optional["Subscription"]] = relationship("Subscription", back_populates="order", uselist=False)
