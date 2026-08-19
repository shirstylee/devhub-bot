from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.language import language_keyboard
from bot.middlewares.language import LANGUAGE_PROMPT
from bot.services.language import set_user_language
from bot.utils.messages import answer_callback, answer_tool_photo, edit_tool_photo


router = Router(name="language")


@router.message(Command("language"))
async def choose_language_command(message: Message, lang: str) -> None:
    await answer_tool_photo(message, "language", LANGUAGE_PROMPT, reply_markup=language_keyboard(lang))


@router.callback_query(F.data == "menu:language")
async def choose_language_callback(callback: CallbackQuery, lang: str) -> None:
    await edit_tool_photo(callback, "language", LANGUAGE_PROMPT, reply_markup=language_keyboard(lang))


@router.callback_query(F.data.startswith("lang:"))
async def save_language(callback: CallbackQuery, state: FSMContext) -> None:
    language = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    try:
        saved_language = await set_user_language(callback.from_user.id, language)
    except ValueError:
        await answer_callback(callback)
        return

    await state.clear()
    await answer_callback(callback)
    if callback.message is None:
        return

    from bot.handlers.common import build_welcome_text
    from bot.keyboards.main_menu import main_menu_keyboard

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await answer_tool_photo(
        callback.message,
        "main",
        build_welcome_text(saved_language),
        reply_markup=main_menu_keyboard(saved_language),
    )
