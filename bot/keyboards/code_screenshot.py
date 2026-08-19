from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.utils.premium_emoji import BRUSH, CODE, HOME, IMAGE, SETTINGS, SUCCESS, WRITE


LANGUAGES = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "csharp": "C#",
    "cpp": "C++",
    "go": "Go",
    "php": "PHP",
    "ruby": "Ruby",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "json": "JSON",
    "bash": "Bash",
    "text": "Без языка",
}

THEME_LABELS = {
    "seti": "Seti (Carbon)",
    "dracula_pro": "Dracula Pro",
    "duotone": "Duotone",
    "hopscotch": "Hopscotch",
    "lucario": "Lucario",
    "material": "Material",
    "monokai": "Monokai",
    "night_owl": "Night Owl",
    "nord": "Nord",
    "oceanic_next": "Oceanic Next",
}

BACKGROUND_LABELS = {
    "carbon": "Carbon",
    "black": "Черный",
    "navy": "Темно-синий",
    "purple": "Фиолетовый",
    "transparent": "Без фона",
}


def language_label(value: str, lang: str = "ru") -> str:
    if value == "text":
        return tr(lang, "Без языка", "Plain text")
    return LANGUAGES.get(value, value)


def background_label(value: str, lang: str = "ru") -> str:
    labels = {
        "carbon": "Carbon",
        "black": tr(lang, "Черный", "Black"),
        "navy": tr(lang, "Темно-синий", "Navy"),
        "purple": tr(lang, "Фиолетовый", "Purple"),
        "transparent": tr(lang, "Без фона", "Transparent"),
    }
    return labels.get(value, value)


def code_settings_keyboard(theme: str = "seti", language: str = "python", background: str = "carbon", lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, "Темы оформления", "Themes"), callback_data="code:panel:themes", icon_custom_emoji_id=BRUSH.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "Цвет фона", "Background color"), callback_data="code:panel:backgrounds", icon_custom_emoji_id=BRUSH.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "Язык кода", "Code language"), callback_data="code:panel:languages", icon_custom_emoji_id=CODE.emoji_id)],
            [
                InlineKeyboardButton(text=tr(lang, f"Тема: {THEME_LABELS.get(theme, theme)}", f"Theme: {THEME_LABELS.get(theme, theme)}"), callback_data="code:noop", icon_custom_emoji_id=BRUSH.emoji_id),
                InlineKeyboardButton(text=tr(lang, f"Фон: {background_label(background, lang)}", f"Background: {background_label(background, lang)}"), callback_data="code:noop", icon_custom_emoji_id=IMAGE.emoji_id),
            ],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )


def code_themes_keyboard(selected: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"code:theme:{value}",
                style="success" if value == selected else None,
                icon_custom_emoji_id=SUCCESS.emoji_id if value == selected else None,
            )
        ]
        for value, label in THEME_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text=tr(lang, "Назад к настройкам", "Back to settings"), callback_data="code:panel:settings", icon_custom_emoji_id=SETTINGS.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def code_background_keyboard(selected: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Carbon", callback_data="code:bg:carbon", style="success" if selected == "carbon" else None, icon_custom_emoji_id=SUCCESS.emoji_id if selected == "carbon" else None),
            InlineKeyboardButton(text=background_label("black", lang), callback_data="code:bg:black", style="success" if selected == "black" else None, icon_custom_emoji_id=SUCCESS.emoji_id if selected == "black" else None),
        ],
        [
            InlineKeyboardButton(text=background_label("navy", lang), callback_data="code:bg:navy", style="success" if selected == "navy" else None, icon_custom_emoji_id=SUCCESS.emoji_id if selected == "navy" else None),
            InlineKeyboardButton(text=background_label("purple", lang), callback_data="code:bg:purple", style="success" if selected == "purple" else None, icon_custom_emoji_id=SUCCESS.emoji_id if selected == "purple" else None),
        ],
        [InlineKeyboardButton(text=background_label("transparent", lang), callback_data="code:bg:transparent", style="success" if selected == "transparent" else None, icon_custom_emoji_id=SUCCESS.emoji_id if selected == "transparent" else None)],
        [InlineKeyboardButton(text=tr(lang, "Ввести HEX", "Enter HEX"), callback_data="code:bg:custom", icon_custom_emoji_id=WRITE.emoji_id)],
        [InlineKeyboardButton(text=tr(lang, "Назад к настройкам", "Back to settings"), callback_data="code:panel:settings", icon_custom_emoji_id=SETTINGS.emoji_id)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def code_languages_keyboard(selected: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    items = list(LANGUAGES.items())
    for index in range(0, len(items), 3):
        rows.append(
            [
                InlineKeyboardButton(
                    text=language_label(value, lang),
                    callback_data=f"code:lang:{value}",
                    style="success" if value == selected else None,
                    icon_custom_emoji_id=SUCCESS.emoji_id if value == selected else None,
                )
                for value, label in items[index : index + 3]
            ]
        )
    rows.append([InlineKeyboardButton(text=tr(lang, "Назад к настройкам", "Back to settings"), callback_data="code:panel:settings", icon_custom_emoji_id=SETTINGS.emoji_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def code_result_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, "Новый скриншот", "New screenshot"), callback_data="menu:code_screenshot", icon_custom_emoji_id=CODE.emoji_id)],
            [InlineKeyboardButton(text=tr(lang, "В главное меню", "Main menu"), callback_data="menu:back", icon_custom_emoji_id=HOME.emoji_id)],
        ]
    )
