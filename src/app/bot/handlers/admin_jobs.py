"""Admin tools for the job queue and the audit log: /retry and /audit."""
import html
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.handlers.admin import is_admin
from src.app.bot.ui import RETRY_PREFIX
from src.app.db.models.audit import ActorType, AuditEvent
from src.app.db.models.base import utc_now
from src.app.db.models.job import JobStatus, JobType, ProvisioningJob
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.repositories.audit_repo import AuditRepository
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository

admin_jobs_router = Router(name="admin_jobs")

RETRY_ALL = "adm_rty_all"


def _age(when: Optional[datetime]) -> str:
    if when is None:
        return "?"
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    minutes = int((utc_now() - when).total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // 1440} d ago"


async def retry_blocker(session: AsyncSession, job: ProvisioningJob) -> Optional[str]:
    """Why running this job again now would be wrong, or None if it is safe.

    Disable and remove jobs check for a renewal themselves when they run. Create and
    enable jobs don't, so an old one must not give a peer to a customer whose
    subscription has since been cancelled or has run out.
    """
    if await JobRepository(session).has_open_job(job.job_type, job.aggregate_id):
        return "the same job is already queued"
    sub = await SubscriptionRepository(session).get_by_id(job.aggregate_id)
    if sub is None:
        return "its subscription no longer exists"
    if job.job_type == JobType.CREATE_PEER and sub.status != SubscriptionStatus.PROVISIONING:
        return f"the subscription is {sub.status.value}, not waiting for a peer"
    if job.job_type == JobType.ENABLE_PEER:
        expires_at = sub.expires_at if sub.expires_at.tzinfo else sub.expires_at.replace(tzinfo=timezone.utc)
        if sub.status != SubscriptionStatus.ACTIVE or expires_at <= utc_now():
            return "the subscription isn't active any more"
    return None


async def _requeue(session: AsyncSession, job: ProvisioningJob, admin_id: int) -> Optional[str]:
    """Queue the job again and record who did it. Returns why not, if it can't be."""
    reason = await retry_blocker(session, job)
    if reason:
        return reason
    previous_error = job.last_error
    await JobRepository(session).requeue(job)
    await AuditRepository(session).record_event(
        actor_type=ActorType.ADMIN,
        actor_telegram_user_id=admin_id,
        event_type="job.requeued",
        entity_type="provisioning_job",
        entity_id=job.id,
        metadata={"job_type": job.job_type.value, "subscription_id": str(job.aggregate_id),
                  "previous_error": (previous_error or "")[:500]},
    )
    return None


async def _failed_list(session: AsyncSession) -> tuple:
    jobs = await JobRepository(session).list_permanent_failures(limit=10)
    if not jobs:
        return "✅ No jobs have failed for good.", None
    lines = [f"🚨 <b>Jobs that failed for good ({len(jobs)}{'+' if len(jobs) == 10 else ''})</b>\n"]
    buttons: List[List[InlineKeyboardButton]] = []
    for job in jobs:
        first_line = (job.last_error or "").strip().splitlines()[:1]
        error = html.escape(first_line[0][:120]) if first_line else "no error saved"
        lines.append(
            f"<code>{job.id.hex[:8]}</code> {job.job_type.value} · {_age(job.updated_at)}\n<i>{error}</i>"
        )
        buttons.append([InlineKeyboardButton(text=f"🔁 {job.job_type.value} {job.id.hex[:8]}",
                                             callback_data=f"{RETRY_PREFIX}{job.id.hex}")])
    buttons.append([InlineKeyboardButton(text="🔁 Retry all", callback_data=RETRY_ALL)])
    lines.append("\nRetry one with its button, or every one with Retry all.")
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@admin_jobs_router.message(Command("retry"))
async def cmd_retry(message: Message, data: Dict[str, Any]):
    if not message.from_user or not is_admin(message.from_user.id):
        return
    text, kb = await _failed_list(data.get("session"))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@admin_jobs_router.callback_query(F.data.startswith(RETRY_PREFIX))
async def callback_retry(query: CallbackQuery, data: Dict[str, Any]):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return
    session: AsyncSession = data.get("session")
    job_repo = JobRepository(session)

    if query.data == RETRY_ALL:
        jobs = await job_repo.list_permanent_failures(limit=100)
    else:
        try:
            job = await job_repo.get_by_id(uuid.UUID(hex=query.data[len(RETRY_PREFIX):]))
        except ValueError:
            job = None
        jobs = [job] if job else []

    queued, skipped = 0, []
    for job in jobs:
        if job.status != JobStatus.PERMANENT_FAILURE:
            skipped.append(f"{job.id.hex[:8]}: already {job.status.value}")
            continue
        reason = await _requeue(session, job, query.from_user.id)
        if reason:
            skipped.append(f"{job.id.hex[:8]}: {reason}")
        else:
            queued += 1
    await session.commit()

    summary = f"Queued {queued} job(s) again."
    if skipped:
        summary += "\nSkipped:\n" + "\n".join(skipped[:10])
    if not jobs:
        summary = "No jobs have failed for good." if query.data == RETRY_ALL else "That job no longer exists."
    await query.answer(summary[:200], show_alert=True)
    if query.message and query.data == RETRY_ALL:
        text, kb = await _failed_list(session)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


@admin_jobs_router.message(Command("audit"))
async def cmd_audit(message: Message, data: Dict[str, Any]):
    """The latest admin and system actions, newest first."""
    if not message.from_user or not is_admin(message.from_user.id):
        return
    session: AsyncSession = data.get("session")
    events = list((await session.execute(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(20)
    )).scalars().all())
    if not events:
        await message.answer("The audit log is empty.")
        return
    lines = ["🧾 <b>Latest actions</b>\n"]
    for e in events:
        who = f"admin {e.actor_telegram_user_id}" if e.actor_type == ActorType.ADMIN else e.actor_type.value
        details = ", ".join(f"{k}={v}" for k, v in (e.metadata_json or {}).items())
        lines.append(
            f"<code>{e.created_at.strftime('%m-%d %H:%M')}</code> {html.escape(e.event_type)} · {html.escape(who)}"
            + (f"\n<i>{html.escape(details[:160])}</i>" if details else "")
        )
    await message.answer("\n".join(lines), parse_mode="HTML")
