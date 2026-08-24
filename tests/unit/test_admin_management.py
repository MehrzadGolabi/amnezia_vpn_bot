import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.bot.handlers.admin import (
    cmd_admin_servers,
    callback_admin_toggle_server,
    cmd_admin_products,
    cmd_admin_user_lookup,
    cmd_admin_block_user,
    cmd_admin_unblock_user,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as s:
        yield s

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_servers_listing_and_toggle(session: AsyncSession):
    server_repo = ServerRepository(session)
    server = await server_repo.create_or_update(
        slug="nl-1",
        display_name="Netherlands 1",
        country_code="NL",
        country_name="Netherlands",
        host="nl.test",
        enabled=True,
    )

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    data = {"session": session}

    # 1. Listing servers
    msg = MagicMock(spec=Message)
    msg.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg.answer = AsyncMock()

    await cmd_admin_servers(msg, data)
    msg.answer.assert_called_once()
    assert "Netherlands 1" in msg.answer.call_args[0][0]

    # 2. Toggle server status
    query = MagicMock(spec=CallbackQuery)
    query.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    query.data = f"adm_tgl_srv_{server.id}"
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()

    await callback_admin_toggle_server(query, data)
    assert query.answer.call_count >= 1

    updated_server = await server_repo.get_by_id(server.id)
    assert updated_server.enabled is False


@pytest.mark.asyncio
async def test_admin_products_listing(session: AsyncSession):
    product_repo = ProductRepository(session)
    await product_repo.create_or_update(
        code="vpn-1m",
        title="1 Month Standard",
        duration_days=30,
        device_limit=1,
        price_amount=Decimal("6.00"),
        price_currency="USD",
    )

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    data = {"session": session}

    msg = MagicMock(spec=Message)
    msg.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg.answer = AsyncMock()

    await cmd_admin_products(msg, data)
    msg.answer.assert_called_once()
    assert "vpn-1m" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_user_lookup_and_blocking(session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.upsert_user(telegram_user_id=1234567, username="target_user")

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    data = {"session": session}

    # 1. Lookup
    msg_lookup = MagicMock(spec=Message)
    msg_lookup.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg_lookup.text = "/user 1234567"
    msg_lookup.answer = AsyncMock()

    await cmd_admin_user_lookup(msg_lookup, data)
    msg_lookup.answer.assert_called_once()
    assert "target_user" in msg_lookup.answer.call_args[0][0]

    # 2. Block
    msg_block = MagicMock(spec=Message)
    msg_block.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg_block.text = "/block 1234567"
    msg_block.answer = AsyncMock()

    await cmd_admin_block_user(msg_block, data)
    msg_block.answer.assert_called_once()

    updated_user = await user_repo.get_by_telegram_id(1234567)
    assert updated_user.is_blocked is True

    # 3. Unblock
    msg_unblock = MagicMock(spec=Message)
    msg_unblock.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg_unblock.text = "/unblock 1234567"
    msg_unblock.answer = AsyncMock()

    await cmd_admin_unblock_user(msg_unblock, data)
    msg_unblock.answer.assert_called_once()

    unblocked_user = await user_repo.get_by_telegram_id(1234567)
    assert unblocked_user.is_blocked is False
