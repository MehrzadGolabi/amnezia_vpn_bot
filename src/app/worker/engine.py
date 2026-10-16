import asyncio
import uuid
from typing import Callable, Optional
from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.audit import ActorType
from src.app.db.models.job import JobStatus, JobType, ProvisioningJob
from src.app.db.models.order import OrderStatus
from src.app.db.repositories.audit_repo import AuditRepository
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.user_repo import UserRepository
from src.app.integrations.provisioning.base import VPNProvisioner
from src.app.integrations.provisioning.ssh_provisioner import (
    PermanentProvisioningError,
    RetryableProvisioningError,
)
from src.app.utils.amnezia_codec import encode_vpn_url
from src.app.bot.locales.strings import get_text, server_name
from src.app.utils.logging import get_logger

logger = get_logger(__name__)


class WorkerEngine:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        provisioner: VPNProvisioner,
        bot: Bot,
        worker_id: Optional[str] = None,
        poll_interval: int = 5,
        admin_chat_id: Optional[int] = None,
    ):
        self.session_factory = session_factory
        self.provisioner = provisioner
        self.bot = bot
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.admin_chat_id = admin_chat_id
        self._running = False
        self._stop_event = asyncio.Event()

    async def run_single_batch(self, limit: int = 10) -> int:
        session = self.session_factory()
        job_repo = JobRepository(session)
        
        try:
            jobs = await job_repo.claim_pending_jobs(worker_id=self.worker_id, limit=limit)
            if not jobs:
                return 0
            # Commit the claim now, so a failure in one job can't roll back the others' locks.
            job_ids = [job.id for job in jobs]
            await session.commit()

            for job_id in job_ids:
                job = await job_repo.get_by_id(job_id)
                try:
                    await self._process_job(session, job)
                    await job_repo.mark_completed(job_id)
                    await session.commit()
                except Exception as e:
                    # Drop whatever the failed job half-wrote before recording the failure.
                    await session.rollback()
                    permanent = isinstance(e, PermanentProvisioningError)
                    if permanent:
                        logger.error("permanent_job_failure", job_id=str(job_id), error=str(e))
                    else:
                        logger.warning("retryable_job_failure", job_id=str(job_id), error=str(e))
                    failed = await job_repo.mark_failed(job_id, str(e), is_retryable=not permanent)
                    await session.commit()
                    if failed and failed.status == JobStatus.PERMANENT_FAILURE:
                        await self._alert_admin(
                            f"🚨 Provisioning job {failed.job_type} {job_id} failed for good "
                            f"after {failed.attempt_count} attempt(s):\n{e}"
                        )

            return len(jobs)
        finally:
            # If session is active and not closed
            if hasattr(session, "close"):
                await session.close()

    async def _process_job(self, session: AsyncSession, job: ProvisioningJob) -> None:
        sub_repo = SubscriptionRepository(session)
        order_repo = OrderRepository(session)
        server_repo = ServerRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditRepository(session)

        if job.job_type == JobType.CREATE_PEER:
            sub = await sub_repo.get_by_id(job.aggregate_id)
            if not sub:
                raise PermanentProvisioningError(f"Subscription {job.aggregate_id} not found")

            server = await server_repo.get_by_id(sub.vpn_server_id)
            user = await user_repo.get_by_id(sub.user_id)
            order = await order_repo.get_by_id(sub.order_id)
            if not server or not user:
                raise PermanentProvisioningError("Server or User missing for subscription")

            # Call provisioner
            peer = await self.provisioner.create_peer(
                server=server,
                subscription_id=sub.id,
                telegram_user_id=user.telegram_user_id,
            )

            # Update subscription & order
            await sub_repo.mark_active(sub.id, peer_external_id=peer.external_id, peer_label=peer.label)
            if order:
                order.status = OrderStatus.FULFILLED
                await session.flush()

            # Record audit
            await audit_repo.record_event(
                actor_type=ActorType.SYSTEM,
                event_type="subscription.activated",
                entity_type="subscription",
                entity_id=sub.id,
                metadata={"peer_id": peer.external_id, "server_slug": server.slug},
            )

            # Deliver config file document to user
            expiry_str = sub.expires_at.strftime("%Y-%m-%d %H:%M UTC")
            lang = user.language_code
            caption = get_text(
                "config_ready", lang, server_name=server_name(server, lang), expires_at=expiry_str
            )
            delivered = await self._deliver_config(
                user.telegram_user_id, peer.config_bytes, peer.config_filename, caption, peer.vpn_url, lang
            )
            sub.config_delivery_status = "delivered" if delivered else "failed"
            if not delivered:
                await self._alert_admin(
                    f"⚠️ Peer {peer.external_id} was created but its config could not be sent to "
                    f"user {user.telegram_user_id}. They can use Redeliver in their subscription menu."
                )

        elif job.job_type == JobType.DISABLE_PEER:
            sub = await sub_repo.get_by_id(job.aggregate_id)
            if sub and sub.peer_external_id:
                server = await server_repo.get_by_id(sub.vpn_server_id)
                if server:
                    await self.provisioner.disable_peer(server=server, peer_external_id=sub.peer_external_id)
                await sub_repo.mark_disabled(sub.id)
                await audit_repo.record_event(
                    actor_type=ActorType.SYSTEM,
                    event_type="subscription.disabled",
                    entity_type="subscription",
                    entity_id=sub.id,
                )

        elif job.job_type == JobType.REMOVE_PEER:
            sub = await sub_repo.get_by_id(job.aggregate_id)
            if sub and sub.peer_external_id:
                server = await server_repo.get_by_id(sub.vpn_server_id)
                if server:
                    await self.provisioner.remove_peer(server=server, peer_external_id=sub.peer_external_id)
                await sub_repo.mark_removed(sub.id)
                await audit_repo.record_event(
                    actor_type=ActorType.SYSTEM,
                    event_type="subscription.removed",
                    entity_type="subscription",
                    entity_id=sub.id,
                )

        elif job.job_type == JobType.REDELIVER_CONFIG:
            sub = await sub_repo.get_by_id(job.aggregate_id)
            if sub and sub.peer_external_id:
                server = await server_repo.get_by_id(sub.vpn_server_id)
                user = await user_repo.get_by_id(sub.user_id)
                if server and user:
                    config_bytes = await self.provisioner.get_peer_config(server=server, peer_external_id=sub.peer_external_id)
                    filename = f"{sub.peer_label or 'amneziawg'}.conf"
                    conf_str = config_bytes.decode("utf-8", errors="ignore")
                    lang = user.language_code
                    caption = get_text("config_redelivery", lang, server_name=server_name(server, lang))
                    delivered = await self._deliver_config(
                        user.telegram_user_id, config_bytes, filename, caption,
                        encode_vpn_url(conf_str) if conf_str else None, lang,
                    )
                    if not delivered:
                        raise RetryableProvisioningError(f"Could not send config to user {user.telegram_user_id}")
                    sub.config_delivery_status = "delivered"
                    await sub_repo.increment_redelivery_count(sub.id)

    async def _deliver_config(
        self,
        chat_id: int,
        config_bytes: bytes,
        filename: str,
        caption: str,
        vpn_url: Optional[str],
        lang: Optional[str] = "en",
    ) -> bool:
        """Send the .conf file, then the vpn:// key as its own message.
        AWG 3.1 keys are too long for Telegram's 1024-character caption limit."""
        try:
            await self.bot.send_document(
                chat_id=chat_id,
                document=BufferedInputFile(config_bytes, filename=filename),
                caption=caption,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("failed_to_send_config_document", user_id=chat_id, error=str(e))
            return False
        if vpn_url:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=get_text("vpn_key", lang, vpn_url=vpn_url),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("failed_to_send_vpn_url", user_id=chat_id, error=str(e))
        return True

    async def _alert_admin(self, message: str) -> None:
        if self.admin_chat_id:
            try:
                await self.bot.send_message(chat_id=self.admin_chat_id, text=message)
            except Exception as e:
                logger.error("admin_alert_failed", error=str(e))

    async def start(self) -> None:
        self._running = True
        logger.info("worker_started", worker_id=self.worker_id)
        while self._running:
            try:
                await self.run_single_batch()
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
            
            # Always yield execution to prevent high CPU utilization on single-core nodes
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
