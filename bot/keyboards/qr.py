from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import BOT, BROADCAST, HOME, LINK, PHONE, QR_CODE, SHOW


def qr_tools_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr(lang, "Текст или ссылка", "Text or link"), callback_data="qr:text", icon_custom_emoji_id=LINK.emoji_id),
                InlineKeyboardButton(text="WiFi", callback_data="qr:wifi", icon_custom_emoji_id=BROADCAST.emoji_id),
            ],
            [
                InlineKeyboardButton(text=tr(lang, "Телефон", "Phone"), callback_data="qr:phone", icon_custom_emoji_id=PHONE.emoji_id),
                InlineKeyboardButton(text="Telegram", callback_data="qr:telegram", icon_custom_emoji_id=BOT.emoji_id),
            ],
            [InlineKeyboardButton(text=tr(lang, "Сканировать QR", "Scan QR"), callback_data="qr:scan", icon_custom_emoji_id=QR_CODE.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
