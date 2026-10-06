from collections.abc import Awaitable, Callable
import re
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.administrators import administrator_store


ADMIN_COMMAND = re.compile(r"^/admin(?:@[A-Za-z0-9_]+)?(?:\s|$)", re.IGNORECASE)


def is_private_admin(event: Message | CallbackQuery) -> bool:
    message = event if isinstance(event, Message) else event.message
    return bool(
        event.from_user and isinstance(message, Message)
        and message.chat.type == "private" and administrator_store.is_admin(event.from_user.id)
    )


class AdminAccessMiddleware(BaseMiddleware):
    """Silently reject admin events before the language prompt or tool handlers."""

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, data: dict[str, Any],
    ) -> Any:
        raw_state = data.get("raw_state")
        if raw_state is None and data.get("state") is not None:
            raw_state = await data["state"].get_state()
        admin_event = (
            isinstance(event, Message) and (
                ADMIN_COMMAND.match(event.text or "")
                or str(raw_state or "").startswith("AdminStates:")
            )
            or isinstance(event, CallbackQuery) and (event.data or "").startswith("admin:")
        )
        if admin_event:
            if not is_private_admin(event):
                return None
            data["admin_event"] = True
        return await handler(event, data)
