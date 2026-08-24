import uuid
from typing import Any, Dict, Optional
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.keyboards.customer_keyboards import (
    get_cancel_keyboard,
    get_main_menu_keyboard,
    get_products_keyboard,
    get_servers_keyboard,
    get_subscription_detail_keyboard,
    get_subscriptions_keyboard,
)
from src.app.bot.locales.strings import get_text
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
    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@customer_router.callback_query(F.data == "menu_buy")
async def callback_menu_buy(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    server_repo = ServerRepository(session)
    servers = await server_repo.list_enabled()

    if not servers:
        empty_msg = "⚠️ <b>No VPN servers are currently active.</b>\nPlease check back shortly or contact support." if lang != "fa" else "⚠️ <b>در حال حاضر هیچ سروری در دسترس نیست.</b>\nلطفا با پشتیبانی تماس بگیرید یا دقایقی دیگر مراجعه فرمایید."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("btn_back", lang), callback_data="main_menu")]
        ])
        if query.message:
            await query.message.edit_text(empty_msg, reply_markup=kb, parse_mode="HTML")
        await query.answer()
        return

    text = get_text("select_server", lang)
    kb = get_servers_keyboard(servers, lang)
    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


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
        await query.answer("Server not found", show_alert=True)
        return

    products = await product_repo.list_enabled()
    text = get_text("select_plan", lang, server_name=server.display_name)
    kb = get_products_keyboard(server_slug, products, lang)

    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@customer_router.callback_query(F.data.startswith("plan_"))
async def callback_select_plan(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    parts = query.data.split("_")
    server_slug = parts[1]
    plan_code = parts[2]

    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)

    server = await server_repo.get_by_slug(server_slug)
    product = await product_repo.get_by_code(plan_code)
    if not server or not product:
        await query.answer("Invalid selection", show_alert=True)
        return

    settings = get_settings()
    payment_instructions = (
        settings.PAYMENT_INSTRUCTIONS_FA if lang == "fa" else settings.PAYMENT_INSTRUCTIONS_EN
    )

    order = await order_repo.create_order(
        user_id=user.id,
        vpn_server_id=server.id,
        product_id=product.id,
        price_amount=product.price_amount,
        price_currency=product.price_currency,
        payment_instructions=payment_instructions,
    )
    await session.commit()

    await state.set_state(OrderFlowStates.awaiting_receipt)
    await state.update_data(order_id=str(order.id), server_slug=server_slug)

    text = get_text(
        "order_created",
        lang,
        order_code=order.public_order_code,
        server_name=server.display_name,
        plan_title=product.title,
        price=str(product.price_amount),
        currency=product.price_currency,
        instructions=payment_instructions,
    )
    kb = get_cancel_keyboard(lang)

    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@customer_router.callback_query(F.data == "cancel_order")
async def callback_cancel_order(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    await state.clear()
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"

    text = get_text("order_cancelled", lang)
    kb = get_main_menu_keyboard(lang)
    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


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

    text = "📋 <b>Your Subscriptions:</b>"
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
        if query.message:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await query.answer()
        return

    text = "📋 <b>Your Subscriptions:</b>"
    kb = get_subscriptions_keyboard(subs, lang)
    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


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
        await query.answer("Subscription not found", show_alert=True)
        return

    server = await server_repo.get_by_id(sub.vpn_server_id)
    server_name = server.display_name if server else "VPN Server"
    expiry_str = sub.expires_at.strftime("%Y-%m-%d %H:%M UTC")

    text = get_text(
        "subscription_detail",
        lang,
        server_name=server_name,
        status=sub.status.value.upper(),
        expires_at=expiry_str,
        label=sub.peer_label or "N/A",
    )
    is_active = (sub.status == SubscriptionStatus.ACTIVE)
    kb = get_subscription_detail_keyboard(str(sub.id), is_active=is_active, lang=lang)

    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@customer_router.callback_query(F.data.startswith("sub_dl_"))
@customer_router.callback_query(F.data.startswith("sub_redeliver_"))
async def callback_redeliver_subscription(query: CallbackQuery, data: Dict[str, Any]):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    settings = get_settings()

    raw_id = query.data.split("_")[-1]
    sub_id = uuid.UUID(raw_id)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)

    sub = await sub_repo.get_by_id(sub_id)
    if not sub or sub.user_id != user.id:
        await query.answer("Subscription not found", show_alert=True)
        return

    if sub.config_redelivery_count >= settings.CONFIG_REDELIVERY_LIMIT:
        await query.answer(
            f"Redelivery limit reached ({settings.CONFIG_REDELIVERY_LIMIT} times). Please contact support.",
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
    await query.answer("Configuration document has been queued for redelivery!", show_alert=True)


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
        await query.answer("Subscription not found", show_alert=True)
        return

    server = await server_repo.get_by_id(sub.vpn_server_id)
    if not server:
        await query.answer("Server not available", show_alert=True)
        return

    products = await product_repo.list_enabled()
    text = get_text("select_plan", lang, server_name=server.display_name)
    kb = get_products_keyboard(server.slug, products, lang)

    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()
