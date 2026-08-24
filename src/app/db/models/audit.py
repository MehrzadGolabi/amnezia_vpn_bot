import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from sqlalchemy import BigInteger, DateTime, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.models.base import Base, utc_now


class ActorType(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    SYSTEM = "system"


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_type: Mapped[ActorType] = mapped_column(String(32), nullable=False, index=True)
    actor_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True, index=True)

    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
