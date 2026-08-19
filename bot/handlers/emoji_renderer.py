from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace
from datetime import datetime
from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaVideo,
    Message,
)

from bot.keyboards.emoji_renderer import (
    color_input_keyboard,
    custom_media_keyboard,
    font_input_keyboard,
    format_keyboard,
    pack_keyboard,
    position_keyboard,
    render_again_keyboard,
    render_history_keyboard,
    render_result_keyboard,
    renderer_back_keyboard,
    renderer_main_keyboard,
    size_keyboard,
    watermark_keyboard,
)
from bot.services.media_renderer import RenderError, media_renderer
from bot.services.render_fonts import FontLoadError, google_font_loader
from bot.services.render_history import RenderHistoryEntry, render_history_store
from bot.services.render_models import (
    OutputFormat,
    RenderRequest,
    RenderSettings,
    RenderSource,
    SourceKind,
    WatermarkPosition,
)
from bot.services.render_settings import render_settings_store
from bot.services.render_validation import normalize_hex, parse_resolution
from bot.states import RenderStates
from bot.utils.messages import (
    answer_callback,
    decorate_panel_text,
    edit_message_text,
    edit_tool_photo,
    forget_panel_media,
    tool_image_path,
)
from bot.utils.temp_files import cleanup_paths, make_temp_path
from bot.utils.premium_emoji import (
    ADD_TEXT,
    APPS,
    BOX,
    BRUSH,
    ERROR,
    FONT,
    FORMAT,
    HISTORY,
    LOADING,
    LOCATION,
    MEDIA,
    SETTINGS,
    SHOW,
    SUCCESS,
    TAG,
)


router = Router(name="emoji_renderer")
LOGGER = logging.getLogger(__name__)
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".tgs"}
MAX_INPUT_BYTES = 20 * 1024 * 1024
PACK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/(?:addstickers|addemoji)/([A-Za-z0-9_]+)",
    re.IGNORECASE,
)
ANIMATED_EMOJI_SET_NAME = "AnimatedEmojies"
_ANIMATED_EMOJI_SOURCES: dict[str, dict] | None = None


@router.callback_query(F.data == "menu:emoji_renderer")
async def open_renderer(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    if callback.message.chat.type != "private":
        await answer_callback(
            callback,
            "Рендер и Mini App доступны в личном чате с ботом.",
            show_alert=True,
        )
        return

    await state.clear()
    await state.set_state(RenderStates.ready)
    settings = await render_settings_store.load(callback.from_user.id)
    background_source = _background_from_settings(settings)
    await state.update_data(
        render_background_source=(
            background_source.to_session_dict() if background_source is not None else None
        )
    )
    panel = await edit_tool_photo(
        callback,
        "renderer",
        _home_text(settings, background_source is not None),
        reply_markup=renderer_main_keyboard(
            settings,
            has_source=False,
            has_background=background_source is not None,
        ),
    )
    if panel is not None:
        await state.update_data(
            renderer_panel_chat_id=panel.chat.id,
            renderer_panel_message_id=panel.message_id,
        )


@router.callback_query(F.data == "render:noop")
async def renderer_noop(callback: CallbackQuery) -> None:
    await answer_callback(callback)


@router.callback_query(F.data == "render:home")
async def renderer_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.callback_query(F.data == "render:settings")
async def renderer_settings(callback: CallbackQuery, state: FSMContext) -> None:
    """Restore the settings banner after the panel was replaced by a result."""
    if callback.message is None:
        await answer_callback(callback)
        return
    await state.set_state(RenderStates.ready)
    settings = await render_settings_store.load(callback.from_user.id)
    background = await _ensure_background_in_state(state, settings)
    data = await state.get_data()
    panel = await edit_tool_photo(
        callback,
        "renderer",
        _home_text(settings, background is not None),
        reply_markup=renderer_main_keyboard(
            settings,
            bool(data.get("render_sources")),
            background is not None,
        ),
    )
    if panel is not None:
        await state.update_data(
            renderer_panel_chat_id=panel.chat.id,
            renderer_panel_message_id=panel.message_id,
        )


@router.callback_query(F.data == "render:history")
async def open_render_history(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    entries = await render_history_store.load(callback.from_user.id)
    await state.set_state(RenderStates.ready)
    panel = await edit_tool_photo(
        callback,
        "renderer",
        _history_text(entries),
        reply_markup=render_history_keyboard(entries),
    )
    if panel is not None:
        await state.update_data(
            renderer_panel_chat_id=panel.chat.id,
            renderer_panel_message_id=panel.message_id,
        )


@router.callback_query(F.data == "render:history:clear")
async def clear_render_history(callback: CallbackQuery, state: FSMContext) -> None:
    await render_history_store.clear(callback.from_user.id)
    await state.set_state(RenderStates.ready)
    await edit_message_text(
        callback,
        _history_text([]),
        reply_markup=render_history_keyboard([]),
    )


@router.callback_query(F.data.startswith("render:history:repeat:"))
async def repeat_history_render(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    entry_id = (callback.data or "").rsplit(":", 1)[-1]
    entries = await render_history_store.load(callback.from_user.id)
    entry = next((item for item in entries if item.entry_id == entry_id), None)
    if entry is None:
        await answer_callback(
            callback,
            "Эта запись уже недоступна.",
            show_alert=True,
        )
        return
    sources = [
        RenderSource.from_session_dict(source.to_session_dict())
        for source in entry.sources
    ]
    await answer_callback(callback)
    await _render_sources(
        callback.message,
        state,
        sources,
        user_id=callback.from_user.id,
        history_entry=entry,
    )


@router.callback_query(F.data == "render:again")
async def render_again(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    await state.set_state(RenderStates.ready)
    panel = await edit_tool_photo(
        callback,
        "renderer",
        f"{APPS.html} <b>Новый рендер</b>\n\n"
        "<blockquote>Отправьте эмодзи или стикер — это сообщение заменится новым результатом.</blockquote>",
        reply_markup=render_again_keyboard(),
    )
    if panel is not None:
        await state.update_data(
            renderer_panel_chat_id=panel.chat.id,
            renderer_panel_message_id=panel.message_id,
        )


@router.callback_query(F.data == "render:defaults")
async def reset_render_defaults(callback: CallbackQuery, state: FSMContext) -> None:
    defaults = RenderSettings()
    await render_settings_store.save(callback.from_user.id, defaults)
    await state.update_data(render_background_source=None)
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.callback_query(F.data == "render:bg")
async def ask_background(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_background)
    await edit_message_text(
        callback,
        f"{BRUSH.html} <b>Цвет фона</b>\n\nВведите HEX-цвет.\n"
        "<blockquote><code>#FFFFFF</code> — белый\n<code>#000000</code> — чёрный</blockquote>",
        reply_markup=color_input_keyboard(
            "render:home",
            default_callback="render:default:background",
        ),
    )


@router.message(RenderStates.waiting_background, F.text)
async def save_background(message: Message, state: FSMContext) -> None:
    try:
        color = normalize_hex(message.text or "")
    except ValueError as exc:
        await _panel_error(
            message,
            state,
            str(exc),
            color_input_keyboard(
                "render:home",
                default_callback="render:default:background",
            ),
        )
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(message.from_user.id, replace(settings, background_color=color))
    await _accept_and_home(message, state)


@router.callback_query(F.data == "render:resolution")
async def ask_resolution(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_resolution)
    await edit_message_text(
        callback,
        f"{FORMAT.html} <b>Разрешение</b>\n\nВведите размер или соотношение сторон.\n"
        "<blockquote><code>1920x530</code> или <code>1920x600</code>\n"
        "<code>2.35:1</code>, <code>16:9</code> или <code>1:1</code></blockquote>",
        reply_markup=renderer_back_keyboard(
            default_callback="render:default:resolution",
        ),
    )


@router.message(RenderStates.waiting_resolution, F.text)
async def save_resolution(message: Message, state: FSMContext) -> None:
    try:
        width, height = parse_resolution(message.text or "")
    except ValueError as exc:
        await _panel_error(
            message,
            state,
            str(exc),
            renderer_back_keyboard(default_callback="render:default:resolution"),
        )
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(
        message.from_user.id,
        replace(settings, width=width, height=height),
    )
    await _accept_and_home(message, state)


@router.callback_query(F.data == "render:format")
async def choose_format(callback: CallbackQuery) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    await edit_message_text(
        callback,
        f"{FORMAT.html} <b>Выберите формат результата</b>\n\n"
        "<blockquote>«Файл» — MP4, отправленный документом без показа как видео.</blockquote>",
        reply_markup=format_keyboard(settings.output_format),
    )


@router.callback_query(F.data.startswith("render:format:"))
async def save_format(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        selected = OutputFormat((callback.data or "").rsplit(":", maxsplit=1)[-1])
    except ValueError:
        await answer_callback(callback, "Неизвестный формат.", show_alert=True)
        return
    settings = await render_settings_store.load(callback.from_user.id)
    await render_settings_store.save(callback.from_user.id, replace(settings, output_format=selected))
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.callback_query(F.data == "render:media")
async def ask_custom_media(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.ready)
    settings = await render_settings_store.load(callback.from_user.id)
    background = await _ensure_background_in_state(state, settings)
    has_background = background is not None
    await edit_message_text(
        callback,
        f"{MEDIA.html} <b>Своя медиа</b>\n\n"
        "<blockquote>Загруженная медиа сохраняется и используется как фон. Эмодзи или стикер остаётся по центру. Для максимального качества отправляйте изображение как файл, а не как сжатое фото.</blockquote>",
        reply_markup=custom_media_keyboard(has_background),
    )


@router.callback_query(F.data == "render:media:upload")
async def wait_custom_media(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_media)
    await edit_message_text(
        callback,
        f"{MEDIA.html} <b>Жду фото…</b>\n\n"
        "<blockquote>Принимаются PNG, JPG, WEBP, GIF, MP4, WEBM и TGS до 20 МБ. Фон сохранится для следующих рендеров. Изображение без сжатия лучше отправлять как файл.</blockquote>",
        reply_markup=renderer_back_keyboard(
            "render:media",
            default_callback="render:default:media",
        ),
    )


@router.callback_query(F.data == "render:media:clear")
async def clear_custom_media(callback: CallbackQuery, state: FSMContext) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    await render_settings_store.save(
        callback.from_user.id,
        replace(
            settings,
            custom_background_file_id=None,
            custom_background_suffix=None,
            custom_background_label=None,
        ),
    )
    await state.update_data(render_background_source=None)
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.message(RenderStates.waiting_media)
async def receive_custom_media(message: Message, state: FSMContext) -> None:
    source = _source_from_message(message, SourceKind.USER_MEDIA, recolorable=False)
    if source is None:
        await _panel_error(message, state, "Отправьте поддерживаемое фото, видео или файл.")
        return
    file_size = _message_file_size(message)
    if file_size and file_size > MAX_INPUT_BYTES:
        await _panel_error(message, state, "Файл больше 20 МБ и не может быть загружен Bot API.")
        return
    await _safe_delete(message)
    await state.update_data(render_background_source=source.to_session_dict())
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(
        message.from_user.id,
        _settings_with_background(settings, source),
    )
    await state.set_state(RenderStates.ready)
    await _show_home_message(message, state, message.from_user.id)


@router.callback_query(F.data == "render:emoji_color")
async def ask_emoji_color(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_emoji_color)
    await edit_message_text(
        callback,
        f"{BRUSH.html} <b>Цвет эмодзи</b>\n\nВведите HEX-цвет для эмодзи или стикера.\n"
        "<blockquote><code>#FFFFFF</code> — белый\n<code>#F2E9E4</code> — светло-серый</blockquote>",
        reply_markup=color_input_keyboard(
            "render:home",
            allow_original=True,
            default_callback="render:default:emoji_color",
        ),
    )


@router.message(RenderStates.waiting_emoji_color, F.text)
async def save_emoji_color(message: Message, state: FSMContext) -> None:
    try:
        color = normalize_hex(message.text or "")
    except ValueError as exc:
        await _panel_error(
            message,
            state,
            str(exc),
            color_input_keyboard(
                "render:home",
                allow_original=True,
                default_callback="render:default:emoji_color",
            ),
        )
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(message.from_user.id, replace(settings, emoji_color=color))
    await _accept_and_home(message, state)


@router.callback_query(F.data == "render:emoji_color:reset")
async def reset_emoji_color(callback: CallbackQuery, state: FSMContext) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    await render_settings_store.save(callback.from_user.id, replace(settings, emoji_color=None))
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.callback_query(F.data == "render:size")
async def choose_size(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.ready)
    settings = await render_settings_store.load(callback.from_user.id)
    await edit_message_text(
        callback,
        _size_text(settings.emoji_size),
        reply_markup=size_keyboard(settings.emoji_size),
    )


@router.callback_query(F.data.in_({"render:size:up", "render:size:down"}))
async def change_size(callback: CallbackQuery) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    delta = 5 if callback.data == "render:size:up" else -5
    value = max(10, min(100, settings.emoji_size + delta))
    if value == settings.emoji_size:
        await answer_callback(callback)
        return
    await render_settings_store.save(callback.from_user.id, replace(settings, emoji_size=value))
    await edit_message_text(
        callback,
        _size_text(value),
        reply_markup=size_keyboard(value),
    )


@router.callback_query(F.data == "render:size:input")
async def ask_custom_size(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_emoji_size)
    await edit_message_text(
        callback,
        "↔️ <b>Свой размер эмодзи</b>\n\n"
        "<blockquote>Введите целое число от 10 до 100. Значение задаётся в процентах от высоты холста.</blockquote>",
        reply_markup=renderer_back_keyboard(
            "render:size",
            default_callback="render:default:emoji_size",
        ),
    )


@router.message(RenderStates.waiting_emoji_size, F.text)
async def save_custom_size(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip().removesuffix("%"))
    except ValueError:
        await _panel_error(
            message,
            state,
            "Введите целое число от 10 до 100.",
            renderer_back_keyboard(
                "render:size",
                default_callback="render:default:emoji_size",
            ),
        )
        return
    if not 10 <= value <= 100:
        await _panel_error(
            message,
            state,
            "Размер эмодзи должен быть от 10 до 100%.",
            renderer_back_keyboard(
                "render:size",
                default_callback="render:default:emoji_size",
            ),
        )
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(message.from_user.id, replace(settings, emoji_size=value))
    await _safe_delete(message)
    await state.set_state(RenderStates.ready)
    await _edit_panel(
        message,
        state,
        _size_text(value),
        size_keyboard(value),
    )


@router.callback_query(F.data == "render:watermark")
async def open_watermark(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.ready)
    settings = await render_settings_store.load(callback.from_user.id)
    await edit_message_text(
        callback,
        _watermark_text(settings),
        reply_markup=watermark_keyboard(settings),
    )


@router.callback_query(F.data == "render:watermark:name")
async def ask_watermark_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_watermark_name)
    await edit_message_text(
        callback,
        f"{ADD_TEXT.html} <b>Текст водяного знака</b>\n\n"
        "<blockquote>Введите от 1 до 80 символов на любом языке.</blockquote>",
        reply_markup=renderer_back_keyboard(
            "render:watermark",
            default_callback="render:default:watermark_name",
        ),
    )


@router.message(RenderStates.waiting_watermark_name, F.text)
async def save_watermark_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= 80:
        await _panel_error(message, state, "Название должно содержать от 1 до 80 символов.")
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(message.from_user.id, replace(settings, watermark_text=value))
    await _accept_and_home(message, state)


@router.callback_query(F.data == "render:watermark:font")
async def ask_watermark_font(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_watermark_font)
    await edit_message_text(
        callback,
        f"{FONT.html} <b>Шрифт водяного знака</b>\n\n"
        "Введите английское название семейства из Google Fonts.\n"
        "<blockquote>Например: <code>Seymour One</code>, <code>Rubik Spray Paint</code>, "
        "<code>Montserrat</code></blockquote>",
        reply_markup=font_input_keyboard(),
    )


@router.message(RenderStates.waiting_watermark_font, F.text)
async def save_watermark_font(message: Message, state: FSMContext) -> None:
    family = (message.text or "").strip()
    await _edit_panel(
        message,
        state,
        f"{LOADING.html} <b>Проверяю шрифт…</b>\n\n<blockquote>Загружаю семейство из Google Fonts.</blockquote>",
        renderer_back_keyboard(
            "render:watermark",
            default_callback="render:default:watermark_font",
        ),
    )
    try:
        await google_font_loader.validate_family(family)
    except FontLoadError as exc:
        await _panel_error(message, state, str(exc), font_input_keyboard())
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(message.from_user.id, replace(settings, watermark_font=family))
    await _accept_and_home(message, state)


@router.callback_query(F.data == "render:watermark:color")
async def ask_watermark_color(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_watermark_color)
    await edit_message_text(
        callback,
        f"{BRUSH.html} <b>Цвет водяного знака</b>\n\nВведите HEX-цвет.\n"
        "<blockquote><code>#FFFFFF</code> — белый\n<code>#000000</code> — чёрный</blockquote>",
        reply_markup=color_input_keyboard(
            "render:watermark",
            default_callback="render:default:watermark_color",
        ),
    )


@router.message(RenderStates.waiting_watermark_color, F.text)
async def save_watermark_color(message: Message, state: FSMContext) -> None:
    try:
        color = normalize_hex(message.text or "")
    except ValueError as exc:
        await _panel_error(
            message,
            state,
            str(exc),
            color_input_keyboard(
                "render:watermark",
                default_callback="render:default:watermark_color",
            ),
        )
        return
    settings = await render_settings_store.load(message.from_user.id)
    await render_settings_store.save(message.from_user.id, replace(settings, watermark_color=color))
    await _accept_and_home(message, state)


@router.callback_query(F.data == "render:watermark:position")
async def choose_watermark_position(callback: CallbackQuery) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    await edit_message_text(
        callback,
        f"{LOCATION.html} <b>Позиция водяного знака</b>\n\n<blockquote>Выберите угол итогового рендера.</blockquote>",
        reply_markup=position_keyboard(settings.watermark_position),
    )


@router.callback_query(F.data.startswith("render:position:"))
async def save_watermark_position(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        position = WatermarkPosition((callback.data or "").rsplit(":", maxsplit=1)[-1])
    except ValueError:
        await answer_callback(callback, "Некорректная позиция.", show_alert=True)
        return
    settings = await render_settings_store.load(callback.from_user.id)
    await render_settings_store.save(
        callback.from_user.id,
        replace(settings, watermark_position=position),
    )
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.callback_query(F.data == "render:watermark:disable")
async def disable_watermark(callback: CallbackQuery, state: FSMContext) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    await render_settings_store.save(callback.from_user.id, replace(settings, watermark_text=None))
    await state.set_state(RenderStates.ready)
    await _show_home_callback(callback, state)


@router.callback_query(
    F.data.in_({"render:watermark:size:up", "render:watermark:size:down"})
)
async def change_watermark_size(callback: CallbackQuery) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    delta = 1 if callback.data == "render:watermark:size:up" else -1
    value = max(1, min(20, settings.watermark_size + delta))
    if value == settings.watermark_size:
        await answer_callback(callback)
        return
    settings = replace(settings, watermark_size=value)
    await render_settings_store.save(callback.from_user.id, settings)
    await edit_message_text(
        callback,
        _watermark_text(settings),
        reply_markup=watermark_keyboard(settings),
    )


@router.callback_query(F.data == "render:watermark:size:input")
async def ask_watermark_size(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenderStates.waiting_watermark_size)
    await edit_message_text(
        callback,
        f"{FORMAT.html} <b>Размер водяного знака</b>\n\n"
        "<blockquote>Введите целое число от 1 до 20. Это процент от высоты рендера.</blockquote>",
        reply_markup=renderer_back_keyboard(
            "render:watermark",
            default_callback="render:default:watermark_size",
        ),
    )


@router.message(RenderStates.waiting_watermark_size, F.text)
async def save_watermark_size(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip().removesuffix("%"))
    except ValueError:
        await _panel_error(
            message,
            state,
            "Введите целое число от 1 до 20.",
            renderer_back_keyboard(
                "render:watermark",
                default_callback="render:default:watermark_size",
            ),
        )
        return
    if not 1 <= value <= 20:
        await _panel_error(
            message,
            state,
            "Размер водяного знака должен быть от 1 до 20%.",
            renderer_back_keyboard(
                "render:watermark",
                default_callback="render:default:watermark_size",
            ),
        )
        return
    settings = await render_settings_store.load(message.from_user.id)
    settings = replace(settings, watermark_size=value)
    await render_settings_store.save(message.from_user.id, settings)
    await _safe_delete(message)
    await state.set_state(RenderStates.ready)
    await _edit_panel(
        message,
        state,
        _watermark_text(settings),
        watermark_keyboard(settings),
    )


@router.callback_query(F.data.startswith("render:default:"))
async def reset_render_section(callback: CallbackQuery, state: FSMContext) -> None:
    section = (callback.data or "").removeprefix("render:default:")
    settings = await render_settings_store.load(callback.from_user.id)
    try:
        settings = _settings_with_section_default(settings, section)
    except ValueError:
        await answer_callback(callback, "Неизвестный раздел настроек.", show_alert=True)
        return

    await render_settings_store.save(callback.from_user.id, settings)
    if section == "media":
        await state.update_data(render_background_source=None)
    await state.set_state(RenderStates.ready)

    if section == "background":
        await ask_background(callback, state)
    elif section == "resolution":
        await ask_resolution(callback, state)
    elif section == "format":
        await choose_format(callback)
    elif section == "media":
        await ask_custom_media(callback, state)
    elif section == "emoji_color":
        await ask_emoji_color(callback, state)
    elif section == "emoji_size":
        await choose_size(callback, state)
    elif section == "watermark_font":
        await ask_watermark_font(callback, state)
    elif section == "watermark_color":
        await ask_watermark_color(callback, state)
    elif section == "watermark_position":
        await choose_watermark_position(callback)
    else:
        await open_watermark(callback, state)


def _settings_with_section_default(
    settings: RenderSettings,
    section: str,
) -> RenderSettings:
    defaults = RenderSettings()
    if section == "background":
        return replace(settings, background_color=defaults.background_color)
    if section == "resolution":
        return replace(
            settings,
            width=defaults.width,
            height=defaults.height,
            fps=defaults.fps,
        )
    if section == "format":
        return replace(settings, output_format=defaults.output_format)
    if section == "media":
        return replace(
            settings,
            custom_background_file_id=None,
            custom_background_suffix=None,
            custom_background_label=None,
        )
    if section == "emoji_color":
        return replace(settings, emoji_color=defaults.emoji_color)
    if section == "emoji_size":
        return replace(settings, emoji_size=defaults.emoji_size)
    if section == "watermark":
        return replace(
            settings,
            watermark_text=defaults.watermark_text,
            watermark_font=defaults.watermark_font,
            watermark_color=defaults.watermark_color,
            watermark_position=defaults.watermark_position,
            watermark_size=defaults.watermark_size,
        )
    if section == "watermark_name":
        return replace(settings, watermark_text=defaults.watermark_text)
    if section == "watermark_font":
        return replace(settings, watermark_font=defaults.watermark_font)
    if section == "watermark_color":
        return replace(settings, watermark_color=defaults.watermark_color)
    if section == "watermark_position":
        return replace(settings, watermark_position=defaults.watermark_position)
    if section == "watermark_size":
        return replace(settings, watermark_size=defaults.watermark_size)
    raise ValueError(section)


@router.message(RenderStates.ready)
async def receive_render_source(message: Message, state: FSMContext) -> None:
    custom_ids = _custom_emoji_ids(message)
    if custom_ids:
        if len(custom_ids) > 10:
            await _panel_error(message, state, "В одном рендере можно использовать до 10 эмодзи.")
            return
        stickers = await message.bot.get_custom_emoji_stickers(custom_ids)
        sources = [_source_from_sticker(sticker, SourceKind.CUSTOM_EMOJI) for sticker in stickers]
        await _safe_delete(message)
        await _render_sources(message, state, sources)
        return

    animated_emoji_source = await _standard_animated_emoji_source(message)
    if animated_emoji_source is not None:
        await _safe_delete(message)
        await _render_sources(message, state, [animated_emoji_source])
        return

    pack_match = PACK_PATTERN.search(message.text or "")
    if pack_match:
        try:
            sticker_set = await message.bot.get_sticker_set(pack_match.group(1))
        except TelegramBadRequest:
            await _panel_error(message, state, "Не удалось найти этот набор стикеров или эмодзи.")
            return
        items = [
            _source_from_sticker(sticker, SourceKind.STICKER).to_session_dict()
            for sticker in sticker_set.stickers
        ]
        await state.update_data(
            render_pack_items=items,
            render_pack_title=sticker_set.title,
            render_pack_selected=[],
            render_pack_page=0,
        )
        await state.set_state(RenderStates.choosing_pack)
        await _safe_delete(message)
        await _show_pack(message, state)
        return

    if message.sticker:
        source = _source_from_message(message, SourceKind.STICKER, recolorable=True)
    else:
        source = _source_from_message(message, SourceKind.USER_MEDIA, recolorable=False)
    if source:
        file_size = _message_file_size(message)
        if file_size and file_size > MAX_INPUT_BYTES:
            await _panel_error(message, state, "Файл больше 20 МБ и не может быть загружен Bot API.")
            return
        await _safe_delete(message)
        if source.kind == SourceKind.USER_MEDIA:
            await state.update_data(render_background_source=source.to_session_dict())
            settings = await render_settings_store.load(message.from_user.id)
            await render_settings_store.save(
                message.from_user.id,
                _settings_with_background(settings, source),
            )
            await _show_home_message(message, state, message.from_user.id)
        else:
            await _render_sources(message, state, [source])
        return

    await _panel_error(
        message,
        state,
        "Отправьте анимированное эмодзи, стикер, ссылку на набор или поддерживаемый файл.",
    )


@router.callback_query(RenderStates.choosing_pack, F.data.startswith("render:pack:page:"))
async def pack_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "0").rsplit(":", maxsplit=1)[-1])
    await state.update_data(render_pack_page=page)
    await _show_pack_callback(callback, state)


@router.callback_query(RenderStates.choosing_pack, F.data.startswith("render:pack:toggle:"))
async def pack_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    index = int((callback.data or "0").rsplit(":", maxsplit=1)[-1])
    data = await state.get_data()
    items = data.get("render_pack_items", [])
    if not 0 <= index < len(items):
        await answer_callback(callback, "Элемент не найден.", show_alert=True)
        return
    selected = set(int(value) for value in data.get("render_pack_selected", []))
    if index in selected:
        selected.remove(index)
    elif len(selected) >= 10:
        await answer_callback(callback, "Можно выбрать не больше 10 элементов.", show_alert=True)
        return
    else:
        selected.add(index)
    await state.update_data(render_pack_selected=sorted(selected))
    await _show_pack_callback(callback, state)


@router.callback_query(RenderStates.choosing_pack, F.data == "render:pack:confirm")
async def pack_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    data = await state.get_data()
    selected = sorted(set(int(value) for value in data.get("render_pack_selected", [])))
    if not selected:
        await answer_callback(callback, "Сначала выберите хотя бы один элемент.", show_alert=True)
        return
    items = data.get("render_pack_items", [])
    sources = [RenderSource.from_session_dict(items[index]) for index in selected]
    await answer_callback(callback)
    await _render_sources(callback.message, state, sources, user_id=callback.from_user.id)


@router.callback_query(F.data == "render:preview")
async def render_preview(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    await state.set_state(RenderStates.waiting_preview_source)
    await edit_message_text(
        callback,
        f"{SHOW.html} <b>Предпросмотр</b>\n\n"
        "<blockquote>Отправьте эмодзи или стикер. Следующее сообщение будет обработано только как быстрый предпросмотр: до 640 px, 30 FPS и 3 секунд.</blockquote>",
        reply_markup=renderer_back_keyboard(),
    )


@router.message(RenderStates.waiting_preview_source)
async def receive_preview_source(message: Message, state: FSMContext) -> None:
    custom_ids = _custom_emoji_ids(message)
    if custom_ids:
        if len(custom_ids) > 10:
            await _panel_error(message, state, "В предпросмотре можно использовать до 10 эмодзи.")
            return
        stickers = await message.bot.get_custom_emoji_stickers(custom_ids)
        sources = [_source_from_sticker(sticker, SourceKind.CUSTOM_EMOJI) for sticker in stickers]
    elif animated_emoji_source := await _standard_animated_emoji_source(message):
        sources = [animated_emoji_source]
    elif message.sticker:
        source = _source_from_message(message, SourceKind.STICKER, recolorable=True)
        sources = [source] if source is not None else []
    else:
        await _panel_error(
            message,
            state,
            "Для предпросмотра отправьте эмодзи Telegram или стикер.",
            renderer_back_keyboard(),
        )
        return
    file_size = _message_file_size(message)
    if file_size and file_size > MAX_INPUT_BYTES:
        await _panel_error(message, state, "Файл больше 20 МБ и не может быть загружен.")
        return
    await _safe_delete(message)
    await _render_sources(
        message,
        state,
        sources,
        user_id=message.from_user.id,
        preview=True,
    )


@router.callback_query(F.data == "render:repeat")
async def repeat_render(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await answer_callback(callback)
        return
    sources = await _stored_sources(state)
    if not sources:
        await answer_callback(callback, "Источник больше недоступен.", show_alert=True)
        return
    await answer_callback(callback)
    await _render_sources(
        callback.message,
        state,
        sources,
        user_id=callback.from_user.id,
        remember=False,
    )


async def _render_sources(
    anchor: Message,
    state: FSMContext,
    sources: list[RenderSource],
    *,
    user_id: int | None = None,
    preview: bool = False,
    remember: bool = True,
    history_entry: RenderHistoryEntry | None = None,
) -> None:
    owner_id = user_id or (anchor.from_user.id if anchor.from_user else anchor.chat.id)
    if remember:
        await state.update_data(render_sources=[source.to_session_dict() for source in sources])
    if history_entry is not None:
        background_source = (
            RenderSource.from_session_dict(history_entry.background_source.to_session_dict())
            if history_entry.background_source is not None
            else None
        )
    else:
        background_source = await _stored_background(state, owner_id)

    await _edit_panel(
        anchor,
        state,
        f"{LOADING.html} <b>Подготавливаю рендер…</b>\n\n"
        "<blockquote>Загружаю источники и кодирую кадры. Это может занять несколько минут.</blockquote>",
        None,
    )
    input_paths: list[Path] = []
    result = None
    try:
        for source in sources:
            path = make_temp_path(source.suffix)
            await anchor.bot.download(source.file_id, destination=path)
            source.local_path = path
            input_paths.append(path)
        if background_source is not None:
            background_path = make_temp_path(background_source.suffix)
            await anchor.bot.download(background_source.file_id, destination=background_path)
            background_source.local_path = background_path
            input_paths.append(background_path)

        settings = (
            RenderSettings.from_dict(history_entry.settings.to_dict())
            if history_entry is not None
            else await render_settings_store.load(owner_id)
        )
        result = await _render_with_progress(
            anchor,
            state,
            RenderRequest(
                sources=sources,
                settings=settings,
                background_source=background_source,
                preview=preview,
            ),
        )
        await _send_result(anchor, result, preview, state=state)
        if not preview:
            try:
                await render_history_store.add(
                    owner_id,
                    settings,
                    sources,
                    background_source,
                    result.duration,
                )
            except (OSError, TypeError, ValueError):
                LOGGER.exception("Could not save render history for user %s", owner_id)
    except (RenderError, FontLoadError, OSError, TelegramBadRequest) as exc:
        await state.set_state(RenderStates.ready)
        await _edit_panel(
            anchor,
            state,
            f"{ERROR.html} <b>Рендер не выполнен</b>\n\n<blockquote>{escape(str(exc))}</blockquote>",
            renderer_main_keyboard(
                await render_settings_store.load(owner_id),
                has_source=bool((await state.get_data()).get("render_sources")),
                has_background=bool((await state.get_data()).get("render_background_source")),
            ),
        )
        return
    finally:
        cleanup_paths(input_paths, result.temporary_paths if result else None)

    await state.set_state(RenderStates.ready)


async def _render_with_progress(
    anchor: Message,
    state: FSMContext,
    request: RenderRequest,
):
    loop = asyncio.get_running_loop()
    updates: asyncio.Queue[str] = asyncio.Queue()

    def report(stage: str) -> None:
        loop.call_soon_threadsafe(updates.put_nowait, stage)

    request.progress = report
    task = asyncio.create_task(media_renderer.render(request))
    labels = {
        "frames": (
            f"{LOADING.html} <b>Рендерю кадры…</b>\n\n"
            "<blockquote>Синхронизирую анимации и собираю композицию.</blockquote>"
        ),
        "encoding": (
            f"{LOADING.html} <b>Кодирую результат…</b>\n\n"
            "<blockquote>Сохраняю GIF или H.264 MP4 без изменения разрешения и FPS.</blockquote>"
        ),
    }
    while not task.done():
        try:
            stage = await asyncio.wait_for(updates.get(), timeout=0.5)
        except TimeoutError:
            continue
        text = labels.get(stage)
        if text:
            await _edit_panel(anchor, state, text, None)
    return await task


async def _send_result(
    anchor: Message,
    result,
    preview: bool,
    *,
    state: FSMContext | None = None,
) -> None:
    caption = (
        f"{SHOW.html} <b>Предпросмотр готов</b>"
        if preview
        else f"{SUCCESS.html} <b>Рендер готов</b>"
    )
    caption += (
        f"\n\n<blockquote>{result.width}×{result.height} · {result.fps} FPS · "
        f"{result.duration:.1f} сек.</blockquote>"
    )
    caption = decorate_panel_text(caption)
    keyboard = render_result_keyboard(preview)

    def input_media():
        file = FSInputFile(result.path, filename="render.mp4")
        if preview or result.output_format == OutputFormat.GIF:
            return InputMediaAnimation(media=file, caption=caption)
        if result.output_format == OutputFormat.VIDEO:
            return InputMediaVideo(media=file, caption=caption, supports_streaming=True)
        return InputMediaDocument(media=file, caption=caption)

    panel_chat_id = None
    panel_message_id = None
    if state is not None:
        data = await state.get_data()
        panel_chat_id = data.get("renderer_panel_chat_id")
        panel_message_id = data.get("renderer_panel_message_id")
    if panel_chat_id and panel_message_id:
        try:
            panel = await anchor.bot.edit_message_media(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                media=input_media(),
                reply_markup=keyboard,
            )
            forget_panel_media(panel_chat_id, panel_message_id)
            if state is not None:
                await state.update_data(
                    renderer_panel_chat_id=panel_chat_id,
                    renderer_panel_message_id=panel_message_id,
                )
            return
        except TelegramBadRequest:
            try:
                await anchor.bot.delete_message(panel_chat_id, panel_message_id)
            except TelegramBadRequest:
                pass

    file = FSInputFile(result.path, filename="render.mp4")
    if preview or result.output_format == OutputFormat.GIF:
        panel = await anchor.bot.send_animation(
            anchor.chat.id,
            file,
            caption=caption,
            reply_markup=keyboard,
        )
    elif result.output_format == OutputFormat.VIDEO:
        panel = await anchor.bot.send_video(
            anchor.chat.id,
            file,
            caption=caption,
            reply_markup=keyboard,
            supports_streaming=True,
        )
    else:
        panel = await anchor.bot.send_document(
            anchor.chat.id,
            file,
            caption=caption,
            reply_markup=keyboard,
        )
    if state is not None:
        await state.update_data(
            renderer_panel_chat_id=panel.chat.id,
            renderer_panel_message_id=panel.message_id,
        )


async def _show_home_callback(callback: CallbackQuery, state: FSMContext) -> None:
    settings = await render_settings_store.load(callback.from_user.id)
    background = await _ensure_background_in_state(state, settings)
    data = await state.get_data()
    await edit_message_text(
        callback,
        _home_text(settings, background is not None),
        reply_markup=renderer_main_keyboard(
            settings,
            bool(data.get("render_sources")),
            background is not None,
        ),
    )


async def _show_home_message(message: Message, state: FSMContext, user_id: int) -> None:
    settings = await render_settings_store.load(user_id)
    background = await _ensure_background_in_state(state, settings)
    data = await state.get_data()
    await _edit_panel(
        message,
        state,
        _home_text(settings, background is not None),
        renderer_main_keyboard(
            settings,
            bool(data.get("render_sources")),
            background is not None,
        ),
    )


async def _accept_and_home(message: Message, state: FSMContext) -> None:
    await _safe_delete(message)
    await state.set_state(RenderStates.ready)
    await _show_home_message(message, state, message.from_user.id)


async def _panel_error(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    await _edit_panel(
        message,
        state,
        f"{ERROR.html} <b>Не удалось применить значение</b>\n\n<blockquote>{escape(text)}</blockquote>",
        reply_markup or renderer_back_keyboard(),
    )


async def _edit_panel(message: Message, state: FSMContext, text: str, reply_markup) -> None:
    text = decorate_panel_text(text)
    data = await state.get_data()
    chat_id = data.get("renderer_panel_chat_id")
    message_id = data.get("renderer_panel_message_id")
    if chat_id and message_id:
        try:
            await message.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message:
                return
            if "message to edit not found" not in exc.message and "message can't be edited" not in exc.message:
                raise

    image_path = tool_image_path("renderer")
    panel = await message.answer_photo(
        FSInputFile(image_path),
        caption=text,
        reply_markup=reply_markup,
    )
    await state.update_data(
        renderer_panel_chat_id=panel.chat.id,
        renderer_panel_message_id=panel.message_id,
    )


async def _show_pack(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    items = data.get("render_pack_items", [])
    selected = set(data.get("render_pack_selected", []))
    page = int(data.get("render_pack_page", 0))
    title = escape(str(data.get("render_pack_title", "Набор стикеров")))
    await _edit_panel(
        message,
        state,
        f"{BOX.html} <b>{title}</b>\n\n"
        f"<blockquote>Выберите до 10 элементов. Найдено: {len(items)}.</blockquote>",
        pack_keyboard(items, selected, page),
    )


async def _show_pack_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    items = data.get("render_pack_items", [])
    selected = set(data.get("render_pack_selected", []))
    page = int(data.get("render_pack_page", 0))
    title = escape(str(data.get("render_pack_title", "Набор стикеров")))
    await edit_message_text(
        callback,
        f"{BOX.html} <b>{title}</b>\n\n"
        f"<blockquote>Выберите до 10 элементов. Выбрано: {len(selected)}.</blockquote>",
        reply_markup=pack_keyboard(items, selected, page),
    )


async def _stored_sources(state: FSMContext) -> list[RenderSource]:
    data = await state.get_data()
    return [
        RenderSource.from_session_dict(raw)
        for raw in data.get("render_sources", [])
        if isinstance(raw, dict)
    ]


async def _stored_background(
    state: FSMContext,
    user_id: int | None = None,
) -> RenderSource | None:
    data = await state.get_data()
    raw = data.get("render_background_source")
    if isinstance(raw, dict):
        return RenderSource.from_session_dict(raw)
    if user_id is None:
        return None
    settings = await render_settings_store.load(user_id)
    return await _ensure_background_in_state(state, settings)


def _home_text(settings: RenderSettings, has_background: bool = False) -> str:
    format_labels = {
        OutputFormat.GIF: "GIF",
        OutputFormat.VIDEO: "Видео",
        OutputFormat.FILE: "Файл",
    }
    emoji_color = settings.emoji_color or "оригинальный"
    watermark = escape(settings.watermark_text) if settings.watermark_text else "выключен"
    background = "своя медиа" if has_background else settings.background_color
    return (
        f"{APPS.html} <b>Рендер</b>\n"
        "<blockquote>Отправьте эмодзи Telegram, стикер или ссылку на набор. Своя медиа используется как сохранённый фон.</blockquote>\n"
        f"\n{SETTINGS.html} <b>Конфигурация</b>\n"
        f"<blockquote>Фон: <code>{background}</code>\n"
        f"Разрешение: {settings.width}×{settings.height} · {settings.fps} FPS\n"
        f"Формат: {format_labels[settings.output_format]}\n"
        f"Цвет эмодзи: {emoji_color}\n"
        f"Размер: {settings.emoji_size}%\nВодяной знак: {watermark}</blockquote>"
    )


def _history_text(entries: list[RenderHistoryEntry]) -> str:
    if not entries:
        return (
            f"{HISTORY.html} <b>История рендеров</b>\n\n"
            "<blockquote>История пока пуста. Здесь появятся последние 10 готовых рендеров.</blockquote>"
        )

    format_labels = {
        OutputFormat.GIF: "GIF",
        OutputFormat.VIDEO: "Видео",
        OutputFormat.FILE: "Файл",
    }
    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        try:
            created_at = datetime.fromisoformat(entry.created_at).astimezone().strftime("%d.%m %H:%M")
        except ValueError:
            created_at = "без даты"
        source_label = entry.sources[0].label if entry.sources else "Медиа"
        if len(entry.sources) > 1:
            source_label = f"{source_label} +{len(entry.sources) - 1}"
        lines.append(
            f"{index}. {created_at} · {escape(source_label)} · "
            f"{entry.settings.width}×{entry.settings.height} · "
            f"{format_labels[entry.settings.output_format]} · {entry.duration:.1f} сек."
        )
    return (
        f"{HISTORY.html} <b>История рендеров</b>\n\n"
        "<blockquote>Нажмите на запись, чтобы повторить её с прежними настройками.\n\n"
        f"{'\n'.join(lines)}</blockquote>"
    )


def _size_text(value: int) -> str:
    return (
        "↔️ <b>Размер эмодзи</b>\n\n"
        f"<blockquote>Текущий размер: <b>{value}%</b>. Процент считается от высоты холста; при нескольких элементах масштаб автоматически уменьшается.</blockquote>"
    )


def _watermark_text(settings: RenderSettings) -> str:
    status = escape(settings.watermark_text) if settings.watermark_text else "не задан"
    return (
        f"{TAG.html} <b>Водяной знак</b>\n\n"
        f"<blockquote>Текст: {status}\nШрифт: {escape(settings.watermark_font)}\n"
        f"Цвет: <code>{settings.watermark_color}</code>\n"
        f"Размер: {settings.watermark_size}%</blockquote>"
    )


def _background_from_settings(settings: RenderSettings) -> RenderSource | None:
    if not settings.custom_background_file_id or not settings.custom_background_suffix:
        return None
    return RenderSource(
        kind=SourceKind.USER_MEDIA,
        file_id=settings.custom_background_file_id,
        suffix=settings.custom_background_suffix,
        label=settings.custom_background_label or "Своя медиа",
        recolorable=False,
    )


def _settings_with_background(
    settings: RenderSettings,
    source: RenderSource,
) -> RenderSettings:
    return replace(
        settings,
        custom_background_file_id=source.file_id,
        custom_background_suffix=source.suffix,
        custom_background_label=source.label,
    )


async def _ensure_background_in_state(
    state: FSMContext,
    settings: RenderSettings,
) -> RenderSource | None:
    data = await state.get_data()
    raw = data.get("render_background_source")
    if isinstance(raw, dict):
        return RenderSource.from_session_dict(raw)
    source = _background_from_settings(settings)
    if source is not None:
        await state.update_data(render_background_source=source.to_session_dict())
    return source


def _custom_emoji_ids(message: Message) -> list[str]:
    result: list[str] = []
    for entity in [*(message.entities or []), *(message.caption_entities or [])]:
        if str(entity.type) == "custom_emoji" and entity.custom_emoji_id:
            if entity.custom_emoji_id not in result:
                result.append(entity.custom_emoji_id)
    return result


async def _standard_animated_emoji_source(message: Message) -> RenderSource | None:
    """Resolve a standalone Unicode emoji to Telegram's official TGS asset.

    Bot API delivers standard animated emoji as plain message text, without a
    custom_emoji entity or file_id. The same animations are exposed through
    Telegram's official ``AnimatedEmojies`` sticker set, so cache that set and
    match the exact standalone emoji text to its downloadable sticker.
    """
    emoji = _emoji_key(getattr(message, "text", None) or "")
    if not emoji or any(character.isspace() for character in emoji):
        return None

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
                source = _source_from_sticker(sticker, SourceKind.CUSTOM_EMOJI)
                _ANIMATED_EMOJI_SOURCES[key] = source.to_session_dict()

    raw_source = _ANIMATED_EMOJI_SOURCES.get(emoji)
    return RenderSource.from_session_dict(raw_source) if raw_source else None


def _emoji_key(value: str) -> str:
    return value.strip().replace("\ufe0e", "").replace("\ufe0f", "")


def _source_from_sticker(sticker, kind: SourceKind) -> RenderSource:
    suffix = ".webm" if sticker.is_video else ".tgs" if sticker.is_animated else ".webp"
    return RenderSource(
        kind=kind,
        file_id=sticker.file_id,
        suffix=suffix,
        label=sticker.emoji or "Стикер",
        recolorable=True,
    )


def _source_from_message(
    message: Message,
    kind: SourceKind,
    recolorable: bool,
) -> RenderSource | None:
    if message.sticker:
        source = _source_from_sticker(message.sticker, kind)
        source.recolorable = recolorable
        return source
    if message.photo:
        return RenderSource(kind, message.photo[-1].file_id, ".jpg", "Фото", recolorable)
    if message.video:
        return RenderSource(kind, message.video.file_id, ".mp4", "Видео", recolorable)
    if message.animation:
        suffix = Path(message.animation.file_name or "").suffix.lower()
        if suffix not in {".gif", ".mp4"}:
            suffix = ".mp4"
        return RenderSource(kind, message.animation.file_id, suffix, "Анимация", recolorable)
    if message.document:
        suffix = Path(message.document.file_name or "").suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return None
        return RenderSource(kind, message.document.file_id, suffix, "Файл", recolorable)
    return None


def _message_file_size(message: Message) -> int | None:
    file = (
        message.document
        or message.video
        or message.animation
        or message.sticker
        or (message.photo[-1] if message.photo else None)
    )
    return getattr(file, "file_size", None) if file else None


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
