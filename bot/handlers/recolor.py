import asyncio
from dataclasses import dataclass
from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender

from bot.keyboards.main_menu import back_keyboard
from bot.keyboards.recolor import recolor_palette_keyboard, recolor_result_keyboard
from bot.services.colors import hex_to_rgb
from bot.services.recolor import (
    IMAGE_SUFFIXES,
    TGS_SUFFIX,
    VIDEO_SUFFIXES,
    is_single_emoji,
    recolor_asset,
    render_unicode_emoji,
)
from bot.states import RecolorStates
from bot.utils.temp_files import cleanup_paths, make_temp_path
from bot.utils.premium_emoji import BRUSH, ERROR, LOADING
from bot.utils.messages import (
    answer_callback,
    answer_tool_photo,
    delete_user_message,
    edit_message_text,
    edit_stored_panel,
    edit_tool_photo,
    remember_panel,
)

router = Router(name="recolor")
ANIMATED_EMOJI_SET_NAME = "AnimatedEmojies"
MAX_INPUT_BYTES = 20 * 1024 * 1024
_ANIMATED_EMOJI_SOURCES: dict[str, "RecolorSource"] | None = None
_RECOLOR_SEMAPHORE = asyncio.Semaphore(1)


@dataclass(frozen=True, slots=True)
class RecolorSource:
    suffix: str
    emoji: str
    file_id: str | None = None
    local_path: Path | None = None
    adaptive: bool = False


@router.callback_query(F.data == "menu:recolor")
async def open_recolor(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("recolor_input_path"))
    await state.set_state(RecolorStates.waiting_file)
    await remember_panel(callback, state, "recolor")
    await state.update_data(
        recolor_input_path=None,
        recolor_source_emoji=None,
        recolor_adaptive=False,
        recolor_panel_is_sticker=False,
    )
    await edit_tool_photo(
        callback,
        "recolor",
        f"{BRUSH.html} <b>Перекраска стикеров и эмодзи</b>\n\n"
        "Отправьте один обычный или Premium Emoji, статичный/анимированный стикер "
        "либо файл PNG, JPG, WEBP, TGS, WEBM, GIF или MP4.",
        reply_markup=back_keyboard(),
    )


@router.message(RecolorStates.waiting_file)
async def receive_recolor_file(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("recolor_input_path"))

    try:
        source = await _resolve_recolor_source(message)
    except ValueError as exc:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {exc}",
            reply_markup=back_keyboard(),
        )
        return
    if source is None:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} Отправьте один эмодзи, стикер или поддерживаемый файл.",
            reply_markup=back_keyboard(),
        )
        return

    input_path = source.local_path or make_temp_path(source.suffix)
    if source.file_id:
        try:
            await message.bot.download(source.file_id, destination=input_path)
        except (OSError, TelegramAPIError) as exc:
            cleanup_paths(input_path)
            await edit_stored_panel(
                message,
                state,
                f"{ERROR.html} Не удалось скачать исходный эмодзи из Telegram: {escape(str(exc))}",
                reply_markup=back_keyboard(),
            )
            return
    await state.update_data(
        recolor_input_path=str(input_path),
        recolor_source_emoji=source.emoji,
        recolor_adaptive=source.adaptive,
    )
    await delete_user_message(message)
    await _show_recolor_palette(message, state)


@router.callback_query(F.data == "recolor:again")
async def recolor_again(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    await answer_callback(callback)
    data = await state.get_data()
    cleanup_paths(data.get("recolor_input_path"))
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(RecolorStates.waiting_file)
    panel = await answer_tool_photo(
        callback.message,
        "recolor",
        f"{BRUSH.html} <b>Перекраска стикеров и эмодзи</b>\n\n"
        "Отправьте обычный/Premium Emoji, стикер или поддерживаемый медиафайл.",
        reply_markup=back_keyboard(),
    )
    await state.update_data(
        recolor_input_path=None,
        recolor_source_emoji=None,
        recolor_adaptive=False,
        recolor_panel_is_sticker=False,
        panel_chat_id=panel.chat.id,
        panel_message_id=panel.message_id,
        panel_tool_key="recolor",
    )


@router.callback_query(F.data == "recolor:custom")
async def ask_custom_color(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RecolorStates.waiting_custom_color)
    await edit_message_text(callback, "Введите HEX цвет, например: <code>#0A84FF</code>", reply_markup=back_keyboard())


@router.message(RecolorStates.waiting_custom_color, F.text)
async def recolor_with_custom_color(message: Message, state: FSMContext) -> None:
    try:
        hex_to_rgb(message.text or "")
    except ValueError as exc:
        await edit_stored_panel(message, state, f"{ERROR.html} {exc}", reply_markup=back_keyboard())
        return
    await _recolor_and_send(message, state, message.text or "#0A84FF")


@router.callback_query(F.data.startswith("recolor:color:"))
async def recolor_with_palette(callback: CallbackQuery, state: FSMContext) -> None:
    hex_color = f"#{(callback.data or '').rsplit(':', maxsplit=1)[-1]}"
    await answer_callback(callback)
    await _recolor_and_send(callback.message, state, hex_color)


async def _recolor_and_send(message: Message, state: FSMContext, hex_color: str) -> None:
    data = await state.get_data()
    input_path = Path(data["recolor_input_path"]) if data.get("recolor_input_path") else None
    if input_path is None or not input_path.exists():
        await message.answer(
            f"{ERROR.html} Сначала отправьте эмодзи, стикер или изображение.",
            reply_markup=back_keyboard(),
        )
        return

    output_path = make_temp_path(input_path.suffix or ".png")
    result_path: Path | None = None
    succeeded = False
    try:
        await edit_stored_panel(
            message,
            state,
            f"{LOADING.html} <b>Перекрашиваю…</b>\n\n"
            f"Выбранный цвет: <code>{hex_color.upper()}</code>\n"
            "Анимированные эмодзи могут обрабатываться немного дольше.",
        )
        async with ChatActionSender.choose_sticker(
            chat_id=message.chat.id,
            bot=message.bot,
            message_thread_id=getattr(message, "message_thread_id", None),
        ):
            async with _RECOLOR_SEMAPHORE:
                result_path = await asyncio.to_thread(
                    recolor_asset,
                    input_path,
                    output_path,
                    hex_color,
                    bool(data.get("recolor_adaptive")),
                )
        if message.from_user and not message.from_user.is_bot:
            await delete_user_message(message)
        panel_chat_id = data.get("panel_chat_id") or message.chat.id
        panel_message_id = data.get("panel_message_id")
        sticker_message = await message.bot.send_sticker(
            chat_id=message.chat.id,
            sticker=FSInputFile(result_path),
            emoji=data.get("recolor_source_emoji") or BRUSH.fallback,
            reply_markup=recolor_result_keyboard(),
        )
        # Keep the progress panel visible until Telegram has accepted and
        # returned the finished sticker, so the user never sees an empty gap.
        if panel_message_id:
            try:
                await message.bot.delete_message(panel_chat_id, panel_message_id)
            except TelegramBadRequest:
                pass
        await state.set_state(RecolorStates.waiting_file)
        await state.update_data(
            recolor_input_path=None,
            recolor_source_emoji=None,
            recolor_adaptive=False,
            recolor_panel_is_sticker=True,
            panel_chat_id=sticker_message.chat.id,
            panel_message_id=sticker_message.message_id,
            panel_tool_key="recolor",
        )
        succeeded = True
    except (OSError, ValueError, TelegramBadRequest) as exc:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} <b>Не удалось перекрасить эмодзи</b>\n\n{escape(str(exc))}",
            reply_markup=recolor_palette_keyboard(),
        )
    finally:
        cleanup_paths(
            output_path,
            output_path.with_suffix(".tgs"),
            output_path.with_suffix(".png"),
            output_path.with_suffix(".webp"),
            output_path.with_suffix(".webm"),
            result_path,
        )
        if succeeded:
            cleanup_paths(input_path)


async def _show_recolor_palette(message: Message, state: FSMContext) -> None:
    text = f"{BRUSH.html} <b>Новый цвет</b>\n\nВыберите оттенок для эмодзи или стикера."
    data = await state.get_data()
    if data.get("recolor_panel_is_sticker"):
        chat_id = data.get("panel_chat_id")
        message_id = data.get("panel_message_id")
        if chat_id and message_id:
            try:
                await message.bot.delete_message(chat_id, message_id)
            except TelegramBadRequest:
                pass
        panel = await answer_tool_photo(
            message,
            "recolor",
            text,
            reply_markup=recolor_palette_keyboard(),
        )
        await state.update_data(
            recolor_panel_is_sticker=False,
            panel_chat_id=panel.chat.id,
            panel_message_id=panel.message_id,
            panel_tool_key="recolor",
        )
        return
    await edit_stored_panel(
        message,
        state,
        text,
        reply_markup=recolor_palette_keyboard(),
    )


async def _resolve_recolor_source(message: Message) -> RecolorSource | None:
    custom_ids = _custom_emoji_ids(message)
    if custom_ids:
        if len(custom_ids) != 1:
            raise ValueError("За один раз можно перекрасить только один Premium Emoji.")
        try:
            stickers = await message.bot.get_custom_emoji_stickers(custom_ids)
        except TelegramAPIError as exc:
            raise ValueError("Не удалось загрузить Premium Emoji из Telegram.") from exc
        if not stickers:
            raise ValueError("Telegram не вернул файл Premium Emoji.")
        return _source_from_sticker(stickers[0], message.text or "")

    text = (message.text or "").strip()
    if text:
        if not is_single_emoji(text):
            return None
        animated_source = await _standard_animated_emoji_source(message, text)
        if animated_source is not None:
            return animated_source
        local_path = make_temp_path(".png")
        try:
            await asyncio.to_thread(render_unicode_emoji, text, local_path)
        except (OSError, ValueError):
            cleanup_paths(local_path)
            raise
        return RecolorSource(".png", text, local_path=local_path)

    if message.sticker:
        return _source_from_sticker(message.sticker, message.sticker.emoji or BRUSH.fallback)
    if message.photo:
        photo = message.photo[-1]
        _ensure_file_size(photo.file_size)
        return RecolorSource(".jpg", BRUSH.fallback, file_id=photo.file_id)
    if message.animation:
        _ensure_file_size(message.animation.file_size)
        suffix = Path(message.animation.file_name or "").suffix.lower()
        if suffix not in {".gif", ".mp4"}:
            suffix = ".mp4"
        return RecolorSource(suffix, BRUSH.fallback, file_id=message.animation.file_id)
    if message.video:
        _ensure_file_size(message.video.file_size)
        return RecolorSource(".mp4", BRUSH.fallback, file_id=message.video.file_id)
    if message.document:
        _ensure_file_size(message.document.file_size)
        suffix = Path(message.document.file_name or "").suffix.lower()
        if suffix not in IMAGE_SUFFIXES | VIDEO_SUFFIXES | {TGS_SUFFIX}:
            raise ValueError("Этот формат не поддерживается для перекраски.")
        return RecolorSource(suffix, BRUSH.fallback, file_id=message.document.file_id)
    return None


def _custom_emoji_ids(message: Message) -> list[str]:
    result: list[str] = []
    for entity in [
        *(getattr(message, "entities", None) or []),
        *(getattr(message, "caption_entities", None) or []),
    ]:
        if str(entity.type) == "custom_emoji" and entity.custom_emoji_id:
            if entity.custom_emoji_id not in result:
                result.append(entity.custom_emoji_id)
    return result


async def _standard_animated_emoji_source(
    message: Message,
    emoji: str,
) -> RecolorSource | None:
    global _ANIMATED_EMOJI_SOURCES
    if _ANIMATED_EMOJI_SOURCES is None:
        try:
            sticker_set = await message.bot.get_sticker_set(ANIMATED_EMOJI_SET_NAME)
        except TelegramAPIError:
            return None
        _ANIMATED_EMOJI_SOURCES = {}
        for sticker in sticker_set.stickers:
            key = _emoji_key(sticker.emoji or "")
            if key and key not in _ANIMATED_EMOJI_SOURCES:
                _ANIMATED_EMOJI_SOURCES[key] = _source_from_sticker(sticker, sticker.emoji or emoji)
    return _ANIMATED_EMOJI_SOURCES.get(_emoji_key(emoji))


def _source_from_sticker(sticker, fallback_emoji: str) -> RecolorSource:
    _ensure_file_size(getattr(sticker, "file_size", None))
    suffix = ".webm" if sticker.is_video else ".tgs" if sticker.is_animated else ".webp"
    return RecolorSource(
        suffix=suffix,
        emoji=sticker.emoji or fallback_emoji or BRUSH.fallback,
        file_id=sticker.file_id,
        adaptive=bool(getattr(sticker, "needs_repainting", False)),
    )


def _emoji_key(value: str) -> str:
    return value.strip().replace("\ufe0e", "").replace("\ufe0f", "")


def _ensure_file_size(file_size: int | None) -> None:
    if file_size and file_size > MAX_INPUT_BYTES:
        raise ValueError("Файл больше 20 МБ и не может быть загружен Bot API.")
