from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards.code_screenshot import (
    BACKGROUND_LABELS,
    LANGUAGES,
    THEME_LABELS,
    code_background_keyboard,
    code_languages_keyboard,
    code_result_keyboard,
    code_settings_keyboard,
    code_themes_keyboard,
)
from bot.keyboards.main_menu import back_keyboard
from bot.i18n import tr
from bot.services.colors import hex_to_rgb
from bot.services.code_screenshot import create_code_screenshot
from bot.services.user_preferences import user_preferences_store
from bot.states import CodeScreenshotStates
from bot.utils.temp_files import cleanup_paths, make_temp_path
from bot.utils.premium_emoji import BRUSH, CODE, ERROR, SUCCESS
from bot.utils.messages import (
    answer_callback,
    decorate_panel_text,
    delete_user_message,
    edit_message_text,
    edit_stored_panel,
    edit_tool_photo,
    remember_panel,
)

router = Router(name="code_screenshot")
DEFAULT_CODE_PREFERENCES = {
    "theme": "seti",
    "language": "javascript",
    "background": "carbon",
}


@router.callback_query(F.data == "menu:code_screenshot")
async def open_code_screenshot(callback: CallbackQuery, state: FSMContext, lang: str = "ru") -> None:
    settings = await _load_code_preferences(callback.from_user.id)
    await state.set_state(CodeScreenshotStates.waiting_code)
    await _put_code_settings_in_state(state, settings)
    await edit_tool_photo(
        callback,
        "code",
        f"{CODE.html} <b>{tr(lang, 'Скриншот кода', 'Code screenshot')}</b>\n\n"
        + tr(lang, "Настройте тему, фон, язык и отправьте фрагмент кода.", "Choose a theme, background, and language, then send your code."),
        reply_markup=code_settings_keyboard(
            settings["theme"],
            settings["language"],
            settings["background"],
            lang,
        ),
    )


@router.callback_query(F.data == "code:noop")
async def noop(callback: CallbackQuery) -> None:
    await answer_callback(callback)


@router.callback_query(F.data == "code:panel:settings")
async def show_code_settings(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    settings = await _code_settings_from_state(state, callback.from_user.id)
    await edit_message_text(
        callback,
        f"{CODE.html} <b>{tr(lang, 'Скриншот кода', 'Code screenshot')}</b>\n\n"
        + tr(lang, "Настройте тему, фон, язык и отправьте фрагмент кода.", "Choose a theme, background, and language, then send your code."),
        reply_markup=code_settings_keyboard(
            settings["theme"],
            settings["language"],
            settings["background"],
            lang,
        ),
    )


@router.callback_query(F.data == "code:panel:themes")
async def show_code_themes(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    settings = await _code_settings_from_state(state, callback.from_user.id)
    await edit_message_text(callback, f"{BRUSH.html} <b>{tr(lang, 'Выберите тему оформления', 'Choose a theme')}</b>", reply_markup=code_themes_keyboard(settings["theme"], lang))


@router.callback_query(F.data == "code:panel:backgrounds")
async def show_code_backgrounds(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    settings = await _code_settings_from_state(state, callback.from_user.id)
    await edit_message_text(callback, f"{BRUSH.html} <b>{tr(lang, 'Выберите фон скриншота', 'Choose a screenshot background')}</b>", reply_markup=code_background_keyboard(settings["background"], lang))


@router.callback_query(F.data == "code:panel:languages")
async def show_code_languages(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    settings = await _code_settings_from_state(state, callback.from_user.id)
    await edit_message_text(callback, f"{CODE.html} <b>{tr(lang, 'Выберите язык кода', 'Choose a code language')}</b>", reply_markup=code_languages_keyboard(settings["language"], lang))


@router.callback_query(F.data.startswith("code:theme:"))
async def set_code_theme(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    theme = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    if theme not in THEME_LABELS:
        await answer_callback(callback)
        return
    settings = await _code_settings_from_state(state, callback.from_user.id)
    settings["theme"] = theme
    await state.update_data(code_theme=theme)
    await _save_code_preferences(callback.from_user.id, settings)
    await edit_message_text(callback, f"{BRUSH.html} <b>{tr(lang, 'Выберите тему оформления', 'Choose a theme')}</b>", reply_markup=code_themes_keyboard(theme, lang))


@router.callback_query(F.data.startswith("code:bg:"))
async def set_code_background(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    background = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    if background == "custom":
        await remember_panel(callback, state, "code")
        await state.set_state(CodeScreenshotStates.waiting_background_hex)
        await edit_message_text(callback, tr(lang, "Введите HEX цвет фона, например: <code>#000000</code>", "Enter a HEX background color, for example: <code>#000000</code>"), reply_markup=back_keyboard(lang))
        return
    if background not in BACKGROUND_LABELS:
        await answer_callback(callback)
        return
    settings = await _code_settings_from_state(state, callback.from_user.id)
    settings["background"] = background
    await state.update_data(code_background=background)
    await _save_code_preferences(callback.from_user.id, settings)
    await edit_message_text(callback, f"{BRUSH.html} <b>{tr(lang, 'Выберите фон скриншота', 'Choose a screenshot background')}</b>", reply_markup=code_background_keyboard(background, lang))


@router.message(CodeScreenshotStates.waiting_background_hex, F.text)
async def set_custom_background(message: Message, state: FSMContext, lang: str) -> None:
    try:
        hex_to_rgb(message.text or "")
    except ValueError as exc:
        await edit_stored_panel(message, state, f"{ERROR.html} {tr(lang, str(exc), 'Invalid HEX color.')}", reply_markup=back_keyboard(lang))
        return
    hex_color = message.text.strip()
    if not hex_color.startswith("#"):
        hex_color = f"#{hex_color}"
    hex_color = hex_color.upper()
    settings = await _code_settings_from_state(state, message.from_user.id)
    settings["background"] = hex_color
    await state.update_data(code_background=hex_color)
    await _save_code_preferences(message.from_user.id, settings)
    await state.set_state(CodeScreenshotStates.waiting_code)
    data = await state.get_data()
    await delete_user_message(message)
    await edit_stored_panel(
        message,
        state,
        f"{SUCCESS.html} {tr(lang, 'Фон обновлен. Отправьте код для скриншота.', 'Background updated. Send code for the screenshot.')}",
        reply_markup=code_settings_keyboard(
            data.get("code_theme", "seti"),
            data.get("code_language", "javascript"),
            data.get("code_background", "carbon"),
            lang,
        ),
    )


@router.callback_query(F.data.startswith("code:lang:"))
async def set_code_language(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    language = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    if language not in LANGUAGES:
        await answer_callback(callback)
        return
    settings = await _code_settings_from_state(state, callback.from_user.id)
    settings["language"] = language
    await state.update_data(code_language=language)
    await _save_code_preferences(callback.from_user.id, settings)
    await edit_message_text(callback, f"{CODE.html} <b>{tr(lang, 'Выберите язык кода', 'Choose a code language')}</b>", reply_markup=code_languages_keyboard(language, lang))


@router.message(CodeScreenshotStates.waiting_code, F.text)
async def render_code(message: Message, state: FSMContext, lang: str) -> None:
    settings = await _code_settings_from_state(state, message.from_user.id)
    output_path: Path = make_temp_path(".png")
    try:
        create_code_screenshot(
            code=message.text or "",
            output_path=output_path,
            language=settings["language"],
            theme=settings["theme"],
            background=settings["background"],
        )
        await message.answer_photo(
            photo=FSInputFile(output_path),
            caption=decorate_panel_text(
                f"{SUCCESS.html} <b>{tr(lang, 'Скриншот кода готов', 'Code screenshot is ready')}</b>\n\n"
                f"<blockquote>{tr(lang, 'Оформление в стиле Carbon · PNG высокого разрешения.', 'Carbon-style design · high-resolution PNG.')}</blockquote>"
            ),
            reply_markup=code_result_keyboard(lang),
        )
    finally:
        cleanup_paths(output_path)


async def _load_code_preferences(user_id: int) -> dict[str, str]:
    raw = await user_preferences_store.load_section(
        user_id,
        "code_screenshot",
        DEFAULT_CODE_PREFERENCES,
    )
    theme = str(raw.get("theme", DEFAULT_CODE_PREFERENCES["theme"]))
    language = str(raw.get("language", DEFAULT_CODE_PREFERENCES["language"]))
    background = str(raw.get("background", DEFAULT_CODE_PREFERENCES["background"]))
    if theme not in THEME_LABELS:
        theme = DEFAULT_CODE_PREFERENCES["theme"]
    if language not in LANGUAGES:
        language = DEFAULT_CODE_PREFERENCES["language"]
    if background not in BACKGROUND_LABELS:
        try:
            hex_to_rgb(background)
        except ValueError:
            background = DEFAULT_CODE_PREFERENCES["background"]
    return {"theme": theme, "language": language, "background": background}


async def _save_code_preferences(user_id: int, settings: dict[str, str]) -> None:
    await user_preferences_store.save_section(user_id, "code_screenshot", settings)


async def _put_code_settings_in_state(state: FSMContext, settings: dict[str, str]) -> None:
    await state.update_data(
        code_theme=settings["theme"],
        code_language=settings["language"],
        code_background=settings["background"],
    )


async def _code_settings_from_state(state: FSMContext, user_id: int) -> dict[str, str]:
    data = await state.get_data()
    if all(key in data for key in ("code_theme", "code_language", "code_background")):
        return {
            "theme": str(data["code_theme"]),
            "language": str(data["code_language"]),
            "background": str(data["code_background"]),
        }
    settings = await _load_code_preferences(user_id)
    await _put_code_settings_in_state(state, settings)
    return settings
