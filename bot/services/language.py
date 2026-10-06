from __future__ import annotations

from bot.i18n import Language, SUPPORTED_LANGUAGES
from bot.services.administrators import administrator_store
from bot.services.user_preferences import user_preferences_store


LANGUAGE_SECTION = "language"


def get_telegram_language(language_code: str | None) -> Language:
    """Use the locale from this update, without caching or saving it."""
    base_language = (language_code or "").replace("_", "-").split("-", 1)[0].casefold()
    return "ru" if base_language == "ru" else "en"


async def get_user_language(user_id: int, telegram_language_code: str | None = None) -> Language | None:
    if not administrator_store.is_admin(user_id):
        return get_telegram_language(telegram_language_code)
    saved = await user_preferences_store.load_section(
        user_id,
        LANGUAGE_SECTION,
        {"code": None},
    )
    code = saved.get("code")
    if code in SUPPORTED_LANGUAGES:
        return code  # type: ignore[return-value]
    return None


async def set_user_language(user_id: int, language: str) -> Language:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("Unsupported language")
    if not administrator_store.is_admin(user_id):
        raise PermissionError("Only administrators can save a language preference.")
    await user_preferences_store.save_section(
        user_id,
        LANGUAGE_SECTION,
        {"code": language},
    )
    return language  # type: ignore[return-value]
