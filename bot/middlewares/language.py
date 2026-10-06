from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.keyboards.language import language_keyboard
from bot.services.language import get_telegram_language, get_user_language
from bot.utils.messages import answer_tool_photo
from bot.utils.premium_emoji import GLOBE


LANGUAGE_PROMPT = (
    f"{GLOBE.html} <b>Выберите язык / Choose your language</b>\n\n"
    "Выберите язык интерфейса.\n"
    "Choose the interface language."
)


class LanguageMiddleware(BaseMiddleware):
    """Use Telegram locale for guests; allow administrators to choose and save a language."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and (event.data or "").startswith("lang:"):
            return await handler(event, data)

        language = await get_user_language(user.id, user.language_code)
        if data.get("admin_event"):
            data["lang"] = language or get_telegram_language(user.language_code)
            return await handler(event, data)
        if language is None:
            await self._request_language(event)
            return None

        data["lang"] = language
        return await handler(event, data)

    @staticmethod
    async def _request_language(event: TelegramObject) -> None:
        if isinstance(event, Message):
            await answer_tool_photo(event, "language", LANGUAGE_PROMPT, reply_markup=language_keyboard())
            return
        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await answer_tool_photo(event.message, "language", LANGUAGE_PROMPT, reply_markup=language_keyboard())
