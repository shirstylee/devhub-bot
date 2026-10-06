from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.i18n import tr
from bot.keyboards.language import language_keyboard
from bot.keyboards.main_menu import back_keyboard
from bot.middlewares.language import LANGUAGE_PROMPT
from bot.services.administrators import administrator_store
from bot.services.language import get_telegram_language, set_user_language
from bot.utils.messages import answer_callback, answer_tool_photo, edit_tool_photo
from bot.utils.premium_emoji import GLOBE


router = Router(name="language")


def automatic_language_text(lang: str) -> str:
    return tr(lang,
        f"{GLOBE.html} <b>Язык интерфейса</b>\n\n"
        "Язык бота определяется языком интерфейса Telegram и отдельно не сохраняется. "
        "Чтобы изменить его, смените язык в настройках Telegram. Для неподдерживаемых языков используется английский.",
        f"{GLOBE.html} <b>Interface language</b>\n\n"
        "The bot follows your Telegram interface language without saving a separate preference. "
        "To change it, change the language in Telegram settings. Unsupported languages use English.")


@router.message(Command("language"))
async def choose_language_command(message: Message, lang: str) -> None:
    if not message.from_user or not administrator_store.is_admin(message.from_user.id):
        await answer_tool_photo(message, "language", automatic_language_text(lang), reply_markup=back_keyboard(lang))
        return
    await answer_tool_photo(message, "language", LANGUAGE_PROMPT, reply_markup=language_keyboard(lang))


@router.callback_query(F.data == "menu:language")
async def choose_language_callback(callback: CallbackQuery, lang: str) -> None:
    if not administrator_store.is_admin(callback.from_user.id):
        await edit_tool_photo(callback, "language", automatic_language_text(lang), reply_markup=back_keyboard(lang))
        return
    await edit_tool_photo(callback, "language", LANGUAGE_PROMPT, reply_markup=language_keyboard(lang))


@router.callback_query(F.data.startswith("lang:"))
async def save_language(callback: CallbackQuery, state: FSMContext) -> None:
    if not administrator_store.is_admin(callback.from_user.id):
        lang = get_telegram_language(callback.from_user.language_code)
        await answer_callback(callback, tr(lang, "Язык определяется настройками Telegram", "Language follows your Telegram settings"))
        return
    language = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    try:
        saved_language = await set_user_language(callback.from_user.id, language)
    except (ValueError, PermissionError):
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
        reply_markup=main_menu_keyboard(saved_language, allow_language_choice=True),
    )
