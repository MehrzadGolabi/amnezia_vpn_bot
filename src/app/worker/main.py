import asyncio
import signal
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from src.app.config.settings import ProvisionerMode, get_settings
from src.app.db.session import get_session_factory
from src.app.integrations.provisioning.mock_provisioner import MockProvisioner
from src.app.integrations.provisioning.ssh_provisioner import SSHCommandProvisioner
from src.app.utils.logging import get_logger, setup_logging
from src.app.worker.engine import WorkerEngine

logger = get_logger("worker")


async def main():
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    if settings.PROVISIONER_MODE == ProvisionerMode.SSH:
        provisioner = SSHCommandProvisioner()
    else:
        provisioner = MockProvisioner()

    session_factory = get_session_factory(settings)
    engine = WorkerEngine(
        session_factory=session_factory,
        provisioner=provisioner,
        bot=bot,
        poll_interval=settings.PROVISIONING_JOB_POLL_SECONDS,
        admin_chat_id=settings.ADMIN_CHAT_ID,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, engine.stop)

    try:
        await engine.start()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
