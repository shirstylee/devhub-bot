from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import ERROR, HOME, LOADING, LOCKED, SETTINGS, SUCCESS, WRITE


def password_settings_keyboard(settings: dict[str, bool | int], lang: str = "ru") -> InlineKeyboardMarkup:
    length = int(settings["length"])
    count = int(settings.get("count", 1))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="−", callback_data="pwd:length:down"),
                InlineKeyboardButton(text=tr(lang, f"Длина: {length}", f"Length: {length}"), callback_data="pwd:noop"),
                InlineKeyboardButton(text="+", callback_data="pwd:length:up"),
            ],
            [InlineKeyboardButton(text=tr(lang, "Ввести длину", "Enter length"), callback_data="pwd:length:input", icon_custom_emoji_id=WRITE.emoji_id)],
            [
                InlineKeyboardButton(text="−", callback_data="pwd:count:down"),
                InlineKeyboardButton(text=tr(lang, f"Паролей: {count}", f"Passwords: {count}"), callback_data="pwd:noop"),
                InlineKeyboardButton(text="+", callback_data="pwd:count:up"),
            ],
            [InlineKeyboardButton(text=tr(lang, "Ввести количество паролей", "Enter password count"), callback_data="pwd:count:input", icon_custom_emoji_id=WRITE.emoji_id)],
            [
                InlineKeyboardButton(text=tr(lang, "Цифры", "Digits"), callback_data="pwd:toggle:digits", icon_custom_emoji_id=_flag_icon(settings["digits"])),
                InlineKeyboardButton(text=tr(lang, "Символы", "Symbols"), callback_data="pwd:toggle:symbols", icon_custom_emoji_id=_flag_icon(settings["symbols"])),
            ],
            [
                InlineKeyboardButton(text=tr(lang, "Заглавные", "Uppercase"), callback_data="pwd:toggle:uppercase", icon_custom_emoji_id=_flag_icon(settings["uppercase"])),
                InlineKeyboardButton(text=tr(lang, "Строчные", "Lowercase"), callback_data="pwd:toggle:lowercase", icon_custom_emoji_id=_flag_icon(settings["lowercase"])),
            ],
            [InlineKeyboardButton(text=tr(lang, "Сгенерировать", "Generate"), callback_data="pwd:generate", icon_custom_emoji_id=LOCKED.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def password_result_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, "Сгенерировать еще", "Generate again"), callback_data="pwd:generate", icon_custom_emoji_id=LOADING.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "Изменить настройки", "Change settings"), callback_data="pwd:settings", icon_custom_emoji_id=SETTINGS.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def _flag_icon(enabled: bool | int) -> str:
    return SUCCESS.emoji_id if enabled else ERROR.emoji_id
