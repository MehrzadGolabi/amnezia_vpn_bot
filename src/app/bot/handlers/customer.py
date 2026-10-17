import uuid
from typing import Any, Dict, Optional
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.keyboards.customer_keyboards import (
    get_cancel_keyboard,
    get_language_keyboard,
    get_main_menu_keyboard,
    get_products_keyboard,
    get_servers_keyboard,
    get_subscription_detail_keyboard,
    get_subscriptions_keyboard,
)
from src.app.bot.locales.strings import get_text, normalize_lang, product_title, server_name
from src.app.bot.ui import show
from src.app.bot.usage import usage_text
from src.app.bot.states.order_states import OrderFlowStates
from src.app.config.settings import get_settings
from src.app.db.models.job import JobType
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.models.user import User
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.utils.logging import get_logger

logger = get_logger(__name__)
customer_router = Router(name="customer")


@customer_router.message(CommandStart())
@customer_router.message(Command("menu"))
async def cmd_start(message: Message, data: Dict[str, Any], state: Optional[FSMContext] = None):
    if state:
        await state.clear()
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"
    text = get_text("welcome", lang)
    kb = get_main_menu_keyboard(lang)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@customer_router.callback_query(F.data == "main_menu")
async def callback_main_menu(query: CallbackQuery, data: Dict[str, Any], state: Optional[FSMContext] = None):
    if state:
        await state.clear()
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"
    text = get_text("welcome", lang)
    kb = get_main_menu_keyboard(lang)
    await show(query, text, kb)


@customer_router.callback_query(F.data == "menu_buy")
async def callback_menu_buy(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    server_repo = ServerRepository(session)
    servers = await server_repo.list_enabled()

    if not servers:
        empty_msg = get_text("no_servers", lang)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("btn_back", lang), callback_data="main_menu")]
        ])
        await show(query, empty_msg, kb)
        return

    text = get_text("select_server", lang)
    kb = get_servers_keyboard(servers, lang)
    await show(query, text, kb)


@customer_router.callback_query(F.data.startswith("srv_"))
async def callback_select_server(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    server_slug = query.data.split("srv_")[1]
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)

    server = await server_repo.get_by_slug(server_slug)
    if not server:
        await query.answer(get_text("server_not_found", lang), show_alert=True)
        return

    products = await product_repo.list_enabled()
    text = get_text("select_plan", lang, server_name=server_name(server, lang))
    kb = get_products_keyboard(server_slug, products, lang)

    await show(query, text, kb)


@customer_router.callback_query(F.data.startswith("plan_"))
async def callback_select_plan(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    parts = query.data.split("_")
    server = await ServerRepository(session).get_by_slug(parts[1])
    product = await ProductRepository(session).get_by_code(parts[2])
    if not server or not product:
        await query.answer(get_text("invalid_selection", lang), show_alert=True)
        return
    await _start_order(query, data, state, server, product)


@customer_router.callback_query(F.data.startswith("rnw_"))
async def callback_select_renewal_plan(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    """A plan picked from Renew: the order adds time to this subscription instead of making a new one."""
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    _, sub_hex, plan_code = query.data.split("_", 2)
    sub = await SubscriptionRepository(session).get_by_id(uuid.UUID(hex=sub_hex))
    if not sub or sub.user_id != user.id:
        await query.answer(get_text("subscription_not_found", lang), show_alert=True)
        return
    server = await ServerRepository(session).get_by_id(sub.vpn_server_id)
    product = await ProductRepository(session).get_by_code(plan_code)
    if not server or not product:
        await query.answer(get_text("invalid_selection", lang), show_alert=True)
        return
    await _start_order(query, data, state, server, product, renews=sub)


async def _start_order(query: CallbackQuery, data: Dict[str, Any], state: FSMContext, server, product, renews=None):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    settings = get_settings()
    payment_instructions = (
        settings.PAYMENT_INSTRUCTIONS_FA if normalize_lang(lang) == "fa" else settings.PAYMENT_INSTRUCTIONS_EN
    )

    order = await OrderRepository(session).create_order(
        user_id=user.id,
        vpn_server_id=server.id,
        product_id=product.id,
        price_amount=product.price_amount,
        price_currency=product.price_currency,
        payment_instructions=payment_instructions,
        renews_subscription_id=renews.id if renews else None,
    )
    await session.commit()

    await state.set_state(OrderFlowStates.awaiting_receipt)
    await state.update_data(order_id=str(order.id), server_slug=server.slug)

    text = get_text(
        "order_created",
        lang,
        order_code=order.public_order_code,
        server_name=server_name(server, lang),
        plan_title=product_title(product, lang),
        price=str(product.price_amount),
        currency=product.price_currency,
        instructions=payment_instructions,
    )
    if renews:
        text = get_text("renewal_of", lang, label=renews.peer_label or "") + "\n" + text
    await show(query, text, get_cancel_keyboard(lang))


@customer_router.callback_query(F.data == "cancel_order")
async def callback_cancel_order(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    await state.clear()
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"

    text = get_text("order_cancelled", lang)
    kb = get_main_menu_keyboard(lang)
    await show(query, text, kb)


async def _renewal_line(session: AsyncSession, order) -> str:
    if not order.renews_subscription_id:
        return ""
    sub = await SubscriptionRepository(session).get_by_id(order.renews_subscription_id)
    return f"🔄 <b>Renews:</b> <code>{sub.peer_label if sub else order.renews_subscription_id}</code>\n"


@customer_router.message(OrderFlowStates.awaiting_receipt, F.photo | F.document)
async def handle_receipt_upload(message: Message, data: Dict[str, Any], state: FSMContext):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    state_data = await state.get_data()
    order_id_str = state_data.get("order_id")
    if not order_id_str:
        await state.clear()
        return

    order_id = uuid.UUID(order_id_str)
    order_repo = OrderRepository(session)
    order = await order_repo.get_by_id(order_id)
    if not order:
        await state.clear()
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    media_type = "photo" if message.photo else "document"
    note = message.caption

    await order_repo.submit_receipt(
        order_id=order.id,
        file_id=file_id,
        message_id=message.message_id,
        chat_id=message.chat.id,
        media_type=media_type,
        note=note,
    )
    await session.commit()
    await state.clear()

    # Alert Admin Chat if configured
    settings = get_settings()
    if settings.ADMIN_CHAT_ID and message.bot:
        admin_text = (
            f"🔔 <b>New Receipt Submitted</b>\n\n"
            f"🧾 <b>Order Code:</b> <code>{order.public_order_code}</code>\n"
            f"👤 <b>User:</b> <code>{user.telegram_user_id}</code> (@{user.username or 'N/A'})\n"
            f"💰 <b>Amount:</b> <code>{order.price_amount_snapshot} {order.currency_snapshot}</code>\n"
            f"{await _renewal_line(session, order)}"
            f"📝 <b>Note:</b> {note or 'None'}\n\n"
            f"Action: Review via Admin Panel."
        )
        try:
            admin_kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_app_{order.id}"),
                    InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_rej_{order.id}"),
                ]]
            )
            if message.photo:
                await message.bot.send_photo(
                    chat_id=settings.ADMIN_CHAT_ID,
                    photo=file_id,
                    caption=admin_text,
                    reply_markup=admin_kb,
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_document(
                    chat_id=settings.ADMIN_CHAT_ID,
                    document=file_id,
                    caption=admin_text,
                    reply_markup=admin_kb,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error("admin_receipt_forward_failed", error=str(e))

    # Respond to customer
    text = get_text("receipt_received", lang, order_code=order.public_order_code)
    kb = get_main_menu_keyboard(lang)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@customer_router.message(Command("my_vpn"))
async def cmd_my_vpn(message: Message, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    sub_repo = SubscriptionRepository(session)
    subs = await sub_repo.get_all_by_user_id(user.id)

    if not subs:
        text = get_text("no_subscriptions", lang)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text=get_text("btn_buy_vpn", lang), callback_data="menu_buy"),
            ]]
        )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    text = get_text("your_subscriptions", lang)
    kb = get_subscriptions_keyboard(subs, lang)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@customer_router.callback_query(F.data == "menu_subs")
async def callback_menu_subs(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    sub_repo = SubscriptionRepository(session)
    subs = await sub_repo.get_all_by_user_id(user.id)

    if not subs:
        text = get_text("no_subscriptions", lang)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text=get_text("btn_buy_vpn", lang), callback_data="menu_buy"),
                InlineKeyboardButton(text=get_text("btn_back", lang), callback_data="main_menu"),
            ]]
        )
        await show(query, text, kb)
        return

    text = get_text("your_subscriptions", lang)
    kb = get_subscriptions_keyboard(subs, lang)
    await show(query, text, kb)


@customer_router.callback_query(F.data.startswith("sub_view_"))
async def callback_view_subscription(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    sub_id = uuid.UUID(query.data.split("sub_view_")[1])
    sub_repo = SubscriptionRepository(session)
    server_repo = ServerRepository(session)

    sub = await sub_repo.get_by_id(sub_id)
    if not sub or sub.user_id != user.id:
        await query.answer(get_text("subscription_not_found", lang), show_alert=True)
        return

    server = await server_repo.get_by_id(sub.vpn_server_id)
    location = server_name(server, lang) if server else "VPN"
    expiry_str = sub.expires_at.strftime("%Y-%m-%d %H:%M UTC")

    text = get_text(
        "subscription_detail",
        lang,
        server_name=location,
        status=get_text(f"status_{sub.status.value}", lang),
        expires_at=expiry_str,
        label=sub.peer_label or "N/A",
    )
    usage = await usage_text(data.get("provisioner"), server, sub, lang)
    if usage:
        text += "\n" + usage
    is_active = (sub.status == SubscriptionStatus.ACTIVE)
    kb = get_subscription_detail_keyboard(str(sub.id), is_active=is_active, lang=lang)

    await show(query, text, kb)


@customer_router.callback_query(F.data.startswith("sub_dl_"))
@customer_router.callback_query(F.data.startswith("sub_redeliver_"))
async def callback_redeliver_subscription(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"
    settings = get_settings()

    raw_id = query.data.split("_")[-1]
    sub_id = uuid.UUID(raw_id)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)

    sub = await sub_repo.get_by_id(sub_id)
    if not sub or sub.user_id != user.id:
        await query.answer(get_text("subscription_not_found", lang), show_alert=True)
        return

    if sub.config_redelivery_count >= settings.CONFIG_REDELIVERY_LIMIT:
        await query.answer(
            get_text("redelivery_limit", lang, limit=settings.CONFIG_REDELIVERY_LIMIT),
            show_alert=True,
        )
        return

    # Enqueue redeliver job in outbox
    await job_repo.enqueue_job(
        job_type=JobType.REDELIVER_CONFIG,
        aggregate_type="subscription",
        aggregate_id=sub.id,
        payload={"redelivery": True},
    )
    await session.commit()
    await query.answer(get_text("redelivery_queued", lang), show_alert=True)


@customer_router.callback_query(F.data.startswith("renew_"))
async def callback_renew_subscription(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    raw_id = query.data.split("renew_")[1]
    sub_id = uuid.UUID(raw_id)
    sub_repo = SubscriptionRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)

    sub = await sub_repo.get_by_id(sub_id)
    if not sub or sub.user_id != user.id:
        await query.answer(get_text("subscription_not_found", lang), show_alert=True)
        return

    server = await server_repo.get_by_id(sub.vpn_server_id)
    if not server:
        await query.answer(get_text("server_unavailable", lang), show_alert=True)
        return

    products = await product_repo.list_enabled()
    text = get_text("select_plan", lang, server_name=server_name(server, lang))
    kb = get_products_keyboard(server.slug, products, lang, renew_subscription_id=sub.id)

    await show(query, text, kb)


@customer_router.message(Command("language"))
async def cmd_language(message: Message, data: Dict[str, Any]):
    await message.answer(get_text("choose_language"), reply_markup=get_language_keyboard(), parse_mode="HTML")


@customer_router.callback_query(F.data == "menu_lang")
async def callback_menu_language(query: CallbackQuery, data: Dict[str, Any]):
    await show(query, get_text("choose_language"), get_language_keyboard())


@customer_router.callback_query(F.data.in_({"lang_en", "lang_fa"}))
async def callback_set_language(query: CallbackQuery, data: Dict[str, Any], state: Optional[FSMContext] = None):
    if state:
        await state.clear()
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = query.data.split("_", 1)[1]
    if user and session:
        user.language_code = lang
        await session.commit()
    await show(query, get_text("welcome", lang), get_main_menu_keyboard(lang))


# Included after every other router, so it only sees presses no handler claimed, such as
# buttons on old messages. Answering stops the button from spinning.
fallback_router = Router(name="fallback")


@fallback_router.callback_query()
async def callback_unhandled(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"
    logger.warning("unhandled_callback", callback_data=query.data)
    await query.answer(get_text("button_expired", lang), show_alert=True)
