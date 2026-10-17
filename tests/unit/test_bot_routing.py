"""Button presses fed through the real dispatcher, routers and middleware, with Telegram faked."""
import itertools
from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.bot.handlers import admin_router, customer_router, fallback_router, support_router
from src.app.bot.middleware.user_middleware import UserMiddleware
from src.app.config.settings import get_settings
from src.app.db.models.base import Base
from src.app.db.repositories.user_repo import UserRepository

ADMIN_ID = 900001
CUSTOMER_ID = 900002


class RecordingSession(BaseSession):
    """Stands in for the Telegram API: records every call and reports success."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=1, date=datetime.now(timezone.utc),
                chat=Chat(id=method.chat_id, type="private"), text=method.text,
            )
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self):
        pass


@pytest.fixture(scope="module")
def dispatcher():
    # Routers can only be attached once per process, so one dispatcher serves the module.
    dp = Dispatcher()
    dp.include_router(customer_router)
    dp.include_router(support_router)
    dp.include_router(admin_router)
    dp.include_router(fallback_router)
    return dp


@pytest.fixture
async def env(dispatcher):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    middleware = UserMiddleware(session_factory=factory)
    dispatcher.callback_query.middleware(middleware)
    dispatcher.message.middleware(middleware)

    settings = get_settings()
    old_admins = settings.ADMIN_TELEGRAM_IDS
    settings.ADMIN_TELEGRAM_IDS = [ADMIN_ID]

    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)
    yield dispatcher, bot, session, factory

    settings.ADMIN_TELEGRAM_IDS = old_admins
    dispatcher.callback_query.middleware._middlewares.remove(middleware)
    dispatcher.message.middleware._middlewares.remove(middleware)
    await engine.dispose()


_ids = itertools.count(1)


async def press(dp, bot, user_id, data, language_code="en"):
    user = TelegramUser(id=user_id, is_bot=False, first_name="T", language_code=language_code)
    menu = Message(
        message_id=10, date=datetime.now(timezone.utc),
        chat=Chat(id=user_id, type="private"), text="menu", from_user=user,
    )
    query = CallbackQuery(id=str(next(_ids)), from_user=user, chat_instance="c", message=menu, data=data)
    await dp.feed_update(bot, Update(update_id=next(_ids), callback_query=query))


def edits(session):
    return [c for c in session.calls if isinstance(c, EditMessageText)]


def answered(session):
    return any(isinstance(c, AnswerCallbackQuery) for c in session.calls)


async def test_admin_back_returns_to_dashboard(env):
    dp, bot, session, _ = env
    await press(dp, bot, ADMIN_ID, "adm_servers_status")
    session.calls.clear()

    await press(dp, bot, ADMIN_ID, "adm_back")
    assert "Admin Dashboard" in edits(session)[-1].text
    assert answered(session)


async def test_admin_pending_orders_button_answers(env):
    dp, bot, session, _ = env
    await press(dp, bot, ADMIN_ID, "adm_pending_orders")
    assert answered(session)


async def test_customer_back_buttons(env):
    dp, bot, session, _ = env
    for data, expected in [("menu_buy", "No VPN servers"), ("main_menu", "Welcome"), ("menu_subs", "subscriptions")]:
        session.calls.clear()
        await press(dp, bot, CUSTOMER_ID, data)
        assert expected in edits(session)[-1].text
        assert answered(session)


async def test_choosing_farsi_sticks(env):
    dp, bot, session, factory = env
    await press(dp, bot, CUSTOMER_ID, "lang_fa", language_code="en")
    assert "خوش آمدید" in edits(session)[-1].text

    # Telegram keeps reporting English, but the customer's choice wins.
    session.calls.clear()
    await press(dp, bot, CUSTOMER_ID, "main_menu", language_code="en")
    assert "خوش آمدید" in edits(session)[-1].text
    async with factory() as s:
        assert (await UserRepository(s).get_by_telegram_id(CUSTOMER_ID)).language_code == "fa"


async def test_new_farsi_telegram_user_starts_in_farsi(env):
    dp, bot, session, _ = env
    await press(dp, bot, CUSTOMER_ID + 1, "main_menu", language_code="fa")
    assert "خوش آمدید" in edits(session)[-1].text


async def test_unknown_button_is_answered(env):
    dp, bot, session, _ = env
    await press(dp, bot, CUSTOMER_ID, "something_old")
    answers = [c for c in session.calls if isinstance(c, AnswerCallbackQuery)]
    assert answers and "/start" in answers[-1].text
