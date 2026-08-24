import asyncio
import signal
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from src.app.config.settings import get_settings
from src.app.db.session import get_session_factory
from src.app.scheduler.service import SchedulerService
from src.app.utils.logging import get_logger, setup_logging

logger = get_logger("scheduler")


async def main():
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    session_factory = get_session_factory(settings)
    service = SchedulerService(
        session_factory=session_factory,
        bot=bot,
        reminder_days=settings.REMINDER_DAYS_BEFORE_EXPIRY,
        peer_removal_grace_days=settings.PEER_REMOVAL_GRACE_DAYS,
        interval_seconds=settings.EXPIRY_CHECK_INTERVAL_SECONDS,
    )

    service.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("scheduler_service_running")
    await stop_event.wait()
    service.stop()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
