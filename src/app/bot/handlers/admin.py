import uuid
from typing import Any, Dict, Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config.settings import get_settings
from src.app.db.models.order import OrderStatus
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.server_repo import ServerRepository
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
