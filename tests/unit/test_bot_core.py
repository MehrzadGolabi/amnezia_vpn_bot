import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import User as TelegramUser, Message, CallbackQuery, InlineKeyboardMarkup

from src.app.db.models.user import User
from src.app.db.models.server import VPNServer
from src.app.db.models.product import Product
from src.app.bot.locales.strings import get_text
from src.app.bot.middleware.user_middleware import UserMiddleware
from src.app.bot.middleware.throttling_middleware import ThrottlingMiddleware
from src.app.bot.keyboards.customer_keyboards import (
    get_main_menu_keyboard,
    get_servers_keyboard,
    get_products_keyboard,
    get_cancel_keyboard,
)


def test_localization_strings():
    assert "AmneziaWG" in get_text("welcome", "en")
    assert "خوش آمدید" in get_text("welcome", "fa")
    assert get_text("btn_buy_vpn", "en") == "🛒 Buy VPN"
    assert get_text("btn_buy_vpn", "fa") == "🛒 خرید اشتراک"
    assert get_text("non_existent_key", "en") == "non_existent_key"


def test_customer_keyboards():
    # Main menu
    kb_main = get_main_menu_keyboard("en")
    assert isinstance(kb_main, InlineKeyboardMarkup)
    assert any("Buy VPN" in btn.text for row in kb_main.inline_keyboard for btn in row)

    # Servers list
    servers = [
        VPNServer(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test", enabled=True),
        VPNServer(slug="tr-1", display_name="Turkey", country_code="TR", country_name="Turkey", host="tr.test", enabled=True),
    ]
    kb_servers = get_servers_keyboard(servers, "en")
    assert len(kb_servers.inline_keyboard) >= 2

    # Products list
    products = [
        Product(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR", enabled=True),
    ]
    kb_prods = get_products_keyboard("de-1", products, "en")
    assert any("1 Month" in btn.text for row in kb_prods.inline_keyboard for btn in row)

    # Cancel
    kb_cancel = get_cancel_keyboard("en")
    assert isinstance(kb_cancel, InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_user_middleware():
    mock_session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session_factory.return_value = mock_session

    mock_repo = AsyncMock()
    mock_db_user = User(id=uuid.uuid4(), telegram_user_id=12345, is_blocked=False)
    mock_repo.upsert_user.return_value = mock_db_user

    middleware = UserMiddleware(session_factory=mock_session_factory, user_repo_cls=lambda s: mock_repo)

    tg_user = TelegramUser(id=12345, is_bot=False, first_name="John", username="johndoe", language_code="en")
    mock_event = MagicMock(spec=Message)
    mock_event.from_user = tg_user

    handler = AsyncMock(return_value="handler_result")
    data = {}

    result = await middleware(handler, mock_event, data)
    assert result == "handler_result"
    assert data["db_user"] == mock_db_user

    # Blocked user
    mock_db_user.is_blocked = True
    blocked_result = await middleware(handler, mock_event, data)
    assert blocked_result is None


@pytest.mark.asyncio
async def test_throttling_middleware():
    middleware = ThrottlingMiddleware(rate_limit_seconds=1.0)
    tg_user = TelegramUser(id=99999, is_bot=False, first_name="Spammer")
    mock_event = MagicMock(spec=Message)
    mock_event.from_user = tg_user

    handler = AsyncMock(return_value="ok")
    data = {}

    # First call ok
    res1 = await middleware(handler, mock_event, data)
    assert res1 == "ok"

    # Immediate second call throttled
    res2 = await middleware(handler, mock_event, data)
    assert res2 is None
from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.bot.keyboards.customer_keyboards import get_subscriptions_keyboard, get_subscription_detail_keyboard


def test_customer_keyboards_expanded():
    subs = [
        Subscription(id=uuid.uuid4(), peer_label="user-1-de", status=SubscriptionStatus.ACTIVE),
        Subscription(id=uuid.uuid4(), peer_label="user-1-tr", status=SubscriptionStatus.EXPIRED),
    ]
    kb_subs = get_subscriptions_keyboard(subs, "en")
    assert len(kb_subs.inline_keyboard) == 3

    # Detail active
    kb_detail_active = get_subscription_detail_keyboard("sub-123", is_active=True, lang="en")
    assert any("Download Config" in btn.text for row in kb_detail_active.inline_keyboard for btn in row)

    # Detail inactive
    kb_detail_inactive = get_subscription_detail_keyboard("sub-123", is_active=False, lang="fa")
    assert not any("Download Config" in btn.text for row in kb_detail_inactive.inline_keyboard for btn in row)


def test_localization_formatting():
    msg = get_text("order_created", "en", order_code="ORD-1", server_name="Germany", plan_title="1 Month", price="5", currency="EUR", instructions="Pay card")
    assert "ORD-1" in msg
    assert "Germany" in msg

    # Fallback to default lang
    msg_other = get_text("welcome", "es")
    assert "AmneziaWG" in msg_other
