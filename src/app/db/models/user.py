import uuid
from typing import List, Optional
from sqlalchemy import BigInteger, Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), default="en", nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user", lazy="selectin")
    subscriptions: Mapped[List["Subscription"]] = relationship("Subscription", back_populates="user", lazy="selectin")
    tickets: Mapped[List["SupportTicket"]] = relationship("SupportTicket", back_populates="user", lazy="selectin")
