from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards.color import color_tools_keyboard
from bot.i18n import tr
from bot.keyboards.main_menu import back_keyboard
from bot.services.colors import create_color_image, hex_to_rgb, random_color, rgb_to_hex
from bot.states import ColorStates
from bot.utils.temp_files import cleanup_paths, make_temp_path
from bot.utils.messages import answer_callback, edit_message_text, edit_tool_photo
from bot.utils.premium_emoji import BRUSH, ERROR

router = Router(name="color_picker")


@router.callback_query(F.data == "menu:color")
async def open_color_picker(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await edit_tool_photo(callback, "color", f"{BRUSH.html} <b>{tr(lang, 'Работа с цветами', 'Color tools')}</b>\n\n{tr(lang, 'Выберите действие:', 'Choose an action:')}", reply_markup=color_tools_keyboard(lang))


@router.callback_query(F.data == "color:hex")
async def ask_hex(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(ColorStates.waiting_hex)
    await edit_message_text(callback, tr(lang, "Введите HEX цвет, например: <code>#FF5733</code>", "Enter a HEX color, for example: <code>#FF5733</code>"), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "color:rgb")
async def ask_rgb(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(ColorStates.waiting_rgb)
    await edit_message_text(callback, tr(lang, "Введите RGB цвет, например: <code>255 87 51</code>", "Enter an RGB color, for example: <code>255 87 51</code>"), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "color:random")
async def send_random_color(callback: CallbackQuery, lang: str) -> None:
    hex_color, rgb = random_color()
    await answer_callback(callback)
    await _send_color(callback.message, hex_color, rgb, lang)


@router.message(ColorStates.waiting_hex, F.text)
async def handle_hex(message: Message, lang: str) -> None:
    try:
        rgb = hex_to_rgb(message.text or "")
    except ValueError as exc:
        await message.answer(f"{ERROR.html} {_color_error(lang, exc)}", reply_markup=back_keyboard(lang))
        return
    hex_color = "#{:02X}{:02X}{:02X}".format(*rgb)
    await _send_color(message, hex_color, rgb, lang)


@router.message(ColorStates.waiting_rgb, F.text)
async def handle_rgb(message: Message, lang: str) -> None:
    try:
        hex_color = rgb_to_hex(message.text or "")
        rgb = hex_to_rgb(hex_color)
    except ValueError as exc:
        await message.answer(f"{ERROR.html} {_color_error(lang, exc)}", reply_markup=back_keyboard(lang))
        return
    await _send_color(message, hex_color, rgb, lang)


async def _send_color(message: Message, hex_color: str, rgb: tuple[int, int, int], lang: str) -> None:
    image_path: Path = make_temp_path(".png")
    create_color_image(rgb, image_path)
    try:
        await message.answer_photo(
            photo=FSInputFile(image_path),
            caption=(
                f"{BRUSH.html} <b>{tr(lang, 'Цвет', 'Color')}</b>\n\n"
                f"HEX: <code>{hex_color}</code>\n"
                f"RGB: <code>{rgb[0]}, {rgb[1]}, {rgb[2]}</code>"
            ),
            reply_markup=color_tools_keyboard(lang),
        )
    finally:
        cleanup_paths(image_path)


def _color_error(lang: str, error: ValueError) -> str:
    translations = {
        "HEX должен быть в формате #FF5733.": "HEX must use the #FF5733 format.",
        "HEX содержит недопустимые символы.": "HEX contains invalid characters.",
        "RGB должен быть в формате: 255 87 51.": "RGB must use this format: 255 87 51.",
        "RGB должен содержать только числа.": "RGB must contain numbers only.",
        "Каждое RGB-значение должно быть от 0 до 255.": "Every RGB value must be between 0 and 255.",
    }
    return translations.get(str(error), "Invalid color value.") if lang == "en" else str(error)
