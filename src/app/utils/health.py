from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_system_health(session: AsyncSession) -> Dict[str, Any]:
    db_healthy = False
    error = None

    try:
        res = await session.execute(text("SELECT 1"))
        db_healthy = (res.scalar() == 1)
    except Exception as e:
        error = str(e)

    status = "ok" if db_healthy else "degraded"
    return {
        "status": status,
        "db_healthy": db_healthy,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
