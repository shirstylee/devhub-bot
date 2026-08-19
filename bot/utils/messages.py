from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from bot.config import BASE_DIR


IMAGES_DIR = BASE_DIR / "Images"

TOOL_IMAGES = {
    "main": "mainmenu.png",
    "language": "language.png",
    "json": "jsonformatter.png",
    "password": "passwordsgenerator.png",
    "color": "colors.png",
    "file": "filesconverter.png",
    "qr": "qrinstruments.png",
    "fake": "fakedata.png",
    "code": "codescreen.png",
    "shortener": "link.png",
    "pdf": "pdfinstruments.png",
    "text_tools": "codescreen.png",
    # Kept as internal compatibility aliases; their routers are no longer registered.
    "recolor": "stickercolor.png",
    "renderer": "renderer.png",
}
_PANEL_MEDIA_KEYS: dict[tuple[int, int], str] = {}


def tool_image_path(key: str) -> Path:
    return IMAGES_DIR / TOOL_IMAGES[key]


def forget_panel_media(chat_id: int, message_id: int) -> None:
    """Mark a panel whose media was changed outside edit_tool_photo."""
    _PANEL_MEDIA_KEYS.pop((chat_id, message_id), None)


async def answer_callback(callback: CallbackQuery, text: str | None = None, show_alert: bool | None = None) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        if "query is too old" not in exc.message and "query ID is invalid" not in exc.message:
            raise


async def answer_tool_photo(message: Message, key: str, caption: str, reply_markup=None) -> Message:
    caption = decorate_panel_text(caption)
    image_path = tool_image_path(key)
    if image_path.exists():
        panel = await message.answer_photo(
            FSInputFile(image_path),
            caption=caption,
            reply_markup=reply_markup,
        )
    else:
        panel = await message.answer(caption, reply_markup=reply_markup)
    _PANEL_MEDIA_KEYS[(panel.chat.id, panel.message_id)] = key
    return panel


async def edit_tool_photo(
    callback: CallbackQuery,
    key: str,
    caption: str,
    reply_markup=None,
) -> Message | None:
    if callback.message is None:
        await answer_callback(callback)
        return None

    await answer_callback(callback)
    caption = decorate_panel_text(caption)
    image_path = tool_image_path(key)
    panel_key = (callback.message.chat.id, callback.message.message_id)
    media_changed = _PANEL_MEDIA_KEYS.get(panel_key) != key
    if image_path.exists() and media_changed:
        media = InputMediaPhoto(media=FSInputFile(image_path), caption=caption)
        try:
            panel = await callback.message.edit_media(media=media, reply_markup=reply_markup)
            _PANEL_MEDIA_KEYS[panel_key] = key
            return panel
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message:
                _PANEL_MEDIA_KEYS[panel_key] = key
                return callback.message
            if "message to edit not found" not in exc.message and "message can't be edited" not in exc.message:
                raise

    try:
        panel = await callback.message.edit_caption(caption=caption, reply_markup=reply_markup)
        _PANEL_MEDIA_KEYS[panel_key] = key
        return panel
    except TelegramBadRequest as exc:
        if "message is not modified" in exc.message:
            _PANEL_MEDIA_KEYS[panel_key] = key
            return callback.message
        if "there is no caption" in exc.message:
            panel = await callback.message.edit_text(caption, reply_markup=reply_markup)
            _PANEL_MEDIA_KEYS[panel_key] = key
            return panel
        if "message to edit not found" not in exc.message and "message can't be edited" not in exc.message:
            raise
        _PANEL_MEDIA_KEYS.pop(panel_key, None)
        return await answer_tool_photo(callback.message, key, caption, reply_markup=reply_markup)


async def edit_message_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    await answer_callback(callback)
    text = decorate_panel_text(text)
    try:
        await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in exc.message:
            return
        if "there is no caption" in exc.message:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return
        raise


async def remember_panel(
    callback: CallbackQuery,
    state: FSMContext,
    tool_key: str,
) -> None:
    if callback.message is None:
        return
    await state.update_data(
        panel_chat_id=callback.message.chat.id,
        panel_message_id=callback.message.message_id,
        panel_tool_key=tool_key,
    )


async def edit_stored_panel(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> Message | None:
    text = decorate_panel_text(text)
    data = await state.get_data()
    chat_id = data.get("panel_chat_id")
    message_id = data.get("panel_message_id")
    if chat_id and message_id:
        try:
            return await message.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message:
                return None
            if "there is no caption" in exc.message:
                return await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
            if "message to edit not found" not in exc.message and "message can't be edited" not in exc.message:
                raise

    tool_key = data.get("panel_tool_key")
    if tool_key in TOOL_IMAGES:
        panel = await answer_tool_photo(message, tool_key, text, reply_markup=reply_markup)
    else:
        panel = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(panel_chat_id=panel.chat.id, panel_message_id=panel.message_id)
    return panel


async def delete_user_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        return


def decorate_panel_text(text: str) -> str:
    """Give every panel a real Telegram block quotation."""
    if "<blockquote" in text.casefold():
        return text
    if "\n\n" in text:
        heading, body = text.split("\n\n", maxsplit=1)
        return f"{heading}\n\n<blockquote>{body}</blockquote>"
    return f"<blockquote>{text}</blockquote>"
