from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.services.sessions import ExpiringMemoryStorage
from bot.utils.temp_files import TemporaryFileManager, temporary_files


class LifecycleMiddleware(BaseMiddleware):
    def __init__(self, files: TemporaryFileManager = temporary_files) -> None:
        self.files = files

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        storage = state.storage if state is not None else None
        protected_storage = isinstance(storage, ExpiringMemoryStorage)
        hold = storage.protect(state.key) if protected_storage else nullcontext()
        with hold:
            existing = await state.get_data() if state is not None else {}
            with self.files.scope(self.files.paths_in(existing)) as scope:
                try:
                    result = await handler(event, data)
                except BaseException:
                    if protected_storage:
                        storage.forget_paths(scope.created, key=state.key)
                    raise
                if state is not None:
                    scope.retain(self.files.paths_in(await state.get_data()))
                return result
