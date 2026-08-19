from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import CODE, HASHTAG, HOME, LINK, LOCKED, REFRESH, UNLOCKED


def text_tools_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr(lang, "Base64: кодировать", "Base64 encode"), callback_data="text:op:base64_encode", icon_custom_emoji_id=LOCKED.emoji_id),
                InlineKeyboardButton(text=tr(lang, "Base64: декодировать", "Base64 decode"), callback_data="text:op:base64_decode", icon_custom_emoji_id=UNLOCKED.emoji_id),
            ],
            [
                InlineKeyboardButton(text=tr(lang, "URL: кодировать", "URL encode"), callback_data="text:op:url_encode", icon_custom_emoji_id=LINK.emoji_id),
                InlineKeyboardButton(text=tr(lang, "URL: декодировать", "URL decode"), callback_data="text:op:url_decode", icon_custom_emoji_id=CODE.emoji_id),
            ],
            [
                InlineKeyboardButton(text="SHA-256", callback_data="text:op:sha256", icon_custom_emoji_id=HASHTAG.emoji_id),
                InlineKeyboardButton(text="SHA-512", callback_data="text:op:sha512", icon_custom_emoji_id=HASHTAG.emoji_id),
            ],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def text_result_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, "Другая операция", "Another operation"), callback_data="text:home", icon_custom_emoji_id=REFRESH.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
