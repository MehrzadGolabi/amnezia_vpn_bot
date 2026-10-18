import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.job import ProvisioningJob, JobStatus, JobType
from src.app.db.models.base import utc_now


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, job_id: uuid.UUID) -> Optional[ProvisioningJob]:
        return await self.session.get(ProvisioningJob, job_id)

    async def enqueue_job(
        self,
        job_type: JobType,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: Dict[str, Any],
        available_at: Optional[datetime] = None,
    ) -> ProvisioningJob:
        job = ProvisioningJob(
            job_type=job_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            status=JobStatus.PENDING,
            payload=payload,
            available_at=available_at or utc_now(),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def has_open_job(self, job_type: JobType, aggregate_id: uuid.UUID) -> bool:
        """True if a job of this type for this aggregate is still queued, running or retrying."""
        stmt = (
            select(ProvisioningJob.id)
            .where(
                ProvisioningJob.job_type == job_type,
                ProvisioningJob.aggregate_id == aggregate_id,
                ProvisioningJob.status.in_(
                    [JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.RETRYABLE_FAILURE]
                ),
            )
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.first() is not None

    @staticmethod
    def _claimable(now: datetime):
        """Pending or retrying jobs that are due, or ones a crashed worker left in
        processing for more than 5 minutes."""
        return (
            or_(
                ProvisioningJob.status.in_([JobStatus.PENDING, JobStatus.RETRYABLE_FAILURE]),
                (
                    (ProvisioningJob.status == JobStatus.PROCESSING)
                    & (ProvisioningJob.locked_at < now - timedelta(minutes=5))
                ),
            ),
            ProvisioningJob.available_at <= now,
        )

    async def claim_one(self, job_id: uuid.UUID, worker_id: str, now: datetime) -> bool:
        """Claim one job in a single UPDATE that only matches while it is still claimable.
        If another worker got there first, nothing matches and this returns False."""
        stmt = (
            update(ProvisioningJob)
            .where(ProvisioningJob.id == job_id, *self._claimable(now))
            .values(status=JobStatus.PROCESSING, locked_at=now, locked_by=worker_id)
            .execution_options(synchronize_session=False)
        )
        res = await self.session.execute(stmt)
        return res.rowcount == 1

    async def claim_pending_jobs(self, worker_id: str, limit: int = 10) -> List[ProvisioningJob]:
        now = utc_now()
        stmt = (
            select(ProvisioningJob.id)
            .where(*self._claimable(now))
            .order_by(ProvisioningJob.available_at.asc())
            .limit(limit)
        )
        candidates = list((await self.session.execute(stmt)).scalars().all())
        claimed = [job_id for job_id in candidates if await self.claim_one(job_id, worker_id, now)]
        if not claimed:
            return []
        # Load the rows as the UPDATEs left them, not as any copy already in the session.
        res = await self.session.execute(
            select(ProvisioningJob)
            .where(ProvisioningJob.id.in_(claimed))
            .order_by(ProvisioningJob.available_at.asc())
            .execution_options(populate_existing=True)
        )
        return list(res.scalars().all())

    async def mark_completed(self, job_id: uuid.UUID) -> Optional[ProvisioningJob]:
        job = await self.get_by_id(job_id)
        if job:
            job.status = JobStatus.SUCCEEDED
            job.locked_at = None
            job.locked_by = None
            await self.session.flush()
        return job

    async def mark_failed(
        self,
        job_id: uuid.UUID,
        error_message: str,
        is_retryable: bool = True,
        max_retries: int = 5,
    ) -> Optional[ProvisioningJob]:
        job = await self.get_by_id(job_id)
        if not job:
            return None

        job.attempt_count += 1
        job.last_error = error_message
        job.locked_at = None
        job.locked_by = None

        if is_retryable and job.attempt_count < max_retries:
            job.status = JobStatus.RETRYABLE_FAILURE
            # Exponential backoff: 10s, 30s, 90s, 270s...
            backoff_seconds = 10 * (3 ** (job.attempt_count - 1))
            job.available_at = utc_now() + timedelta(seconds=backoff_seconds)
        else:
            job.status = JobStatus.PERMANENT_FAILURE

        await self.session.flush()
        return job

    async def list_permanent_failures(self, limit: int = 10) -> List[ProvisioningJob]:
        stmt = (
            select(ProvisioningJob)
            .where(ProvisioningJob.status == JobStatus.PERMANENT_FAILURE)
            .order_by(ProvisioningJob.updated_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def requeue(self, job: ProvisioningJob) -> ProvisioningJob:
        """Give a job that failed for good a fresh set of attempts, starting now."""
        job.status = JobStatus.PENDING
        job.attempt_count = 0
        job.available_at = utc_now()
        job.locked_at = None
        job.locked_by = None
        job.last_error = None
        await self.session.flush()
        return job
