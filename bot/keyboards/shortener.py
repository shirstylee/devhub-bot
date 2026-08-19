from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import HOME, LINK


def shortener_keyboard(short_url: str | None = None, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    if short_url:
        rows.append([InlineKeyboardButton(text=tr(lang, "Открыть ссылку", "Open link"), url=short_url, icon_custom_emoji_id=LINK.emoji_id)])
    rows.append([InlineKeyboardButton(text=tr(lang, "Сократить еще", "Shorten another"), callback_data="menu:shortener", icon_custom_emoji_id=LINK.emoji_id)])
    rows.append([InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
