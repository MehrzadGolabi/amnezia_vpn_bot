"""The single-process entry point starts the worker and scheduler next to the bot and stops them with it."""
import asyncio
from unittest.mock import patch

from aiogram import Bot, Dispatcher

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app import main as all_in_one
from src.app.db.models.base import Base


async def test_runs_worker_and_scheduler_alongside_polling(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(all_in_one, "get_session_factory", lambda st: factory)
    monkeypatch.setattr(all_in_one, "make_bot", lambda st: Bot(token="42:TEST"))
    seen = {}

    async def fake_polling(self, bot, **kwargs):
        await asyncio.sleep(0.05)  # let the worker loop run once
        seen["worker_running"] = worker_ref["w"]._running
        seen["scheduler_running"] = scheduler_ref["s"].scheduler.running

    worker_ref, scheduler_ref = {}, {}
    real_build_worker, real_build_scheduler = all_in_one.build_worker, all_in_one.build_scheduler

    def build_worker(*a):
        worker_ref["w"] = real_build_worker(*a)
        return worker_ref["w"]

    def build_scheduler(*a):
        scheduler_ref["s"] = real_build_scheduler(*a)
        return scheduler_ref["s"]

    with patch.object(Dispatcher, "start_polling", fake_polling), \
         patch.object(all_in_one, "build_dispatcher", lambda sf, st, pv=None: _dispatcher()), \
         patch.object(all_in_one, "build_worker", build_worker), \
         patch.object(all_in_one, "build_scheduler", build_scheduler):
        await all_in_one.main()

    assert seen == {"worker_running": True, "scheduler_running": True}
    assert worker_ref["w"]._running is False
    assert scheduler_ref["s"].scheduler.running is False
    await engine.dispose()


async def _dispatcher():
    # A bare dispatcher: the real one attaches the routers, which can only happen once per process.
    return Dispatcher()
