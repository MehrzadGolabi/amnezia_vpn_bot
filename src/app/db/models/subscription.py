import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.models.base import Base, TimestampMixin


class SubscriptionStatus(str, Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"
    FAILED = "failed"
    REVOKED = "revoked"


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), unique=True, nullable=False)
    vpn_server_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vpn_servers.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False)

    status: Mapped[SubscriptionStatus] = mapped_column(String(32), default=SubscriptionStatus.PROVISIONING, nullable=False, index=True)

    peer_external_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    peer_label: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)

    config_delivery_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    config_delivery_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    config_redelivery_count: Mapped[int] = mapped_column(default=0, nullable=False)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    order: Mapped["Order"] = relationship("Order", back_populates="subscription")
