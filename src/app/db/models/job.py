import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.models.base import Base, TimestampMixin, utc_now


class JobType(str, Enum):
    CREATE_PEER = "create_peer"
    DISABLE_PEER = "disable_peer"
    REMOVE_PEER = "remove_peer"
    REDELIVER_CONFIG = "redeliver_config"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


class ProvisioningJob(Base, TimestampMixin):
    __tablename__ = "provisioning_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_type: Mapped[JobType] = mapped_column(String(32), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING, nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
