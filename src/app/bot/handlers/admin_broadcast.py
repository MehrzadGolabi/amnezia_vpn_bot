"""/broadcast: send one message to active users, inactive users, or everyone.

The admin picks an audience, sends the message (text, photo, file, anything), sees it
copied back as a preview, and confirms. The bot then copies it to each user in the
background, under Telegram's rate limit, and reports how many got it.
"""
import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.handlers.admin import _audit, is_admin
from src.app.bot.states.admin_states import AdminBroadcastStates
from src.app.db.repositories.user_repo import Audience, UserRepository
from src.app.utils.logging import get_logger

logger = get_logger(__name__)
admin_broadcast_router = Router(name="admin_broadcast")

PICK_PREFIX = "adm_bc_aud_"
CONFIRM = "adm_bc_send"
CANCEL = "adm_bc_cancel"
# Telegram allows about 30 messages a second to different chats; stay well under it.
SEND_INTERVAL_SECONDS = 0.05
MAX_RETRY_AFTER_SECONDS = 60

AUDIENCE_NAMES = {
    Audience.ACTIVE: "active users",
    Audience.INACTIVE: "inactive users",
    Audience.ALL: "all users",
}
# Kept so running broadcasts aren't garbage-collected; tests also await them from here.
running_broadcasts: Set[asyncio.Task] = set()


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data=CANCEL)]])


async def _audience_menu(session: AsyncSession) -> Tuple[str, InlineKeyboardMarkup]:
    repo = UserRepository(session)
    counts = {a: len(await repo.list_audience_telegram_ids(a)) for a in Audience}
    text = (
        "📣 <b>Broadcast</b>\n\n"
        f"🟢 Active: <code>{counts[Audience.ACTIVE]}</code> (a subscription that hasn't expired)\n"
        f"⚪ Inactive: <code>{counts[Audience.INACTIVE]}</code> (no running subscription, "
        "including people who never bought)\n"
        f"👥 Everyone: <code>{counts[Audience.ALL]}</code>\n\n"
        "Blocked users are left out. Who should get the message?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟢 Active ({counts[Audience.ACTIVE]})",
                              callback_data=PICK_PREFIX + Audience.ACTIVE.value),
         InlineKeyboardButton(text=f"⚪ Inactive ({counts[Audience.INACTIVE]})",
                              callback_data=PICK_PREFIX + Audience.INACTIVE.value)],
        [InlineKeyboardButton(text=f"👥 Everyone ({counts[Audience.ALL]})",
                              callback_data=PICK_PREFIX + Audience.ALL.value)],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=CANCEL)],
    ])
    return text, kb


@admin_broadcast_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, data: Dict[str, Any], state: FSMContext):
    if not message.from_user or not is_admin(message.from_user.id):
        return
    await state.clear()
    text, kb = await _audience_menu(data.get("session"))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@admin_broadcast_router.callback_query(F.data.startswith(PICK_PREFIX))
async def callback_pick_audience(query: CallbackQuery, state: FSMContext):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return
    try:
        audience = Audience(query.data[len(PICK_PREFIX):])
    except ValueError:
        await query.answer("Unknown audience", show_alert=True)
        return
    await state.set_state(AdminBroadcastStates.waiting_for_message)
    await state.update_data(audience=audience.value)
    if query.message:
        await query.message.answer(
            f"✍️ Send the message for <b>{AUDIENCE_NAMES[audience]}</b>. Text, a photo, a file "
            "or anything else is sent exactly as you send it. Send /cancel to stop.",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
    await query.answer()


@admin_broadcast_router.message(AdminBroadcastStates.waiting_for_message)
async def handle_broadcast_message(message: Message, data: Dict[str, Any], state: FSMContext):
    if not message.from_user or not is_admin(message.from_user.id):
        return
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.answer("Broadcast cancelled.")
        return

    audience = Audience((await state.get_data()).get("audience", Audience.ALL.value))
    count = len(await UserRepository(data.get("session")).list_audience_telegram_ids(audience))
    if count == 0:
        await state.clear()
        await message.answer(f"There are no {AUDIENCE_NAMES[audience]} to send to.")
        return

    await state.set_state(AdminBroadcastStates.confirming)
    await state.update_data(from_chat_id=message.chat.id, message_id=message.message_id)
    # The preview is the same copy each user will get.
    await message.bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id,
                                   message_id=message.message_id)
    await message.answer(
        f"☝️ This is what <b>{count}</b> {AUDIENCE_NAMES[audience]} will get. Send it?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"📣 Send to {count}", callback_data=CONFIRM),
            InlineKeyboardButton(text="❌ Cancel", callback_data=CANCEL),
        ]]),
        parse_mode="HTML",
    )


@admin_broadcast_router.callback_query(F.data == CANCEL)
async def callback_cancel(query: CallbackQuery, state: FSMContext):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return
    await state.clear()
    if query.message:
        try:
            await query.message.edit_text("Broadcast cancelled.")
        except TelegramAPIError:
            pass
    await query.answer()


@admin_broadcast_router.callback_query(F.data == CONFIRM)
async def callback_confirm(query: CallbackQuery, data: Dict[str, Any], state: FSMContext):
    if not query.from_user or not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return
    stored = await state.get_data()
    if await state.get_state() != AdminBroadcastStates.confirming.state or "message_id" not in stored:
        await query.answer("This broadcast was already sent or cancelled.", show_alert=True)
        return
    # Clear first, so a double tap can't send it twice.
    await state.clear()

    audience = Audience(stored["audience"])
    session: AsyncSession = data.get("session")
    recipients = await UserRepository(session).list_audience_telegram_ids(audience)
    await _audit(session, query.from_user.id, "broadcast.sent", "broadcast", None,
                 audience=audience.value, recipients=len(recipients))
    await session.commit()

    if query.message:
        try:
            await query.message.edit_text(
                f"📣 Sending to {len(recipients)} {AUDIENCE_NAMES[audience]}. I'll report when it's done.")
        except TelegramAPIError:
            pass
    await query.answer()

    task = asyncio.create_task(_broadcast_and_report(
        query.bot, recipients, stored["from_chat_id"], stored["message_id"],
        report_chat_id=query.from_user.id, audience=audience,
    ))
    running_broadcasts.add(task)
    task.add_done_callback(running_broadcasts.discard)


async def send_broadcast(bot: Bot, recipients: List[int], from_chat_id: int, message_id: int,
                         interval: float = SEND_INTERVAL_SECONDS) -> Tuple[int, int]:
    """Copy one message to each recipient. Returns (sent, failed).

    A user who blocked the bot, or deleted their account, counts as failed and the
    rest still get it. When Telegram says to slow down, wait as asked and try again.
    """
    sent = failed = 0
    for chat_id in recipients:
        for attempt in range(3):
            try:
                await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
                sent += 1
                break
            except TelegramRetryAfter as e:
                if attempt == 2:
                    failed += 1
                    break
                await asyncio.sleep(min(e.retry_after, MAX_RETRY_AFTER_SECONDS))
            except TelegramAPIError as e:
                logger.info("broadcast_delivery_failed", chat_id=chat_id, error=str(e))
                failed += 1
                break
        if interval:
            await asyncio.sleep(interval)
    return sent, failed


async def _broadcast_and_report(bot: Bot, recipients: List[int], from_chat_id: int, message_id: int,
                                report_chat_id: int, audience: Audience,
                                interval: Optional[float] = None) -> None:
    try:
        sent, failed = await send_broadcast(
            bot, recipients, from_chat_id, message_id,
            SEND_INTERVAL_SECONDS if interval is None else interval,
        )
        report = f"✅ Broadcast to {AUDIENCE_NAMES[audience]} finished: {sent} delivered"
        if failed:
            report += f", {failed} failed (mostly people who blocked the bot)"
        report += "."
        logger.info("broadcast_finished", audience=audience.value, sent=sent, failed=failed)
    except Exception as e:  # report instead of dying silently in the background
        logger.error("broadcast_crashed", error=str(e))
        report = f"🚨 Broadcast to {AUDIENCE_NAMES[audience]} stopped: {e}"
    try:
        await bot.send_message(chat_id=report_chat_id, text=report)
    except TelegramAPIError as e:
        logger.error("broadcast_report_failed", error=str(e))
