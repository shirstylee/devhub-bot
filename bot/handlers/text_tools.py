from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.i18n import tr
from bot.keyboards.text_tools import text_result_keyboard, text_tools_keyboard
from bot.services.text_tools import OPERATIONS, TextToolError, transform_text
from bot.states import TextToolsStates
from bot.utils.messages import edit_message_text, edit_tool_photo
from bot.utils.premium_emoji import ERROR, SUCCESS, TEXT


router = Router(name="text_tools")


def _intro(lang: str) -> str:
    return (
        f"{TEXT.html} <b>{tr(lang, 'Текстовые инструменты', 'Text tools')}</b>\n\n"
        + tr(
            lang,
            "Кодируйте Base64 и URL-компоненты или вычисляйте SHA-хеши локально внутри бота.",
            "Encode Base64 and URL components or calculate SHA hashes locally inside the bot.",
        )
    )


@router.callback_query(F.data == "menu:text_tools")
async def open_text_tools(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await edit_tool_photo(callback, "text_tools", _intro(lang), reply_markup=text_tools_keyboard(lang))


@router.callback_query(F.data == "text:home")
async def show_text_tools(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await edit_message_text(callback, _intro(lang), reply_markup=text_tools_keyboard(lang))


@router.callback_query(F.data.startswith("text:op:"))
async def select_operation(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    operation = (callback.data or "").removeprefix("text:op:")
    if operation not in OPERATIONS:
        await callback.answer()
        return
    await state.update_data(text_operation=operation)
    await state.set_state(TextToolsStates.waiting_input)
    await edit_message_text(
        callback,
        f"{TEXT.html} <b>{tr(lang, 'Отправьте текст', 'Send text')}</b>\n\n"
        + tr(lang, "Результат появится отдельным сообщением.", "The result will appear in a separate message."),
        reply_markup=text_tools_keyboard(lang),
    )


@router.message(TextToolsStates.waiting_input, F.text)
async def process_text(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    operation = str(data.get("text_operation", ""))
    try:
        result = transform_text(operation, message.text or "")
    except TextToolError as exc:
        error = tr(
            lang,
            "Некорректная строка Base64. Нужны UTF-8 данные без повреждений.",
            "Invalid Base64 input. It must contain valid UTF-8 data.",
        ) if str(exc) == "invalid_base64" else tr(lang, "Неизвестная операция.", "Unknown operation.")
        await message.answer(f"{ERROR.html} {error}", reply_markup=text_result_keyboard(lang))
        return

    if len(result) <= 3200:
        await message.answer(
            f"{SUCCESS.html} <b>{tr(lang, 'Результат', 'Result')}</b>\n\n<pre><code>{escape(result)}</code></pre>",
            reply_markup=text_result_keyboard(lang),
        )
        return

    document = BufferedInputFile(result.encode("utf-8"), filename="text-result.txt")
    await message.answer_document(
        document,
        caption=f"{SUCCESS.html} {tr(lang, 'Результат сохранён в файл.', 'The result was saved to a file.')}",
        reply_markup=text_result_keyboard(lang),
    )
