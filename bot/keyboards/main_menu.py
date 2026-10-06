from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import (
    BRUSH,
    CODE,
    FILE,
    HOME,
    LINK,
    LOCKED,
    PEOPLE,
    QR_CODE,
    TEXT,
    TRANSLATE,
)


def main_menu_keyboard(lang: str = "ru", *, allow_language_choice: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=tr(lang, "Форматировать JSON", "Format JSON"), callback_data="menu:json", icon_custom_emoji_id=CODE.emoji_id),
            InlineKeyboardButton(text=tr(lang, "Генератор паролей", "Password generator"), callback_data="menu:password", icon_custom_emoji_id=LOCKED.emoji_id),
        ],
        [
            InlineKeyboardButton(text=tr(lang, "Цвета", "Colors"), callback_data="menu:color", icon_custom_emoji_id=BRUSH.emoji_id),
            InlineKeyboardButton(text=tr(lang, "Конвертер файлов", "File converter"), callback_data="menu:file", icon_custom_emoji_id=FILE.emoji_id),
        ],
        [
            InlineKeyboardButton(text=tr(lang, "QR-инструменты", "QR tools"), callback_data="menu:qr", icon_custom_emoji_id=QR_CODE.emoji_id),
            InlineKeyboardButton(text=tr(lang, "Фейковые данные", "Fake data"), callback_data="menu:fake_data", icon_custom_emoji_id=PEOPLE.emoji_id),
        ],
        [
            InlineKeyboardButton(text=tr(lang, "Скриншот кода", "Code screenshot"), callback_data="menu:code_screenshot", icon_custom_emoji_id=CODE.emoji_id),
            InlineKeyboardButton(text=tr(lang, "Сократить ссылку", "Shorten a link"), callback_data="menu:shortener", icon_custom_emoji_id=LINK.emoji_id),
        ],
        [
            InlineKeyboardButton(text=tr(lang, "PDF-инструменты", "PDF tools"), callback_data="menu:pdf", icon_custom_emoji_id=FILE.emoji_id),
            InlineKeyboardButton(text=tr(lang, "Текстовые инструменты", "Text tools"), callback_data="menu:text_tools", icon_custom_emoji_id=TEXT.emoji_id),
        ],
    ]
    if allow_language_choice:
        rows.append([InlineKeyboardButton(text=tr(lang, "Язык", "Language"), callback_data="menu:language", icon_custom_emoji_id=TRANSLATE.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=tr(lang, "В главное меню", "Main menu"),
                callback_data="menu:back",
                icon_custom_emoji_id=HOME.emoji_id,
            )
        ]]
    )
