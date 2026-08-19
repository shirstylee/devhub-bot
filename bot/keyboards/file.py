from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import BOX, HOME


def file_actions_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr(lang, "В PNG", "To PNG"), callback_data="file:convert:png"),
                InlineKeyboardButton(text=tr(lang, "В JPG", "To JPG"), callback_data="file:convert:jpg"),
                InlineKeyboardButton(text=tr(lang, "В WEBP", "To WEBP"), callback_data="file:convert:webp"),
            ],
            [
                InlineKeyboardButton(text="800 px", callback_data="file:resize:800"),
                InlineKeyboardButton(text="1200 px", callback_data="file:resize:1200"),
                InlineKeyboardButton(text=tr(lang, "Сжать 50%", "Compress 50%"), callback_data="file:compress:50"),
            ],
            [InlineKeyboardButton(text=tr(lang, "Создать ZIP", "Create ZIP"), callback_data="file:zip", icon_custom_emoji_id=BOX.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
