import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.audit import AuditEvent, ActorType
from src.app.utils.logging import redact_sensitive_text


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        sanitized: Dict[str, Any] = {}
        for k, v in metadata.items():
            if any(secret_term in k.lower() for secret_term in ("secret", "token", "password", "key", "private")):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, str):
                sanitized[k] = redact_sensitive_text(v)
            else:
                sanitized[k] = v
        return sanitized

    async def record_event(
        self,
        actor_type: ActorType,
        event_type: str,
        entity_type: str,
        actor_telegram_user_id: Optional[int] = None,
        entity_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        clean_metadata = self._sanitize_metadata(metadata or {})
        event = AuditEvent(
            actor_type=actor_type,
            actor_telegram_user_id=actor_telegram_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=clean_metadata,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_entity(self, entity_type: str, entity_id: uuid.UUID) -> List[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_idempotency_key(self, key: str):
        from src.app.db.models.notification import Notification
        stmt = select(Notification).where(Notification.idempotency_key == key)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_notification_if_not_exists(
        self,
        user_id: uuid.UUID,
        notification_type,
        idempotency_key: str,
        subscription_id: Optional[uuid.UUID] = None,
    ):
        from src.app.db.models.notification import Notification
        existing = await self.get_by_idempotency_key(idempotency_key)
        if existing:
            return None, False

        notif = Notification(
            user_id=user_id,
            subscription_id=subscription_id,
            notification_type=notification_type,
            idempotency_key=idempotency_key,
            status="pending",
        )
        self.session.add(notif)
        await self.session.flush()
        return notif, True
