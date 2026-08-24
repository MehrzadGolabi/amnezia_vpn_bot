import uuid
from typing import Optional
from sqlalchemy import Boolean, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.models.base import Base, TimestampMixin


class VPNServer(Base, TimestampMixin):
    __tablename__ = "vpn_servers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    country_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provisioner_type: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    host: Mapped[str] = mapped_column(String(255), default="localhost", nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    ssh_username: Mapped[str] = mapped_column(String(64), default="vpn-provisioner", nullable=False)
    max_active_subscriptions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
