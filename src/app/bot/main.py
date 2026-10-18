import asyncio
from decimal import Decimal
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from src.app.config.settings import get_settings
from src.app.db.session import get_session_factory
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.bot.middleware.user_middleware import UserMiddleware
from src.app.bot.middleware.throttling_middleware import ThrottlingMiddleware
from src.app.bot.handlers import admin_router, customer_router, fallback_router, support_router
from src.app.utils.logging import get_logger, setup_logging
from src.app.worker.main import build_provisioner

logger = get_logger("bot")


async def init_data(session_factory, settings):
    """Seed configured servers and default product plans if needed."""
    async with session_factory() as session:
        server_repo = ServerRepository(session)
        product_repo = ProductRepository(session)

        # Sync servers from settings
        for slug, s_cfg in settings.vpn_servers.items():
            await server_repo.create_or_update(
                slug=s_cfg.slug,
                display_name=s_cfg.display_name,
                country_code=s_cfg.country_code,
                country_name=s_cfg.display_name,
                host=s_cfg.host,
                provisioner_type=settings.PROVISIONER_MODE.value,
                enabled=s_cfg.enabled,
                max_active_subscriptions=s_cfg.max_active_subscriptions,
            )

        # Ensure default products exist
        existing_products = await product_repo.list_enabled()
        if not existing_products:
            await product_repo.create_or_update(
                code="vpn-1m",
                title="1 Month (1 User)",
                duration_days=30,
                device_limit=1,
                price_amount=Decimal("5.00"),
                price_currency="EUR",
                sort_order=1,
            )
            await product_repo.create_or_update(
                code="vpn-3m",
                title="3 Months (2 Users)",
                duration_days=90,
                device_limit=2,
                price_amount=Decimal("12.00"),
                price_currency="EUR",
                sort_order=2,
            )
            await product_repo.create_or_update(
                code="vpn-6m",
                title="6 Months (3 Users)",
                duration_days=180,
                device_limit=3,
                price_amount=Decimal("20.00"),
                price_currency="EUR",
                sort_order=3,
            )

        await session.commit()
        logger.info(
            "initialized_servers_and_products",
            servers_count=len(settings.vpn_servers),
            servers=list(settings.vpn_servers.keys()),
        )


def make_bot(settings) -> Bot:
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )


async def build_dispatcher(session_factory, settings, provisioner=None) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Handlers read live usage (data used, last connection) through it.
    dp["provisioner"] = provisioner or build_provisioner(settings)

    # Initialize servers & catalog data
    try:
        await init_data(session_factory, settings)
    except Exception as e:
        logger.error("data_initialization_failed", error=str(e))

    # Register error handler
    @dp.error()
    async def error_handler(event: ErrorEvent):
        logger.error("telegram_bot_handler_exception", error=str(event.exception), exc_info=event.exception)

    # Register middlewares
    user_middleware = UserMiddleware(session_factory=session_factory)
    throttling_middleware = ThrottlingMiddleware(rate_limit_seconds=0.5)

    dp.message.outer_middleware(throttling_middleware)
    # Button presses too: opening a subscription asks its VPN host for usage over SSH.
    dp.callback_query.outer_middleware(ThrottlingMiddleware(rate_limit_seconds=0.5))
    dp.message.middleware(user_middleware)
    dp.callback_query.middleware(user_middleware)

    # Register routers
    dp.include_router(customer_router)
    dp.include_router(support_router)
    dp.include_router(admin_router)
    dp.include_router(fallback_router)
    return dp


async def main():
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    bot = make_bot(settings)
    dp = await build_dispatcher(get_session_factory(settings), settings)

    logger.info("telegram_bot_polling_started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
