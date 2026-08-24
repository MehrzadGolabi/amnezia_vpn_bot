import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import or_, select
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

    async def claim_pending_jobs(self, worker_id: str, limit: int = 10) -> List[ProvisioningJob]:
        now = utc_now()
        # Find pending or retryable jobs whose lock has expired (after 5 minutes)
        lock_timeout = now - timedelta(minutes=5)
        stmt = (
            select(ProvisioningJob)
            .where(
                or_(
                    ProvisioningJob.status.in_([JobStatus.PENDING, JobStatus.RETRYABLE_FAILURE]),
                    (
                        (ProvisioningJob.status == JobStatus.PROCESSING)
                        & (ProvisioningJob.locked_at < lock_timeout)
                    ),
                ),
                ProvisioningJob.available_at <= now,
            )
            .order_by(ProvisioningJob.available_at.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        jobs = list(res.scalars().all())

        claimed_jobs: List[ProvisioningJob] = []
        for job in jobs:
            job.status = JobStatus.PROCESSING
            job.locked_at = now
            job.locked_by = worker_id
            claimed_jobs.append(job)

        if claimed_jobs:
            await self.session.flush()

        return claimed_jobs

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
