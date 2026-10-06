from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.i18n import tr
from bot.handlers.common import build_welcome_text
from bot.keyboards.admin import (
    admin_keyboard, administrators_keyboard, back_keyboard, confirmation_keyboard, privacy_keyboard,
)
from bot.keyboards.main_menu import main_menu_keyboard
from bot.middlewares.admin_access import is_private_admin
from bot.services.administrators import administrator_store, parse_admin_id
from bot.services.privacy import forget_user_data, prune_non_admin_data
from bot.services.statistics import TOOL_LABELS, statistics
from bot.states import AdminStates
from bot.utils.premium_emoji import (
    APPROVE_USER, BACK_ICON, BOT, BRUSH, CLOCK, CODE, DELETE, ERROR, FILE, INFO,
    LINK, LOCKED, PEOPLE, PROFILE, QR_CODE, REJECT_USER, SETTINGS, STATISTICS,
    SUCCESS, TEXT, TRANSLATE,
)
from bot.utils.temp_files import cleanup_paths
from bot.utils.messages import answer_tool_photo


router = Router(name="admin")
TOOL_ICONS = {
    "json": CODE, "password": LOCKED, "color": BRUSH, "file": FILE, "qr": QR_CODE,
    "fake_data": PEOPLE, "code_screenshot": CODE, "shortener": LINK, "pdf": FILE,
    "text_tools": TEXT,
}


def home_text(lang: str) -> str:
    return tr(lang,
        f"{SETTINGS.html} <b>Админ-панель</b>\n\n"
        f"{PEOPLE.html} <b>Администраторы</b> — роли и доступ к боту.\n"
        f"{STATISTICS.html} <b>Статистика</b> — активность и время работы.\n"
        f"{FILE.html} <b>Хранение данных</b> — политика и очистка записей.\n"
        f"{SETTINGS.html} <b>Мои настройки</b> — сброс языка, параметров и истории.\n\n"
        f"{LOCKED.html} Настройки на диске сохраняются только у администраторов.",
        f"{SETTINGS.html} <b>Admin panel</b>\n\n"
        f"{PEOPLE.html} <b>Administrators</b> — roles and bot access.\n"
        f"{STATISTICS.html} <b>Statistics</b> — activity and uptime.\n"
        f"{FILE.html} <b>Data storage</b> — policy and record cleanup.\n"
        f"{SETTINGS.html} <b>My settings</b> — reset language, preferences and history.\n\n"
        f"{LOCKED.html} Only administrators' settings are saved to disk.")


async def clear_state(state: FSMContext) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("file_input_path"), data.get("pdf_input_path"), data.get("pdf_images"))
    await state.clear()


async def edit_panel(callback: CallbackQuery, text: str, keyboard) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise


@router.message(Command("admin", ignore_case=True))
async def open_admin(message: Message, state: FSMContext, lang: str = "ru") -> None:
    if not is_private_admin(message):
        return
    await clear_state(state)
    await message.answer(home_text(lang), reply_markup=admin_keyboard(lang))


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(callback: CallbackQuery, state: FSMContext, lang: str = "ru") -> None:
    if not is_private_admin(callback):
        return
    actor_id = callback.from_user.id
    action = (callback.data or "")[6:]
    management = action == "add" or action.startswith(("remove:", "confirm_remove:"))
    if management and not administrator_store.can_manage(actor_id):
        await callback.answer(tr(lang, "Доступно только основным администраторам", "Primary administrators only"), show_alert=True)
        return

    await clear_state(state)
    if action == "home":
        await edit_panel(callback, home_text(lang), admin_keyboard(lang))
    elif action.startswith("admins:"):
        try:
            page = int(action.split(":", 1)[1])
        except ValueError:
            await callback.answer()
            return
        ids = administrator_store.list_ids()
        page = max(0, min(page, (len(ids) - 1) // 10))
        lines = [tr(lang, f"{PEOPLE.html} <b>Администраторы</b>\n", f"{PEOPLE.html} <b>Administrators</b>\n")]
        for user_id in ids[page * 10:page * 10 + 10]:
            primary = user_id in administrator_store.primary_ids
            role = tr(lang, "основной", "primary") if primary else tr(lang, "дополнительный", "additional")
            icon = LOCKED if primary else PROFILE
            lines.append(f"{icon.html} <code>{user_id}</code> — {role}")
        lines.append(tr(lang, f"\n{INFO.html} Основные ID задаются в <code>ADMIN_IDS</code> на сервере.\n{LOCKED.html} Только они управляют списком.",
                        f"\n{INFO.html} Primary IDs are configured in <code>ADMIN_IDS</code> on the server.\n{LOCKED.html} Only they can manage this list."))
        await edit_panel(callback, "\n".join(lines), administrators_keyboard(actor_id, lang, page))
    elif action == "add":
        await state.set_state(AdminStates.waiting_admin_id)
        await edit_panel(callback, tr(lang,
            f"{APPROVE_USER.html} <b>Добавить администратора</b>\n\n"
            f"{PROFILE.html} Отправьте числовой Telegram user ID нового администратора. Не @username.\n"
            f"{BACK_ICON.html} /cancel — отмена.",
            f"{APPROVE_USER.html} <b>Add administrator</b>\n\n"
            f"{PROFILE.html} Send the new administrator's numeric Telegram user ID, not an @username.\n"
            f"{BACK_ICON.html} /cancel to cancel."), back_keyboard(lang))
    elif action.startswith(("remove:", "confirm_remove:")):
        try:
            target = parse_admin_id(action.split(":", 1)[1])
            if target in administrator_store.primary_ids:
                raise ValueError("Primary administrator")
        except ValueError:
            await callback.answer(tr(lang, "Этот ID нельзя удалить здесь", "This ID cannot be removed here"), show_alert=True)
            return
        if action.startswith("confirm_remove:"):
            removed = await administrator_store.remove(actor_id, target)
            if not removed:
                await edit_panel(callback, tr(lang, f"{INFO.html} Этот ID уже не является дополнительным администратором.",
                    f"{INFO.html} This ID is no longer an additional administrator."), administrators_keyboard(actor_id, lang))
                return
            await forget_user_data(target)
            await edit_panel(callback, tr(lang, f"{REJECT_USER.html} Администратор удалён.\n{DELETE.html} Его сохранённые настройки очищены.",
                f"{REJECT_USER.html} Administrator removed.\n{DELETE.html} Their saved settings have been cleared."), administrators_keyboard(actor_id, lang))
        else:
            await edit_panel(callback, tr(lang, f"{REJECT_USER.html} <b>Удалить администратора?</b>\n\n{PROFILE.html} ID: <code>{target}</code>\n{DELETE.html} Его сохранённые настройки тоже будут удалены.",
                f"{REJECT_USER.html} <b>Remove administrator?</b>\n\n{PROFILE.html} ID: <code>{target}</code>\n{DELETE.html} Their saved settings will also be deleted."), confirmation_keyboard(f"confirm_remove:{target}", lang))
    elif action == "statistics":
        counters = statistics.snapshot()
        hours, remainder = divmod(counters["uptime_seconds"], 3600)
        minutes = remainder // 60
        lines = [tr(lang, f"{STATISTICS.html} <b>Статистика с запуска</b>", f"{STATISTICS.html} <b>Statistics since startup</b>"),
            tr(lang, f"{CLOCK.html} Время работы: {hours} ч {minutes} мин", f"{CLOCK.html} Uptime: {hours} h {minutes} min"),
            tr(lang, f"{TEXT.html} Сообщения: {counters['messages']}", f"{TEXT.html} Messages: {counters['messages']}"),
            tr(lang, f"{LINK.html} Нажатия кнопок: {counters['callbacks']}", f"{LINK.html} Button clicks: {counters['callbacks']}"),
            tr(lang, f"{ERROR.html} Ошибки обработчиков: {counters['errors']}", f"{ERROR.html} Handler errors: {counters['errors']}"),
            tr(lang, f"\n{CODE.html} <b>Нажатия инструментов:</b>", f"\n{CODE.html} <b>Tool button clicks:</b>")]
        lines.extend(f"{TOOL_ICONS[key].html} {TOOL_LABELS[key]}: {counters['tool_opens'].get(key, 0)}" for key in TOOL_LABELS)
        lines.append(tr(lang, f"\n{LOCKED.html} Без ID, имён и содержимого сообщений.\n{INFO.html} Счётчики только в памяти; админ-панель не учитывается.",
            f"\n{LOCKED.html} No IDs, names or message contents.\n{INFO.html} Counters are in memory only; admin panel traffic is excluded."))
        await edit_panel(callback, "\n".join(lines), back_keyboard(lang))
    elif action == "privacy":
        await edit_panel(callback, tr(lang,
            f"{INFO.html} <b>Хранение данных</b>\n\n"
            f"{FILE.html} На диске: только ID администраторов, их настройки и история рендера.\n"
            f"{TRANSLATE.html} Язык обычного пользователя берётся из Telegram и отдельно не сохраняется.\n"
            f"{CLOCK.html} Остальные настройки обычных пользователей временно в памяти (срок действия — 1 час бездействия, максимум 512 записей на хранилище); история не ведётся.\n"
            f"{DELETE.html} Просроченные записи очищаются при обращении к хранилищу.\n"
            f"{BOT.html} Диалоговые состояния и статистика — в оперативной памяти, без базы пользователей.\n"
            f"{LOCKED.html} При запуске старые записи неадминистраторов удаляются автоматически.\n\n"
            f"{INFO.html} Файлы для обработки временно скачиваются на диск. Это не означает отсутствия обработки персональных данных.",
            f"{INFO.html} <b>Data storage</b>\n\n"
            f"{FILE.html} On disk: administrator IDs, their settings and render history only.\n"
            f"{TRANSLATE.html} Ordinary users' language comes from Telegram and is not saved separately.\n"
            f"{CLOCK.html} Other settings of ordinary users: temporary in-memory settings (1-hour idle expiry, up to 512 entries per store); no history.\n"
            f"{DELETE.html} Expired entries are cleared when the store is accessed.\n"
            f"{BOT.html} Conversation state and statistics are in memory, with no user database.\n"
            f"{LOCKED.html} Old non-admin records are automatically removed at startup.\n\n"
            f"{INFO.html} Files are temporarily downloaded to disk for processing. This does not mean that no personal data is processed."), privacy_keyboard(lang))
    elif action == "prune":
        await edit_panel(callback, tr(lang, f"{DELETE.html} <b>Очистить старые записи?</b>\n\n{PROFILE.html} Будут удалены записи неадминистраторов.\n{LOCKED.html} Настройки администраторов останутся.",
            f"{DELETE.html} <b>Clean old records?</b>\n\n{PROFILE.html} Non-admin records will be removed.\n{LOCKED.html} Administrator settings will be kept."), confirmation_keyboard("confirm_prune", lang))
    elif action == "confirm_prune":
        removed = await prune_non_admin_data()
        await edit_panel(callback, tr(lang, f"{SUCCESS.html} Очистка завершена.\n{DELETE.html} Удалено записей: {removed}.",
            f"{SUCCESS.html} Cleanup completed.\n{DELETE.html} Records removed: {removed}."), privacy_keyboard(lang))
    elif action == "reset":
        await edit_panel(callback, tr(lang, f"{SETTINGS.html} <b>Сбросить ваши настройки?</b>\n\n{TRANSLATE.html} Выбранный язык, параметры инструментов и история будут удалены.\n{LOCKED.html} Настройки других администраторов останутся.",
            f"{SETTINGS.html} <b>Reset your settings?</b>\n\n{TRANSLATE.html} Your chosen language, tool preferences and history will be deleted.\n{LOCKED.html} Other administrators' settings will be kept."), confirmation_keyboard("confirm_reset", lang))
    elif action == "confirm_reset":
        await forget_user_data(actor_id)
        await edit_panel(callback, tr(lang, f"{SUCCESS.html} Ваши настройки и история сброшены.\n{TRANSLATE.html} Язык можно выбрать в /menu.",
            f"{SUCCESS.html} Your settings and history have been reset.\n{TRANSLATE.html} Choose your language in /menu."), admin_keyboard(lang))
    elif action in {"menu", "close"}:  # Support the old button in already sent panels too.
        await callback.answer()
        if isinstance(callback.message, Message):
            await answer_tool_photo(
                callback.message, "main", build_welcome_text(lang),
                reply_markup=main_menu_keyboard(lang, allow_language_choice=administrator_store.is_admin(actor_id)),
            )
            # Send the menu first so a failed delivery never leaves the user without a panel.
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except TelegramBadRequest:
                    pass
    else:
        await callback.answer()


@router.message(AdminStates.waiting_admin_id)
async def receive_admin_id(message: Message, state: FSMContext, lang: str = "ru") -> None:
    if not is_private_admin(message):
        return
    if not administrator_store.can_manage(message.from_user.id):
        await state.clear()
        return
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.answer(home_text(lang), reply_markup=admin_keyboard(lang))
        return
    try:
        target = parse_admin_id(message.text or "")
    except ValueError:
        await message.answer(tr(lang, f"{ERROR.html} Нужен положительный числовой Telegram user ID.\n{BACK_ICON.html} /cancel — отмена.",
            f"{ERROR.html} A positive numeric Telegram user ID is required.\n{BACK_ICON.html} /cancel to cancel."))
        return
    added = await administrator_store.add(message.from_user.id, target)
    await state.clear()
    text = tr(lang, f"{SUCCESS.html} Администратор добавлен.", f"{SUCCESS.html} Administrator added.") if added else tr(lang, f"{INFO.html} Этот ID уже является администратором.", f"{INFO.html} This ID is already an administrator.")
    await message.answer(text, reply_markup=administrators_keyboard(message.from_user.id, lang))
