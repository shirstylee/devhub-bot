from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.services.render_models import OutputFormat, RenderSettings, WatermarkPosition
from bot.utils.premium_emoji import (
    ADD_TEXT,
    APPS,
    BACK,
    BRUSH,
    DELETE,
    ERROR,
    FILE,
    FONT,
    FORMAT,
    HISTORY,
    HOME,
    LOADING,
    LOCATION,
    MEDIA,
    SEND,
    SETTINGS,
    SHOW,
    SUCCESS,
    TAG,
    WRITE,
)

if TYPE_CHECKING:
    from bot.services.render_history import RenderHistoryEntry


COLOR_PICKER_URL = "https://htmlcolorcodes.com/color-picker/"
GOOGLE_FONTS_URL = "https://fonts.google.com/"


def renderer_main_keyboard(
    settings: RenderSettings,
    has_source: bool,
    has_background: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Цвет фона", callback_data="render:bg", icon_custom_emoji_id=BRUSH.emoji_id),
            InlineKeyboardButton(text="Разрешение", callback_data="render:resolution", icon_custom_emoji_id=FORMAT.emoji_id),
        ],
        [
            InlineKeyboardButton(text="Формат", callback_data="render:format", icon_custom_emoji_id=FORMAT.emoji_id),
            InlineKeyboardButton(
                text="Своя медиа",
                callback_data="render:media",
                style="success" if has_background else None,
                icon_custom_emoji_id=MEDIA.emoji_id,
            ),
        ],
        [
            InlineKeyboardButton(text="Цвет эмодзи", callback_data="render:emoji_color", icon_custom_emoji_id=BRUSH.emoji_id),
            InlineKeyboardButton(text="Водяной знак", callback_data="render:watermark", icon_custom_emoji_id=TAG.emoji_id),
        ],
        [
            InlineKeyboardButton(text="Предпросмотр", callback_data="render:preview", icon_custom_emoji_id=SHOW.emoji_id),
            InlineKeyboardButton(text="Размер эмодзи", callback_data="render:size", icon_custom_emoji_id=FORMAT.emoji_id),
        ],
    ]
    if has_source:
        rows.append([InlineKeyboardButton(text="Повторить рендер", callback_data="render:repeat", icon_custom_emoji_id=LOADING.emoji_id)])
    rows.append(
        [InlineKeyboardButton(text="История рендеров", callback_data="render:history", icon_custom_emoji_id=HISTORY.emoji_id)]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="По умолчанию",
                callback_data="render:defaults",
                style="danger",
                icon_custom_emoji_id=LOADING.emoji_id,
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="В главное меню", callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_result_keyboard(preview: bool = False) -> InlineKeyboardMarkup:
    repeat_label = "Предпросмотреть ещё" if preview else "Зарендерить ещё"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=repeat_label,
                    callback_data="render:again",
                    style="primary",
                    icon_custom_emoji_id=LOADING.emoji_id,
                )
            ],
            [InlineKeyboardButton(text="К настройкам", callback_data="render:settings", icon_custom_emoji_id=SETTINGS.emoji_id)],
            [InlineKeyboardButton(text="История рендеров", callback_data="render:history", icon_custom_emoji_id=HISTORY.emoji_id)],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def render_history_keyboard(entries: list["RenderHistoryEntry"]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    format_labels = {
        OutputFormat.GIF: "GIF",
        OutputFormat.VIDEO: "Видео",
        OutputFormat.FILE: "Файл",
    }
    for index, entry in enumerate(entries, start=1):
        labels = [source.label for source in entry.sources]
        source_label = labels[0] if labels else "Медиа"
        if len(labels) > 1:
            source_label = f"{source_label} +{len(labels) - 1}"
        if len(source_label) > 18:
            source_label = f"{source_label[:17]}…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{index}. {source_label} · "
                        f"{format_labels[entry.settings.output_format]}"
                    ),
                    callback_data=f"render:history:repeat:{entry.entry_id}",
                    icon_custom_emoji_id=LOADING.emoji_id,
                )
            ]
        )
    if entries:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Очистить историю",
                    callback_data="render:history:clear",
                    style="danger",
                    icon_custom_emoji_id=DELETE.emoji_id,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="К настройкам", callback_data="render:home", icon_custom_emoji_id=SETTINGS.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_again_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="К настройкам", callback_data="render:settings", icon_custom_emoji_id=SETTINGS.emoji_id)],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def custom_media_keyboard(has_background: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Загрузить медиа",
                callback_data="render:media:upload",
                style="primary",
                icon_custom_emoji_id=SEND.emoji_id,
            )
        ]
    ]
    if has_background:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Удалить свой фон",
                    callback_data="render:media:clear",
                    style="danger",
                    icon_custom_emoji_id=DELETE.emoji_id,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="По умолчанию",
                callback_data="render:default:media",
                style="danger",
                icon_custom_emoji_id=SETTINGS.emoji_id,
            )
        ]
    )
    rows.append([InlineKeyboardButton(text=f"{BACK} Назад", callback_data="render:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def color_input_keyboard(
    back_callback: str,
    allow_original: bool = False,
    default_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Подобрать цвет",
                web_app=WebAppInfo(url=COLOR_PICKER_URL),
                style="primary",
                icon_custom_emoji_id=BRUSH.emoji_id,
            )
        ]
    ]
    if allow_original:
        rows.append(
            [InlineKeyboardButton(text="Оригинальный цвет", callback_data="render:emoji_color:reset", icon_custom_emoji_id=BRUSH.emoji_id)]
        )
    if default_callback:
        rows.append(
            [
                InlineKeyboardButton(
                    text="По умолчанию",
                    callback_data=default_callback,
                    style="danger",
                    icon_custom_emoji_id=SETTINGS.emoji_id,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=f"{BACK} Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renderer_back_keyboard(
    callback_data: str = "render:home",
    default_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if default_callback:
        rows.append(
            [
                InlineKeyboardButton(
                    text="По умолчанию",
                    callback_data=default_callback,
                    style="danger",
                    icon_custom_emoji_id=SETTINGS.emoji_id,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=f"{BACK} Назад", callback_data=callback_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_keyboard(selected: OutputFormat) -> InlineKeyboardMarkup:
    labels = {
        OutputFormat.GIF: ("GIF", MEDIA.emoji_id),
        OutputFormat.VIDEO: ("Видео", MEDIA.emoji_id),
        OutputFormat.FILE: ("Файл", FILE.emoji_id),
    }
    buttons = [
        InlineKeyboardButton(
            text=labels[value][0],
            callback_data=f"render:format:{value.value}",
            style="success" if selected == value else None,
            icon_custom_emoji_id=labels[value][1],
        )
        for value in OutputFormat
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons,
            [
                InlineKeyboardButton(
                    text="По умолчанию",
                    callback_data="render:default:format",
                    style="danger",
                    icon_custom_emoji_id=SETTINGS.emoji_id,
                )
            ],
            [InlineKeyboardButton(text=f"{BACK} Назад", callback_data="render:home")],
        ]
    )


def size_keyboard(selected: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="−", callback_data="render:size:down"),
                InlineKeyboardButton(
                    text=f"Размер: {selected}%",
                    callback_data="render:noop",
                    style="success",
                ),
                InlineKeyboardButton(text="+", callback_data="render:size:up"),
            ],
            [InlineKeyboardButton(text="Ввести свой размер", callback_data="render:size:input", icon_custom_emoji_id=WRITE.emoji_id)],
            [
                InlineKeyboardButton(
                    text="По умолчанию",
                    callback_data="render:default:emoji_size",
                    style="danger",
                    icon_custom_emoji_id=SETTINGS.emoji_id,
                )
            ],
            [InlineKeyboardButton(text=f"{BACK} Назад", callback_data="render:home")],
        ]
    )


def watermark_keyboard(settings: RenderSettings) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Название", callback_data="render:watermark:name", icon_custom_emoji_id=ADD_TEXT.emoji_id),
            InlineKeyboardButton(text="Шрифт", callback_data="render:watermark:font", icon_custom_emoji_id=FONT.emoji_id),
        ],
        [
            InlineKeyboardButton(text="Цвет", callback_data="render:watermark:color", icon_custom_emoji_id=BRUSH.emoji_id),
            InlineKeyboardButton(text="Позиция", callback_data="render:watermark:position", icon_custom_emoji_id=LOCATION.emoji_id),
        ],
        [
            InlineKeyboardButton(text="−", callback_data="render:watermark:size:down"),
            InlineKeyboardButton(
                text=f"Размер: {settings.watermark_size}%",
                callback_data="render:noop",
                style="success",
            ),
            InlineKeyboardButton(text="+", callback_data="render:watermark:size:up"),
        ],
        [
            InlineKeyboardButton(
                text="Ввести размер водяного знака",
                callback_data="render:watermark:size:input",
                icon_custom_emoji_id=WRITE.emoji_id,
            )
        ],
    ]
    if settings.watermark_text:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Отключить водяной знак",
                    callback_data="render:watermark:disable",
                    style="danger",
                    icon_custom_emoji_id=DELETE.emoji_id,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="По умолчанию",
                callback_data="render:default:watermark",
                style="danger",
                icon_custom_emoji_id=SETTINGS.emoji_id,
            )
        ]
    )
    rows.append([InlineKeyboardButton(text=f"{BACK} Назад", callback_data="render:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def font_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть Google Fonts",
                    web_app=WebAppInfo(url=GOOGLE_FONTS_URL),
                    style="primary",
                    icon_custom_emoji_id=FONT.emoji_id,
                )
            ],
            [
                InlineKeyboardButton(
                    text="По умолчанию",
                    callback_data="render:default:watermark_font",
                    style="danger",
                    icon_custom_emoji_id=SETTINGS.emoji_id,
                )
            ],
            [InlineKeyboardButton(text=f"{BACK} Назад", callback_data="render:watermark")],
        ]
    )


def position_keyboard(selected: WatermarkPosition) -> InlineKeyboardMarkup:
    options = (
        (WatermarkPosition.TOP_LEFT, "Слева сверху"),
        (WatermarkPosition.TOP_RIGHT, "Справа сверху"),
        (WatermarkPosition.BOTTOM_LEFT, "Слева снизу"),
        (WatermarkPosition.BOTTOM_RIGHT, "Справа снизу"),
    )
    buttons = [
        InlineKeyboardButton(
            text=label,
            callback_data=f"render:position:{position.value}",
            style="success" if selected == position else None,
            icon_custom_emoji_id=SUCCESS.emoji_id if selected == position else LOCATION.emoji_id,
        )
        for position, label in options
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons[:2],
            buttons[2:],
            [
                InlineKeyboardButton(
                    text="По умолчанию",
                    callback_data="render:default:watermark_position",
                    style="danger",
                    icon_custom_emoji_id=SETTINGS.emoji_id,
                )
            ],
            [InlineKeyboardButton(text=f"{BACK} Назад", callback_data="render:watermark")],
        ]
    )


def pack_keyboard(
    items: list[dict],
    selected: set[int],
    page: int,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    page_count = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, page_count - 1))
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for local_index in range(0, min(page_size, len(items) - start), 2):
        row: list[InlineKeyboardButton] = []
        for offset in (0, 1):
            index = start + local_index + offset
            if index >= len(items) or index >= start + page_size:
                continue
            emoji = items[index].get("label") or "Эмодзи"
            row.append(
                InlineKeyboardButton(
                    text=f"{index + 1}. {emoji}",
                    callback_data=f"render:pack:toggle:{index}",
                    style="success" if index in selected else None,
                )
            )
        rows.append(row)
    if page_count > 1:
        rows.append(
            [
                InlineKeyboardButton(text=BACK, callback_data=f"render:pack:page:{max(0, page - 1)}"),
                InlineKeyboardButton(text=f"{page + 1}/{page_count}", callback_data="render:noop"),
                InlineKeyboardButton(
                    text="Вперёд", callback_data=f"render:pack:page:{min(page_count - 1, page + 1)}"
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Рендер ({len(selected)}/10)",
                callback_data="render:pack:confirm",
                style="success" if selected else None,
                icon_custom_emoji_id=APPS.emoji_id,
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="render:home", icon_custom_emoji_id=ERROR.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
