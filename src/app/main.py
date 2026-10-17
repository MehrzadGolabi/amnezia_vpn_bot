"""Bot, worker and scheduler in one process.

Each process that imports aiogram pays ~150 MB for its Telegram types, so running the
three together uses about a third of the memory of running them separately. The
separate entry points (src.app.bot.main, src.app.worker.main, src.app.scheduler.main)
still work, for Docker or for scaling the worker out.
"""
import asyncio
import contextlib

from src.app.bot.main import build_dispatcher, make_bot
from src.app.config.settings import get_settings
from src.app.db.session import get_session_factory
from src.app.scheduler.main import build_scheduler
from src.app.utils.logging import get_logger, setup_logging
from src.app.worker.main import build_provisioner, build_worker

logger = get_logger("main")


async def main():
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    bot = make_bot(settings)
    session_factory = get_session_factory(settings)
    # One provisioner for both, so the bot's usage view and the worker see the same peers.
    provisioner = build_provisioner(settings)
    dp = await build_dispatcher(session_factory, settings, provisioner)
    worker = build_worker(session_factory, bot, settings, provisioner)
    scheduler = build_scheduler(session_factory, bot, settings)

    worker_task = asyncio.create_task(worker.start())
    scheduler.start()
    logger.info("all_in_one_started")
    try:
        # Returns on SIGINT/SIGTERM.
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        worker.stop()
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
