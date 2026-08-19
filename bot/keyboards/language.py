from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import EN_FLAG, HOME, RU_FLAG


def language_keyboard(back_language: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Русский",
                callback_data="lang:ru",
                icon_custom_emoji_id=RU_FLAG.emoji_id,
            ),
            InlineKeyboardButton(
                text="English",
                callback_data="lang:en",
                icon_custom_emoji_id=EN_FLAG.emoji_id,
            ),
        ]
    ]
    if back_language is not None:
        rows.append([
            InlineKeyboardButton(
                text=tr(back_language, "Назад", "Back"),
                callback_data="menu:back",
                icon_custom_emoji_id=HOME.emoji_id,
            )
        ])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )
