from src.app.bot.handlers.customer import customer_router, fallback_router
from src.app.bot.handlers.support import support_router
from src.app.bot.handlers.admin import admin_router
from src.app.bot.handlers.admin_jobs import admin_jobs_router
from src.app.bot.handlers.admin_broadcast import admin_broadcast_router

__all__ = [
    "customer_router", "fallback_router", "support_router", "admin_router", "admin_jobs_router",
    "admin_broadcast_router",
]
