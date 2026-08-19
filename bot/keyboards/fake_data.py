from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import BOX, DE_FLAG, EN_FLAG, FR_FLAG, GB_FLAG, HOME, LOCATION, MONEY, PEOPLE, PROFILE, RU_FLAG, WRITE


COUNTRY_LABELS = {
    "ru": "Россия",
    "us": "США",
    "de": "Германия",
    "fr": "Франция",
    "gb": "Великобритания",
}


def country_label(country: str, lang: str = "ru") -> str:
    english = {"ru": "Russia", "us": "USA", "de": "Germany", "fr": "France", "gb": "United Kingdom"}
    return english[country] if lang == "en" else COUNTRY_LABELS[country]


def fake_country_keyboard(selected: str | None = None, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=country_label("ru", lang), callback_data="fake:country:ru", style="success" if selected == "ru" else None, icon_custom_emoji_id=RU_FLAG.emoji_id),
                InlineKeyboardButton(text=country_label("us", lang), callback_data="fake:country:us", style="success" if selected == "us" else None, icon_custom_emoji_id=EN_FLAG.emoji_id),
            ],
            [
                InlineKeyboardButton(text=country_label("de", lang), callback_data="fake:country:de", style="success" if selected == "de" else None, icon_custom_emoji_id=DE_FLAG.emoji_id),
                InlineKeyboardButton(text=country_label("fr", lang), callback_data="fake:country:fr", style="success" if selected == "fr" else None, icon_custom_emoji_id=FR_FLAG.emoji_id),
            ],
            [InlineKeyboardButton(text=country_label("gb", lang), callback_data="fake:country:gb", style="success" if selected == "gb" else None, icon_custom_emoji_id=GB_FLAG.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def fake_settings_keyboard(country: str, count: int, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="−", callback_data="fake:count:down"),
                InlineKeyboardButton(text=tr(lang, f"Записей: {count}", f"Records: {count}"), callback_data="fake:noop"),
                InlineKeyboardButton(text="+", callback_data="fake:count:up"),
            ],
            [InlineKeyboardButton(text=tr(lang, "Ввести количество", "Enter count"), callback_data="fake:count:input", icon_custom_emoji_id=WRITE.emoji_id)],
            [
                InlineKeyboardButton(text=tr(lang, "Персона", "Person"), callback_data="fake:generate:person", icon_custom_emoji_id=PROFILE.emoji_id),
                InlineKeyboardButton(text=tr(lang, "Компания", "Company"), callback_data="fake:generate:company", icon_custom_emoji_id=PEOPLE.emoji_id),
            ],
            [
                InlineKeyboardButton(text=tr(lang, "Платежные данные", "Payment data"), callback_data="fake:generate:payment", icon_custom_emoji_id=MONEY.emoji_id),
                InlineKeyboardButton(text=tr(lang, "Все сразу", "All fields"), callback_data="fake:generate:full", icon_custom_emoji_id=BOX.emoji_id),
            ],
            [InlineKeyboardButton(text=tr(lang, f"Страна: {country_label(country, lang)}", f"Country: {country_label(country, lang)}"), callback_data="fake:country_menu", icon_custom_emoji_id=LOCATION.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
