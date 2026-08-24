from typing import Any, Dict, Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.keyboards.customer_keyboards import get_cancel_keyboard, get_main_menu_keyboard
from src.app.bot.locales.strings import get_text
from src.app.bot.states.support_states import SupportStates
from src.app.config.settings import get_settings
from src.app.db.models.ticket import SenderType
from src.app.db.models.user import User
from src.app.db.repositories.ticket_repo import TicketRepository
from src.app.utils.logging import get_logger

logger = get_logger(__name__)
support_router = Router(name="support")


@support_router.message(Command("support"))
async def cmd_support(message: Message, data: Dict[str, Any], state: FSMContext):
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"

    await state.set_state(SupportStates.writing_message)
    text = (
        "💬 <b>Customer Support</b>\n\n"
        "Please describe your question or issue below. You can also attach photos or documents if needed."
        if lang == "en"
        else "💬 <b>پشتیبانی مشتریان</b>\n\nلطفا پیام، سوال یا مشکل خود را ارسال نمایید:"
    )
    kb = get_cancel_keyboard(lang)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@support_router.callback_query(F.data == "menu_support")
async def callback_menu_support(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    user: User = data.get("db_user")
    lang = user.language_code if user else "en"

    await state.set_state(SupportStates.writing_message)
    text = (
        "💬 <b>Customer Support</b>\n\n"
        "Please describe your question or issue below. You can also attach photos or documents if needed."
        if lang == "en"
        else "💬 <b>پشتیبانی مشتریان</b>\n\nلطفا پیام، سوال یا مشکل خود را ارسال نمایید:"
    )
    kb = get_cancel_keyboard(lang)
    if query.message:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@support_router.message(SupportStates.writing_message)
async def handle_support_message(message: Message, data: Dict[str, Any], state: FSMContext):
    user: User = data.get("db_user")
    session: AsyncSession = data.get("session")
    lang = user.language_code if user else "en"

    ticket_repo = TicketRepository(session)
    active_ticket = await ticket_repo.get_active_ticket_for_user(user.id)

    body_text = message.text or message.caption or "Media attachment"
    file_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
    media_type = "photo" if message.photo else ("document" if message.document else None)

    if not active_ticket:
        active_ticket = await ticket_repo.create_ticket(
            user_id=user.id,
            subject=body_text[:40],
            initial_message=body_text,
            sender_telegram_user_id=user.telegram_user_id,
            attachment_file_id=file_id,
            attachment_type=media_type,
        )
    else:
        await ticket_repo.add_message(
            ticket_id=active_ticket.id,
            sender_type=SenderType.CUSTOMER,
            sender_telegram_user_id=user.telegram_user_id,
            body=body_text,
            telegram_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            attachment_file_id=file_id,
            attachment_type=media_type,
        )

    await session.commit()
    await state.clear()

    # Forward alert to admin chat
    settings = get_settings()
    if settings.ADMIN_CHAT_ID and message.bot:
        admin_text = (
            f"📩 <b>Support Message:</b> <code>{active_ticket.public_ticket_code}</code>\n"
            f"👤 <b>From:</b> <code>{user.telegram_user_id}</code> (@{user.username or 'N/A'})\n\n"
            f"{body_text}"
        )
        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✍️ Reply", callback_data=f"adm_rep_tck_{active_ticket.id}"),
                InlineKeyboardButton(text="🔒 Close", callback_data=f"adm_cls_tck_{active_ticket.id}"),
            ]]
        )
        try:
            await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("admin_ticket_forward_failed", error=str(e))

    # Respond to customer
    reply_text = (
        f"✅ <b>Message Received!</b>\n\nTicket Code: <code>{active_ticket.public_ticket_code}</code>\n"
        f"Our support team has been notified and will reply shortly."
        if lang == "en"
        else f"✅ <b>پیام شما ثبت شد!</b>\n\nکد پیگیری: <code>{active_ticket.public_ticket_code}</code>\nپاسخ پشتیبانی به زودی برای شما ارسال خواهد شد."
    )
    kb = get_main_menu_keyboard(lang)
    await message.answer(reply_text, reply_markup=kb, parse_mode="HTML")
