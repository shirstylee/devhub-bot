import json
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards.main_menu import back_keyboard
from bot.i18n import tr
from bot.services.json_formatter import format_json
from bot.states import JsonStates
from bot.utils.messages import edit_tool_photo
from bot.utils.premium_emoji import CODE, ERROR, SUCCESS

router = Router(name="json_formatter")


@router.callback_query(F.data == "menu:json")
async def open_json_formatter(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(JsonStates.waiting_json)
    await edit_tool_photo(
        callback,
        "json",
        f"{CODE.html} <b>{tr(lang, 'Форматировать JSON', 'Format JSON')}</b>\n\n"
        + tr(lang, "Отправьте JSON, и я проверю валидность и красиво расставлю отступы.", "Send JSON to validate and pretty-print it."),
        reply_markup=back_keyboard(lang),
    )


@router.message(JsonStates.waiting_json, F.text)
async def handle_json(message: Message, lang: str) -> None:
    try:
        formatted = format_json(message.text or "")
    except json.JSONDecodeError as exc:
        await message.answer(f"{ERROR.html} <b>{tr(lang, 'JSON невалидный', 'Invalid JSON')}</b>\n\n<code>{escape(str(exc))}</code>", reply_markup=back_keyboard(lang))
        return

    if len(formatted) <= 3500:
        await message.answer(f"{SUCCESS.html} <b>{tr(lang, 'Готово', 'Done')}</b>\n\n<pre><code>{escape(formatted)}</code></pre>", reply_markup=back_keyboard(lang))
        return

    document = BufferedInputFile(formatted.encode("utf-8"), filename="formatted.json")
    await message.answer_document(document=document, caption=f"{SUCCESS.html} {tr(lang, 'JSON отформатирован.', 'JSON formatted.')}", reply_markup=back_keyboard(lang))
