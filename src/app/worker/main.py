import asyncio
import signal
from typing import Optional
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from src.app.config.settings import ProvisionerMode, get_settings
from src.app.db.session import get_session_factory
from src.app.integrations.provisioning.base import VPNProvisioner
from src.app.integrations.provisioning.mock_provisioner import MockProvisioner
from src.app.integrations.provisioning.ssh_provisioner import LocalCommandProvisioner, SSHCommandProvisioner
from src.app.utils.logging import get_logger, setup_logging
from src.app.worker.engine import WorkerEngine

logger = get_logger("worker")


def build_provisioner(settings) -> VPNProvisioner:
    if settings.PROVISIONER_MODE == ProvisionerMode.SSH:
        return SSHCommandProvisioner(vpnctl_command=settings.VPNCTL_COMMAND)
    if settings.PROVISIONER_MODE == ProvisionerMode.LOCAL:
        return LocalCommandProvisioner(vpnctl_command=settings.VPNCTL_COMMAND)
    return MockProvisioner()


def build_worker(session_factory, bot: Bot, settings, provisioner: Optional[VPNProvisioner] = None) -> WorkerEngine:
    logger.info("worker_provisioner", mode=settings.PROVISIONER_MODE.value)
    return WorkerEngine(
        session_factory=session_factory,
        provisioner=provisioner or build_provisioner(settings),
        bot=bot,
        poll_interval=settings.PROVISIONING_JOB_POLL_SECONDS,
        admin_chat_id=settings.ADMIN_CHAT_ID,
    )


async def main():
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    engine = build_worker(get_session_factory(settings), bot, settings)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, engine.stop)

    try:
        await engine.start()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
