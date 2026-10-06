from __future__ import annotations

import asyncio
import json
from pathlib import Path

from bot.config import BASE_DIR, settings


ADMINS_PATH = BASE_DIR / "bot" / "data" / "administrators.json"


def parse_admin_id(value: str) -> int:
    value = value.strip()
    if not value.isascii() or not value.isdigit() or not 0 < int(value) < 2**52:
        raise ValueError("Введите положительный числовой Telegram user ID.")
    return int(value)


class AdministratorStore:
    """Only IDs are stored; configured primary administrators cannot be removed in the UI."""

    def __init__(self, path: Path = ADMINS_PATH, primary_ids: frozenset[int] | None = None) -> None:
        self.path = path
        self.primary_ids = settings.admin_ids if primary_ids is None else frozenset(primary_ids)
        self._additional_ids: frozenset[int] = frozenset()
        self._lock = asyncio.Lock()
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("admin_ids"), list):
                raise RuntimeError("Invalid administrators.json; refusing to load administrator permissions.")
            self._additional_ids = frozenset(
                parse_admin_id(str(value)) for value in payload["admin_ids"]
            ) - self.primary_ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.primary_ids or user_id in self._additional_ids

    def can_manage(self, user_id: int) -> bool:
        return user_id in self.primary_ids

    def list_ids(self) -> list[int]:
        return sorted(self.primary_ids | self._additional_ids)

    async def add(self, actor_id: int, user_id: int) -> bool:
        user_id = parse_admin_id(str(user_id))
        async with self._lock:
            if not self.can_manage(actor_id):
                raise PermissionError("Only configured primary administrators can manage permissions.")
            if self.is_admin(user_id):
                return False
            updated = self._additional_ids | {user_id}
            await asyncio.to_thread(self._write, updated)
            self._additional_ids = frozenset(updated)
            return True

    async def remove(self, actor_id: int, user_id: int) -> bool:
        async with self._lock:
            if not self.can_manage(actor_id):
                raise PermissionError("Only configured primary administrators can manage permissions.")
            if user_id in self.primary_ids:
                raise ValueError("Основной администратор задан в ADMIN_IDS и не удаляется через панель.")
            if user_id not in self._additional_ids:
                return False
            updated = self._additional_ids - {user_id}
            await asyncio.to_thread(self._write, updated)
            self._additional_ids = frozenset(updated)
            return True

    def _write(self, user_ids: frozenset[int] | set[int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "admin_ids": sorted(user_ids)}, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


administrator_store = AdministratorStore()
