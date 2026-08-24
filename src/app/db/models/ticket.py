import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.models.base import Base, TimestampMixin, utc_now


class TicketStatus(str, Enum):
    OPEN = "open"
    WAITING_FOR_ADMIN = "waiting_for_admin"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    CLOSED = "closed"


class SenderType(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    SYSTEM = "system"


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    public_ticket_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status: Mapped[TicketStatus] = mapped_column(String(32), default=TicketStatus.OPEN, nullable=False, index=True)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assigned_admin_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="tickets")
    messages: Mapped[List["SupportMessage"]] = relationship("SupportMessage", back_populates="ticket", lazy="selectin", cascade="all, delete-orphan")


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)

    sender_type: Mapped[SenderType] = mapped_column(String(32), nullable=False)
    sender_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    attachment_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attachment_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    ticket: Mapped["SupportTicket"] = relationship("SupportTicket", back_populates="messages")
