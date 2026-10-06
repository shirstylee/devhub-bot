from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.statistics import statistics


class StatisticsMiddleware(BaseMiddleware):
    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, data: dict[str, Any],
    ) -> Any:
        if not data.get("admin_event") and isinstance(event, (Message, CallbackQuery)):
            statistics.record(event)
        try:
            return await handler(event, data)
        except Exception:
            statistics.errors += 1
            raise
