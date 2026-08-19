from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import HOME, SUCCESS


def pdf_tools_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="PDF → PNG", callback_data="pdf:mode:pages_png"),
                InlineKeyboardButton(text="PDF → JPG", callback_data="pdf:mode:pages_jpg"),
            ],
            [
                InlineKeyboardButton(text=tr(lang, "Картинки → PDF", "Images → PDF"), callback_data="pdf:mode:images_to_pdf"),
                InlineKeyboardButton(text=tr(lang, "Достать картинки", "Extract images"), callback_data="pdf:mode:extract_images"),
            ],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def image_pdf_collect_keyboard(count: int, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, f"Создать PDF из {count} изображ.", f"Create PDF from {count} images"), callback_data="pdf:create_from_images", icon_custom_emoji_id=SUCCESS.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
