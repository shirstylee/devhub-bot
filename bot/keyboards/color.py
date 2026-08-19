from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import BRUSH, HOME


def color_tools_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="HEX → RGB", callback_data="color:hex"),
                InlineKeyboardButton(text="RGB → HEX", callback_data="color:rgb"),
            ],
            [InlineKeyboardButton(text=tr(lang, "Случайный цвет", "Random color"), callback_data="color:random", icon_custom_emoji_id=BRUSH.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
