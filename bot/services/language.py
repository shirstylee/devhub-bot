from __future__ import annotations

from bot.i18n import Language, SUPPORTED_LANGUAGES
from bot.services.user_preferences import user_preferences_store


LANGUAGE_SECTION = "language"


async def get_user_language(user_id: int) -> Language | None:
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
    await user_preferences_store.save_section(
        user_id,
        LANGUAGE_SECTION,
        {"code": language},
    )
    return language  # type: ignore[return-value]
