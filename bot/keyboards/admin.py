from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import tr
from bot.services.administrators import administrator_store
from bot.utils.premium_emoji import (
    APPROVE_USER, BACK_ICON, DELETE, HOME, INFO, PEOPLE, REFRESH, SETTINGS, STATISTICS,
)


def button(text: str, action: str, icon) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"admin:{action}", icon_custom_emoji_id=icon.emoji_id)


def admin_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(tr(lang, "Администраторы", "Administrators"), "admins:0", PEOPLE),
         button(tr(lang, "Статистика", "Statistics"), "statistics", STATISTICS)],
        [button(tr(lang, "Хранение данных", "Data storage"), "privacy", INFO)],
        [button(tr(lang, "Сбросить мои настройки", "Reset my settings"), "reset", SETTINGS),
         button(tr(lang, "Обновить", "Refresh"), "home", REFRESH)],
        [button(tr(lang, "Главное меню", "Main menu"), "menu", HOME)],
    ])


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(tr(lang, "Назад", "Back"), "home", BACK_ICON)],
    ])


def administrators_keyboard(actor_id: int, lang: str, page: int = 0) -> InlineKeyboardMarkup:
    ids = administrator_store.list_ids()
    rows = []
    if administrator_store.can_manage(actor_id):
        rows.append([button(tr(lang, "Добавить администратора", "Add administrator"), "add", APPROVE_USER)])
        for user_id in ids[page * 10:page * 10 + 10]:
            if user_id not in administrator_store.primary_ids:
                rows.append([button(tr(lang, f"Удалить {user_id}", f"Remove {user_id}"), f"remove:{user_id}", DELETE)])
    navigation = []
    if page:
        navigation.append(button("←", f"admins:{page - 1}", BACK_ICON))
    if (page + 1) * 10 < len(ids):
        navigation.append(button("→", f"admins:{page + 1}", PEOPLE))
    if navigation:
        rows.append(navigation)
    rows.append([button(tr(lang, "Назад", "Back"), "home", BACK_ICON)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard(action: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(tr(lang, "Подтвердить", "Confirm"), action, DELETE)],
        [button(tr(lang, "Отмена", "Cancel"), "home", BACK_ICON)],
    ])


def privacy_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(tr(lang, "Очистить старые записи неадминистраторов", "Clean old non-admin records"), "prune", DELETE)],
        [button(tr(lang, "Назад", "Back"), "home", BACK_ICON)],
    ])
