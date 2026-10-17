import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Type

from sqlalchemy import DateTime, String
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EnumString(TypeDecorator):
    """A VARCHAR column that holds an Enum's value and loads back as the Enum.

    A plain String column hands back a str after a reload, so `row.status.value`
    works on a fresh object but raises on one read from the database.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: Type[Enum], length: int = 32):
        super().__init__(length)
        self.enum_cls = enum_cls

    def process_bind_param(self, value, dialect) -> Optional[str]:
        if value is None:
            return None
        return self.enum_cls(value).value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self.enum_cls(value)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
