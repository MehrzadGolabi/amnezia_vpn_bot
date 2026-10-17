from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def show(query: CallbackQuery, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Replace the menu a button was pressed on, and always answer the button press.

    Telegram refuses to edit a message whose content wouldn't change, a photo or file
    (no text to edit), or one that is too old. In those cases the menu is sent as a new
    message instead, so a button never just spins.
    """
    if query.message:
        try:
            await query.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await query.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    try:
        await query.answer()
    except TelegramBadRequest:
        pass  # already answered, or the press is too old to answer
