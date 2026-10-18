import uuid
from typing import Optional
from sqlalchemy import Boolean, Integer, String, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.models.base import Base, TimestampMixin


class VPNServer(Base, TimestampMixin):
    __tablename__ = "vpn_servers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    country_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # From VPN_SERVER_<NAME>_ENABLED in .env, reloaded on every start.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Set by the /servers button. Kept across restarts, because .env never touches it.
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provisioner_type: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    host: Mapped[str] = mapped_column(String(255), default="localhost", nullable=False)
    max_active_subscriptions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    @property
    def on_sale(self) -> bool:
        """Turned on in .env and not paused from /servers. Capacity is checked separately."""
        return bool(self.enabled) and not self.paused
