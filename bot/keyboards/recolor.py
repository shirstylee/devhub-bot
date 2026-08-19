from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.premium_emoji import HOME, LOADING


def recolor_palette_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Красный", callback_data="recolor:color:FF3B30"),
                InlineKeyboardButton(text="Синий", callback_data="recolor:color:0A84FF"),
                InlineKeyboardButton(text="Зеленый", callback_data="recolor:color:32D74B"),
            ],
            [
                InlineKeyboardButton(text="Фиолетовый", callback_data="recolor:color:BF5AF2"),
                InlineKeyboardButton(text="Желтый", callback_data="recolor:color:FFD60A"),
                InlineKeyboardButton(text="Белый", callback_data="recolor:color:F2F2F7"),
            ],
            [InlineKeyboardButton(text="Ввести HEX", callback_data="recolor:custom")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def recolor_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перекрасить ещё",
                    callback_data="recolor:again",
                    style="primary",
                    icon_custom_emoji_id=LOADING.emoji_id,
                )
            ],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
