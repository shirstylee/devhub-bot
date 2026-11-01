from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from bot.utils.temp_files import TemporaryFileManager, temporary_files


DIALOG_TTL = 15 * 60


@dataclass
class Dialog:
    expires_at: float
    state: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class ExpiringMemoryStorage(BaseStorage):
    """Expiring FSM only. No disk writes or changes to administrator preferences."""

    def __init__(self, *, ttl: float = DIALOG_TTL, clock: Callable[[], float] = monotonic,
                 files: TemporaryFileManager = temporary_files) -> None:
        if ttl <= 0:
            raise ValueError("Dialog TTL must be positive")
        self.ttl = ttl
        self.clock = clock
        self.files = files
        self.dialogs: dict[StorageKey, Dialog] = {}
        self._active: dict[StorageKey, int] = {}

    def _discard(self, key: StorageKey) -> None:
        dialog = self.dialogs.pop(key, None)
        if dialog is not None:
            self.files.delete(self.files.paths_in(dialog.data))

    def _read(self, key: StorageKey) -> Dialog | None:
        dialog = self.dialogs.get(key)
        if dialog is not None:
            if dialog.expires_at <= self.clock() and not self._active.get(key):
                self._discard(key)
                return None
            dialog.expires_at = self.clock() + self.ttl
        return dialog

    def _write(self, key: StorageKey) -> Dialog:
        dialog = self._read(key)
        if dialog is None:
            dialog = Dialog(self.clock() + self.ttl)
            self.dialogs[key] = dialog
        return dialog

    @contextmanager
    def protect(self, key: StorageKey):
        self._active[key] = self._active.get(key, 0) + 1
        try:
            yield
        finally:
            count = self._active[key] - 1
            if count:
                self._active[key] = count
            else:
                del self._active[key]
            if key in self.dialogs:
                self.dialogs[key].expires_at = self.clock() + self.ttl

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        if value is None and key not in self.dialogs:
            return
        dialog = self._write(key)
        dialog.state = value
        if value is None and not dialog.data:
            self.dialogs.pop(key, None)

    async def get_state(self, key: StorageKey) -> str | None:
        dialog = self._read(key)
        return dialog.state if dialog is not None else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            raise DataNotDictLikeError(f"Data must be a dict or dict-like object, got {type(data).__name__}")
        previous = self._read(key)
        previous_paths = self.files.paths_in(previous.data) if previous is not None else set()
        self.files.delete(previous_paths - self.files.paths_in(data))
        if not data and (previous is None or previous.state is None):
            self.dialogs.pop(key, None)
            return
        self._write(key).data = data.copy()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        dialog = self._read(key)
        return dialog.data.copy() if dialog is not None else {}

    async def get_value(self, storage_key: StorageKey, dict_key: str, default: Any = None) -> Any:
        return copy((await self.get_data(storage_key)).get(dict_key, default))

    def expire(self) -> int:
        keys = [key for key, dialog in self.dialogs.items()
                if dialog.expires_at <= self.clock() and not self._active.get(key)]
        for key in keys:
            self._discard(key)
        return len(keys)

    def forget_paths(self, owners: set[Path], *, key: StorageKey | None = None) -> None:
        # Removing an expired file reference is not user activity: do not renew TTL.
        if not owners:
            return
        if key is None:
            dialogs = list(self.dialogs.items())
        else:
            dialogs = [(key, self.dialogs[key])] if key in self.dialogs else []
        for dialog_key, dialog in dialogs:
            dialog.data = self.files.without_paths(dialog.data, owners)
            if not dialog.data and dialog.state is None and not self._active.get(dialog_key):
                self.dialogs.pop(dialog_key, None)

    async def close(self) -> None:
        for key in tuple(self.dialogs):
            self._discard(key)
