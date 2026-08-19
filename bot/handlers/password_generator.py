from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.password import password_result_keyboard, password_settings_keyboard
from bot.i18n import tr
from bot.services.passwords import copy_settings, generate_passwords
from bot.services.user_preferences import user_preferences_store
from bot.states import PasswordStates
from bot.utils.messages import (
    answer_callback,
    delete_user_message,
    edit_message_text,
    edit_stored_panel,
    edit_tool_photo,
    remember_panel,
)
from bot.utils.premium_emoji import ERROR, LOCKED

router = Router(name="password_generator")


@router.callback_query(F.data == "menu:password")
async def open_password_generator(callback: CallbackQuery, state: FSMContext, lang: str = "ru") -> None:
    settings = await _load_password_preferences(callback.from_user.id)
    await state.update_data(password_settings=settings)
    await edit_tool_photo(callback, "password", _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))


@router.callback_query(F.data.startswith("pwd:"))
async def handle_password_callbacks(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    settings = copy_settings(data.get("password_settings"))
    action = callback.data or ""

    if action == "pwd:noop":
        await answer_callback(callback)
        return

    if action == "pwd:length:up":
        settings["length"] = min(int(settings["length"]) + 1, 64)
        await _save_password_settings(callback.from_user.id, state, settings)
        await edit_message_text(callback, _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))
        return

    if action == "pwd:length:down":
        settings["length"] = max(int(settings["length"]) - 1, 6)
        await _save_password_settings(callback.from_user.id, state, settings)
        await edit_message_text(callback, _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))
        return

    if action == "pwd:length:input":
        await remember_panel(callback, state, "password")
        await state.set_state(PasswordStates.waiting_length)
        await edit_message_text(callback, tr(lang, "Введите длину пароля числом от 6 до 64.", "Enter a password length from 6 to 64."))
        return

    if action == "pwd:count:up":
        settings["count"] = min(int(settings.get("count", 1)) + 1, 10)
        await _save_password_settings(callback.from_user.id, state, settings)
        await edit_message_text(callback, _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))
        return

    if action == "pwd:count:down":
        settings["count"] = max(int(settings.get("count", 1)) - 1, 1)
        await _save_password_settings(callback.from_user.id, state, settings)
        await edit_message_text(callback, _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))
        return

    if action == "pwd:count:input":
        await remember_panel(callback, state, "password")
        await state.set_state(PasswordStates.waiting_count)
        await edit_message_text(callback, tr(lang, "Введите количество паролей числом от 1 до 10.", "Enter the number of passwords from 1 to 10."))
        return

    if action.startswith("pwd:toggle:"):
        key = action.rsplit(":", maxsplit=1)[-1]
        if key in settings:
            settings[key] = not bool(settings[key])
            await _save_password_settings(callback.from_user.id, state, settings)
            await edit_message_text(callback, _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))
        else:
            await answer_callback(callback)
        return

    if action == "pwd:settings":
        await edit_message_text(callback, _settings_text(settings, lang), reply_markup=password_settings_keyboard(settings, lang))
        return

    if action == "pwd:generate":
        try:
            passwords = generate_passwords(settings)
        except ValueError as exc:
            error = tr(
                lang,
                str(exc),
                "Select at least one character set." if "набор" in str(exc) else "The selected length is too short.",
            )
            await answer_callback(callback, error, show_alert=True)
            return
        text = "\n".join(f"<code>{escape(password)}</code>" for password in passwords)
        await edit_message_text(
            callback,
            f"{LOCKED.html} <b>{tr(lang, 'Надежные пароли', 'Secure passwords')}</b>\n\n{text}",
            reply_markup=password_result_keyboard(lang),
        )


@router.message(PasswordStates.waiting_length, F.text)
async def set_password_length(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    settings = copy_settings(data.get("password_settings"))
    try:
        length = int(message.text or "")
    except ValueError:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {tr(lang, 'Введите число от 6 до 64.', 'Enter a number from 6 to 64.')}",
            reply_markup=password_settings_keyboard(settings, lang),
        )
        return
    if length < 6 or length > 64:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {tr(lang, 'Длина должна быть от 6 до 64.', 'Length must be between 6 and 64.')}",
            reply_markup=password_settings_keyboard(settings, lang),
        )
        return
    settings["length"] = length
    await _save_password_settings(message.from_user.id, state, settings)
    await state.set_state(None)
    await delete_user_message(message)
    await edit_stored_panel(
        message,
        state,
        _settings_text(settings, lang),
        reply_markup=password_settings_keyboard(settings, lang),
    )


@router.message(PasswordStates.waiting_count, F.text)
async def set_password_count(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    settings = copy_settings(data.get("password_settings"))
    try:
        count = int(message.text or "")
    except ValueError:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {tr(lang, 'Введите число от 1 до 10.', 'Enter a number from 1 to 10.')}",
            reply_markup=password_settings_keyboard(settings, lang),
        )
        return
    if count < 1 or count > 10:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {tr(lang, 'Количество должно быть от 1 до 10.', 'Count must be between 1 and 10.')}",
            reply_markup=password_settings_keyboard(settings, lang),
        )
        return
    settings["count"] = count
    await _save_password_settings(message.from_user.id, state, settings)
    await state.set_state(None)
    await delete_user_message(message)
    await edit_stored_panel(
        message,
        state,
        _settings_text(settings, lang),
        reply_markup=password_settings_keyboard(settings, lang),
    )


def _settings_text(settings: dict[str, bool | int], lang: str = "ru") -> str:
    return (
        f"{LOCKED.html} <b>{tr(lang, 'Генератор паролей', 'Password generator')}</b>\n\n"
        f"{tr(lang, 'Настройте пароль через кнопки ниже.', 'Configure passwords using the buttons below.')}\n\n"
        f"{tr(lang, 'Длина', 'Length')}: <b>{settings['length']}</b>\n"
        f"{tr(lang, 'Количество', 'Count')}: <b>{settings.get('count', 1)}</b>"
    )


async def _load_password_preferences(user_id: int) -> dict[str, bool | int]:
    defaults = copy_settings()
    raw = await user_preferences_store.load_section(user_id, "password", defaults)
    try:
        length = max(6, min(64, int(raw.get("length", defaults["length"]))))
        count = max(1, min(10, int(raw.get("count", defaults["count"]))))
    except (TypeError, ValueError):
        length = int(defaults["length"])
        count = int(defaults["count"])
    return {
        "length": length,
        "count": count,
        "digits": raw.get("digits") if isinstance(raw.get("digits"), bool) else defaults["digits"],
        "symbols": raw.get("symbols") if isinstance(raw.get("symbols"), bool) else defaults["symbols"],
        "uppercase": raw.get("uppercase") if isinstance(raw.get("uppercase"), bool) else defaults["uppercase"],
        "lowercase": raw.get("lowercase") if isinstance(raw.get("lowercase"), bool) else defaults["lowercase"],
    }


async def _save_password_settings(
    user_id: int,
    state: FSMContext,
    settings: dict[str, bool | int],
) -> None:
    await state.update_data(password_settings=settings)
    await user_preferences_store.save_section(user_id, "password", settings)
