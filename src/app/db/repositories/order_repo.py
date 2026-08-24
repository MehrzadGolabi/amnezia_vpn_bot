import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.order import Order, OrderStatus
from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.db.models.job import ProvisioningJob, JobType, JobStatus
from src.app.db.models.product import Product
from src.app.db.models.server import VPNServer
from src.app.db.models.audit import AuditEvent, ActorType
from src.app.db.models.base import utc_now


def generate_order_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(alphabet) for _ in range(6))
    return f"ORD-{code}"


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.subscription))
            .where(Order.id == order_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.subscription))
            .where(Order.public_order_code == code.upper().strip())
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_order(
        self,
        user_id: uuid.UUID,
        vpn_server_id: uuid.UUID,
        product_id: uuid.UUID,
        price_amount: Decimal,
        price_currency: str,
        payment_instructions: str,
    ) -> Order:
        code = generate_order_code()
        order = Order(
            public_order_code=code,
            user_id=user_id,
            vpn_server_id=vpn_server_id,
            product_id=product_id,
            price_amount_snapshot=price_amount,
            currency_snapshot=price_currency,
            payment_instructions_snapshot=payment_instructions,
            status=OrderStatus.AWAITING_RECEIPT,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def submit_receipt(
        self,
        order_id: uuid.UUID,
        file_id: str,
        message_id: int,
        chat_id: int,
        media_type: str = "photo",
        note: Optional[str] = None,
    ) -> Optional[Order]:
        order = await self.get_by_id(order_id)
        if not order:
            return None
        order.receipt_telegram_file_id = file_id
        order.receipt_message_id = message_id
        order.receipt_chat_id = chat_id
        order.receipt_media_type = media_type
        order.receipt_note = note
        order.submitted_at = utc_now()
        order.status = OrderStatus.RECEIPT_SUBMITTED
        await self.session.flush()
        return order

    async def approve_order_atomic(
        self,
        order_id: uuid.UUID,
        admin_telegram_id: int,
    ) -> Tuple[bool, Optional[Subscription], Optional[ProvisioningJob]]:
        """
        Atomically approves an order, creates the subscription in provisioning state,
        and enqueues the create_peer provisioning job.
        Strictly idempotent: returns (False, existing_sub, None) if already processed.
        """
        order = await self.get_by_id(order_id)
        if not order:
            return False, None, None

        # Check existing subscription
        stmt = select(Subscription).where(Subscription.order_id == order.id)
        res = await self.session.execute(stmt)
        existing_sub = res.scalar_one_or_none()

        if existing_sub is not None or order.status in (OrderStatus.APPROVED, OrderStatus.PROVISIONING, OrderStatus.FULFILLED):
            return False, existing_sub, None

        product = await self.session.get(Product, order.product_id)
        server = await self.session.get(VPNServer, order.vpn_server_id)
        if not product or not server:
            return False, None, None

        now = utc_now()
        order.status = OrderStatus.PROVISIONING
        order.reviewed_by_telegram_user_id = admin_telegram_id
        order.reviewed_at = now

        duration_days = product.duration_days if product else 30
        subscription = Subscription(
            user_id=order.user_id,
            order_id=order.id,
            vpn_server_id=order.vpn_server_id,
            product_id=order.product_id,
            status=SubscriptionStatus.PROVISIONING,
            starts_at=now,
            expires_at=now + timedelta(days=duration_days),
        )
        self.session.add(subscription)
        await self.session.flush()

        job = ProvisioningJob(
            job_type=JobType.CREATE_PEER,
            aggregate_type="subscription",
            aggregate_id=subscription.id,
            status=JobStatus.PENDING,
            payload={
                "subscription_id": str(subscription.id),
                "order_id": str(order.id),
                "user_id": str(order.user_id),
                "server_id": str(server.id),
                "server_slug": server.slug,
                "duration_days": duration_days,
            },
        )
        self.session.add(job)

        audit = AuditEvent(
            actor_type=ActorType.ADMIN,
            actor_telegram_user_id=admin_telegram_id,
            event_type="order.approved",
            entity_type="order",
            entity_id=order.id,
            metadata_json={"order_code": order.public_order_code, "subscription_id": str(subscription.id)},
        )
        self.session.add(audit)
        await self.session.flush()

        return True, subscription, job

    async def reject_order(
        self,
        order_id: uuid.UUID,
        admin_telegram_id: int,
        reason: Optional[str] = None,
    ) -> Tuple[bool, Optional[Order]]:
        order = await self.get_by_id(order_id)
        if not order or order.status in (OrderStatus.APPROVED, OrderStatus.PROVISIONING, OrderStatus.FULFILLED):
            return False, order

        order.status = OrderStatus.REJECTED
        order.reviewed_by_telegram_user_id = admin_telegram_id
        order.reviewed_at = utc_now()
        order.rejection_reason = reason

        audit = AuditEvent(
            actor_type=ActorType.ADMIN,
            actor_telegram_user_id=admin_telegram_id,
            event_type="order.rejected",
            entity_type="order",
            entity_id=order.id,
            metadata_json={"order_code": order.public_order_code, "reason": reason or ""},
        )
        self.session.add(audit)
        await self.session.flush()
        return True, order

    async def list_pending_orders(self) -> List[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.user))
            .where(Order.status == OrderStatus.RECEIPT_SUBMITTED)
            .order_by(Order.submitted_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_recent_orders(self, limit: int = 10) -> List[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.user))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
