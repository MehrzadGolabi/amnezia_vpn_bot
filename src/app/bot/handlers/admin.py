import uuid
from typing import Any, Dict, Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.states.admin_states import AdminTicketStates
from src.app.config.settings import get_settings
from src.app.db.models.order import OrderStatus
from src.app.db.models.ticket import SenderType, TicketStatus
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.ticket_repo import TicketRepository
from src.app.db.repositories.user_repo import UserRepository
from src.app.utils.logging import get_logger

logger = get_logger(__name__)
admin_router = Router(name="admin")


def is_admin(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    settings = get_settings()
    return user_id in settings.ADMIN_TELEGRAM_IDS


@admin_router.message(Command("admin"))
async def cmd_admin_dashboard(message: Message, data: Dict[str, Any]):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    session: AsyncSession = data.get("session")
    order_repo = OrderRepository(session)
    ticket_repo = TicketRepository(session)

    pending_orders = await order_repo.list_pending_orders()
    open_tickets = await ticket_repo.list_open_tickets()

    text = (
        f"👑 <b>AmneziaWG Admin Dashboard</b>\n\n"
        f"⏳ <b>Pending Receipts:</b> <code>{len(pending_orders)}</code>\n"
        f"📩 <b>Open Tickets:</b> <code>{len(open_tickets)}</code>\n\n"
        f"Commands:\n"
        f"• <code>/servers</code> - View/Toggle Server Capacity\n"
        f"• <code>/products</code> - View Products Catalogue\n"
        f"• <code>/user &lt;telegram_id&gt;</code> - Lookup User Details\n"
        f"• <code>/block &lt;telegram_id&gt;</code> - Suspend User\n"
        f"• <code>/unblock &lt;telegram_id&gt;</code> - Unsuspend User\n"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏳ Pending Orders", callback_data="adm_pending_orders"),
                InlineKeyboardButton(text="📩 Open Tickets", callback_data="adm_open_tickets"),
            ],
            [
                InlineKeyboardButton(text="🌐 Servers Status", callback_data="adm_servers_status"),
            ],
        ]
    )

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@admin_router.callback_query(F.data.startswith("adm_app_"))
async def callback_admin_approve_order(query: CallbackQuery, data: Dict[str, Any]):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return

    order_id = uuid.UUID(query.data.split("adm_app_")[1])
    session: AsyncSession = data.get("session")
    order_repo = OrderRepository(session)
    user_repo = UserRepository(session)

    order = await order_repo.get_by_id(order_id)
    if not order:
        await query.answer("Order not found", show_alert=True)
        return

    if order.status not in (OrderStatus.RECEIPT_SUBMITTED, OrderStatus.AWAITING_RECEIPT):
        await query.answer(f"Order was already {order.status.value}", show_alert=True)
        return

    success, sub, job = await order_repo.approve_order_atomic(
        order_id=order.id,
        admin_telegram_id=query.from_user.id,
    )
    await session.commit()

    if not success:
        await query.answer("Order was already approved", show_alert=True)
        return

    admin_tag = f"@{query.from_user.username}" if query.from_user.username else str(query.from_user.id)
    updated_caption = f"{query.message.caption or query.message.text or ''}\n\n✅ <b>Approved by {admin_tag}</b>"

    if query.message:
        try:
            if query.message.caption:
                await query.message.edit_caption(caption=updated_caption, parse_mode="HTML")
            elif query.message.text:
                await query.message.edit_text(text=updated_caption, parse_mode="HTML")
        except Exception:
            pass

    await query.answer("Order approved! Outbox provisioning job enqueued.", show_alert=True)

    # Notify Customer
    user = await user_repo.get_by_id(order.user_id)
    if user and query.bot:
        cust_msg = (
            f"✅ <b>Payment Approved!</b>\n\n"
            f"Your order <code>{order.public_order_code}</code> has been verified.\n"
            f"Your AmneziaWG VPN configuration is being generated and will be sent shortly."
        )
        try:
            await query.bot.send_message(chat_id=user.telegram_user_id, text=cust_msg, parse_mode="HTML")
        except Exception as e:
            logger.error("customer_approval_notification_failed", error=str(e))


@admin_router.callback_query(F.data.startswith("adm_rej_"))
async def callback_admin_reject_order(query: CallbackQuery, data: Dict[str, Any]):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return

    order_id = uuid.UUID(query.data.split("adm_rej_")[1])
    session: AsyncSession = data.get("session")
    order_repo = OrderRepository(session)
    user_repo = UserRepository(session)

    reason = "Receipt verification failed. Please contact support."
    success, order = await order_repo.reject_order(
        order_id=order_id,
        admin_telegram_id=query.from_user.id,
        reason=reason,
    )
    await session.commit()

    if not success or not order:
        await query.answer("Order could not be rejected", show_alert=True)
        return

    admin_tag = f"@{query.from_user.username}" if query.from_user.username else str(query.from_user.id)
    updated_caption = f"{query.message.caption or query.message.text or ''}\n\n❌ <b>Rejected by {admin_tag}</b>\nReason: {reason}"

    if query.message:
        try:
            if query.message.caption:
                await query.message.edit_caption(caption=updated_caption, parse_mode="HTML")
            elif query.message.text:
                await query.message.edit_text(text=updated_caption, parse_mode="HTML")
        except Exception:
            pass

    await query.answer("Order rejected.", show_alert=True)

    # Notify Customer
    user = await user_repo.get_by_id(order.user_id)
    if user and query.bot:
        cust_msg = (
            f"❌ <b>Payment Receipt Rejected</b>\n\n"
            f"Your order <code>{order.public_order_code}</code> receipt was rejected.\n"
            f"Reason: <i>{reason}</i>\n\n"
            f"Please check your payment details or contact our support team."
        )
        try:
            await query.bot.send_message(chat_id=user.telegram_user_id, text=cust_msg, parse_mode="HTML")
        except Exception as e:
            logger.error("customer_rejection_notification_failed", error=str(e))


@admin_router.callback_query(F.data == "adm_open_tickets")
async def callback_admin_open_tickets(query: CallbackQuery, data: Dict[str, Any]):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return

    session: AsyncSession = data.get("session")
    ticket_repo = TicketRepository(session)
    tickets = await ticket_repo.list_open_tickets()

    if not tickets:
        await query.answer("No open support tickets.", show_alert=True)
        return

    text = f"📩 <b>Open Support Tickets ({len(tickets)}):</b>\n\n"
    buttons = []
    for t in tickets[:10]:
        user_tag = f"@{t.user.username}" if t.user and t.user.username else f"{t.user.telegram_user_id if t.user else 'Unknown'}"
        text += f"• <code>{t.public_ticket_code}</code> | {user_tag} | {t.status.value}\n"
        buttons.append([InlineKeyboardButton(text=f"✍️ {t.public_ticket_code}", callback_data=f"adm_rep_tck_{t.id}")])

    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="adm_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@admin_router.callback_query(F.data.startswith("adm_rep_tck_"))
async def callback_admin_reply_ticket(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return

    ticket_id_str = query.data.split("adm_rep_tck_")[1]
    ticket_id = uuid.UUID(ticket_id_str)
    session: AsyncSession = data.get("session")
    ticket_repo = TicketRepository(session)

    ticket = await ticket_repo.get_by_id(ticket_id)
    if not ticket:
        await query.answer("Ticket not found", show_alert=True)
        return

    await state.set_state(AdminTicketStates.waiting_for_reply)
    await state.update_data(ticket_id=str(ticket.id))

    if query.message:
        await query.message.answer(
            f"✍️ <b>Replying to Ticket</b> <code>{ticket.public_ticket_code}</code>\n"
            f"Please enter your reply below:",
            parse_mode="HTML",
        )
    await query.answer()


@admin_router.message(AdminTicketStates.waiting_for_reply)
async def handle_admin_ticket_reply(message: Message, data: Dict[str, Any], state: FSMContext):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    session: AsyncSession = data.get("session")
    state_data = await state.get_data()
    ticket_id_str = state_data.get("ticket_id")
    if not ticket_id_str:
        await state.clear()
        return

    ticket_id = uuid.UUID(ticket_id_str)
    ticket_repo = TicketRepository(session)
    user_repo = UserRepository(session)

    ticket = await ticket_repo.get_by_id(ticket_id)
    if not ticket:
        await state.clear()
        return

    reply_body = message.text or message.caption or "Admin attachment response"
    file_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
    media_type = "photo" if message.photo else ("document" if message.document else None)

    await ticket_repo.add_message(
        ticket_id=ticket.id,
        sender_type=SenderType.ADMIN,
        sender_telegram_user_id=message.from_user.id,
        body=reply_body,
        telegram_chat_id=message.chat.id,
        telegram_message_id=message.message_id,
        attachment_file_id=file_id,
        attachment_type=media_type,
    )
    await session.commit()
    await state.clear()

    # Deliver to customer
    user = await user_repo.get_by_id(ticket.user_id)
    if user and message.bot:
        cust_text = (
            f"💬 <b>Support Reply:</b> <code>{ticket.public_ticket_code}</code>\n\n"
            f"{reply_body}\n\n"
            f"<i>You can reply to this message to continue the conversation.</i>"
        )
        try:
            await message.bot.send_message(chat_id=user.telegram_user_id, text=cust_text, parse_mode="HTML")
        except Exception as e:
            logger.error("admin_reply_delivery_failed", error=str(e))

    await message.answer(f"✅ Reply delivered to user for ticket <code>{ticket.public_ticket_code}</code>.", parse_mode="HTML")


@admin_router.callback_query(F.data.startswith("adm_cls_tck_"))
async def callback_admin_close_ticket(query: CallbackQuery, data: Dict[str, Any]):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return

    ticket_id_str = query.data.split("adm_cls_tck_")[1]
    ticket_id = uuid.UUID(ticket_id_str)
    session: AsyncSession = data.get("session")
    ticket_repo = TicketRepository(session)
    user_repo = UserRepository(session)

    ticket = await ticket_repo.close_ticket(ticket_id)
    await session.commit()

    if not ticket:
        await query.answer("Ticket not found", show_alert=True)
        return

    admin_tag = f"@{query.from_user.username}" if query.from_user.username else str(query.from_user.id)
    if query.message:
        try:
            await query.message.edit_text(
                f"🔒 <b>Ticket {ticket.public_ticket_code} Closed</b> by {admin_tag}.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await query.answer("Ticket closed.", show_alert=True)

    # Deliver to customer
    user = await user_repo.get_by_id(ticket.user_id)
    if user and query.bot:
        cust_text = (
            f"🔒 <b>Support Ticket Closed</b>\n\n"
            f"Ticket <code>{ticket.public_ticket_code}</code> has been marked as resolved.\n"
            f"Feel free to open a new support request if you need further help."
        )
        try:
            await query.bot.send_message(chat_id=user.telegram_user_id, text=cust_text, parse_mode="HTML")
        except Exception as e:
            logger.error("admin_close_ticket_delivery_failed", error=str(e))


@admin_router.message(Command("servers"))
@admin_router.callback_query(F.data == "adm_servers_status")
async def cmd_admin_servers(event: Any, data: Dict[str, Any]):
    user_id = event.from_user.id if event.from_user else None
    if not is_admin(user_id):
        return

    session: AsyncSession = data.get("session")
    server_repo = ServerRepository(session)
    servers = await server_repo.list_all()

    text = f"🌐 <b>VPN Servers Management ({len(servers)} total)</b>\n\n"
    buttons = []
    for s in servers:
        status_emoji = "🟢" if s.enabled else "🔴"
        active_count = await server_repo.count_active_subscriptions(s.id)
        cap = s.max_active_subscriptions or "∞"
        text += (
            f"{status_emoji} <b>{s.display_name}</b> (<code>{s.slug}</code>)\n"
            f"Host: <code>{s.host}:{s.ssh_port}</code> | Country: {s.country_code}\n"
            f"Active Peers: <code>{active_count}/{cap}</code>\n\n"
        )
        toggle_label = f"🔴 Disable {s.slug}" if s.enabled else f"🟢 Enable {s.slug}"
        buttons.append([InlineKeyboardButton(text=toggle_label, callback_data=f"adm_tgl_srv_{s.id}")])

    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="adm_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@admin_router.callback_query(F.data.startswith("adm_tgl_srv_"))
async def callback_admin_toggle_server(query: CallbackQuery, data: Dict[str, Any]):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return

    server_id = uuid.UUID(query.data.split("adm_tgl_srv_")[1])
    session: AsyncSession = data.get("session")
    server_repo = ServerRepository(session)

    server = await server_repo.get_by_id(server_id)
    if not server:
        await query.answer("Server not found", show_alert=True)
        return

    server.enabled = not server.enabled
    await session.commit()

    await query.answer(f"Server {server.slug} is now {'ENABLED' if server.enabled else 'DISABLED'}.", show_alert=True)
    await cmd_admin_servers(query, data)


@admin_router.message(Command("products"))
async def cmd_admin_products(message: Message, data: Dict[str, Any]):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    session: AsyncSession = data.get("session")
    product_repo = ProductRepository(session)
    products = await product_repo.list_enabled()

    text = f"📦 <b>Active Products Catalogue ({len(products)} active)</b>\n\n"
    for p in products:
        text += (
            f"• <b>{p.title}</b> (<code>{p.code}</code>)\n"
            f"  Price: <code>{p.price_amount} {p.price_currency}</code> | "
            f"Duration: <code>{p.duration_days} days</code> | "
            f"Devices: <code>{p.device_limit}</code>\n\n"
        )

    await message.answer(text, parse_mode="HTML")


@admin_router.message(Command("user"))
async def cmd_admin_user_lookup(message: Message, data: Dict[str, Any]):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: <code>/user &lt;telegram_user_id&gt;</code>", parse_mode="HTML")
        return

    target_tg_id = int(parts[1])
    session: AsyncSession = data.get("session")
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.get_by_telegram_id(target_tg_id)
    if not user:
        await message.answer(f"User with Telegram ID <code>{target_tg_id}</code> not found.", parse_mode="HTML")
        return

    subs = await sub_repo.get_all_by_user_id(user.id)
    block_status = "🔴 BLOCKED" if user.is_blocked else "🟢 ACTIVE"

    text = (
        f"👤 <b>User Profile:</b> <code>{user.telegram_user_id}</code>\n"
        f"Username: @{user.username or 'N/A'}\n"
        f"Language: <code>{user.language_code}</code>\n"
        f"Status: {block_status}\n"
        f"Total Subscriptions: <code>{len(subs)}</code>\n"
        f"Created At: <code>{user.created_at.strftime('%Y-%m-%d %H:%M UTC') if user.created_at else 'N/A'}</code>"
    )

    await message.answer(text, parse_mode="HTML")


@admin_router.message(Command("block"))
async def cmd_admin_block_user(message: Message, data: Dict[str, Any]):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: <code>/block &lt;telegram_user_id&gt;</code>", parse_mode="HTML")
        return

    target_tg_id = int(parts[1])
    session: AsyncSession = data.get("session")
    user_repo = UserRepository(session)

    user = await user_repo.get_by_telegram_id(target_tg_id)
    if not user:
        await message.answer(f"User <code>{target_tg_id}</code> not found.", parse_mode="HTML")
        return

    user.is_blocked = True
    await session.commit()
    await message.answer(f"🔒 User <code>{target_tg_id}</code> (@{user.username or 'N/A'}) has been suspended/blocked.", parse_mode="HTML")


@admin_router.message(Command("unblock"))
async def cmd_admin_unblock_user(message: Message, data: Dict[str, Any]):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: <code>/unblock &lt;telegram_user_id&gt;</code>", parse_mode="HTML")
        return

    target_tg_id = int(parts[1])
    session: AsyncSession = data.get("session")
    user_repo = UserRepository(session)

    user = await user_repo.get_by_telegram_id(target_tg_id)
    if not user:
        await message.answer(f"User <code>{target_tg_id}</code> not found.", parse_mode="HTML")
        return

    user.is_blocked = False
    await session.commit()
    await message.answer(f"🔓 User <code>{target_tg_id}</code> (@{user.username or 'N/A'}) has been unblocked.", parse_mode="HTML")
