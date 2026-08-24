import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.models.base import Base, utc_now


class NotificationType(str, Enum):
    ORDER_RECEIVED = "order_received"
    ORDER_APPROVED = "order_approved"
    ORDER_REJECTED = "order_rejected"
    CONFIG_DELIVERED = "config_delivered"
    EXPIRES_7D = "expires_7d"
    EXPIRES_3D = "expires_3d"
    EXPIRES_1D = "expires_1d"
    EXPIRED = "expired"
    SUPPORT_REPLY = "support_reply"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)

    notification_type: Mapped[NotificationType] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
