from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main_menu import back_keyboard
from bot.i18n import tr
from bot.keyboards.shortener import shortener_keyboard
from bot.services.shortener import shorten_url
from bot.states import LinkShortenerStates
from bot.utils.messages import edit_tool_photo
from bot.utils.premium_emoji import ERROR, LINK, SUCCESS

router = Router(name="link_shortener")


@router.callback_query(F.data == "menu:shortener")
async def open_shortener(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(LinkShortenerStates.waiting_url)
    await edit_tool_photo(callback, "shortener", f"{LINK.html} <b>{tr(lang, 'Сократитель ссылок', 'Link shortener')}</b>\n\n{tr(lang, 'Отправьте длинную ссылку.', 'Send a long link.')}", reply_markup=back_keyboard(lang))


@router.message(LinkShortenerStates.waiting_url, F.text)
async def handle_url(message: Message, lang: str) -> None:
    try:
        short_url = await shorten_url(message.text or "")
    except ValueError as exc:
        await message.answer(f"{ERROR.html} {tr(lang, str(exc), 'The link shortening service is temporarily unavailable.')}", reply_markup=back_keyboard(lang))
        return
    except Exception:
        await message.answer(f"{ERROR.html} {tr(lang, 'Не удалось подключиться к сервису сокращения ссылок.', 'Could not connect to the link shortening service.')}", reply_markup=back_keyboard(lang))
        return
    await message.answer(f"{SUCCESS.html} <b>{tr(lang, 'Короткая ссылка', 'Short link')}</b>\n\n<code>{short_url}</code>", reply_markup=shortener_keyboard(short_url, lang))
