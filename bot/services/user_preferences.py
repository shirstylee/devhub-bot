from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any

from bot.config import BASE_DIR
from bot.services.private_storage import AdminOnlyJsonStore


STORE_VERSION = 1
PREFERENCES_PATH = BASE_DIR / "bot" / "data" / "user_preferences.json"


class UserPreferencesStore(AdminOnlyJsonStore):
    """Administrator settings on disk; ordinary users use bounded session memory."""

    def __init__(self, path: Path = PREFERENCES_PATH, *, is_admin=None) -> None:
        super().__init__(path, is_admin=is_admin)

    async def load_section(
        self,
        user_id: int,
        section: str,
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._lock:
            if self._is_admin(user_id):
                payload = await asyncio.to_thread(self._read_payload)
            else:
                if section == "language":
                    return deepcopy(defaults)
                payload = {"users": {str(user_id): self._sessions.get(user_id)}}
        user = payload.get("users", {}).get(str(user_id), {})
        saved = user.get(section, {}) if isinstance(user, dict) else {}
        result = deepcopy(defaults)
        if isinstance(saved, dict):
            for key in defaults:
                if key in saved:
                    result[key] = deepcopy(saved[key])
        return result

    async def save_section(
        self,
        user_id: int,
        section: str,
        settings: dict[str, Any],
    ) -> None:
        async with self._lock:
            if not self._is_admin(user_id):
                # Guest language always comes from Telegram, never from a session preference.
                if section == "language":
                    return
                user = self._sessions.get(user_id)
                user[section] = deepcopy(settings)
                self._sessions.put(user_id, user)
                return
            await asyncio.to_thread(
                self._save_section_sync,
                user_id,
                section,
                deepcopy(settings),
            )

    def _save_section_sync(
        self,
        user_id: int,
        section: str,
        settings: dict[str, Any],
    ) -> None:
        if not self._is_admin(user_id):
            return
        payload = self._read_payload()
        payload["version"] = STORE_VERSION
        users = payload.setdefault("users", {})
        user = users.setdefault(str(user_id), {})
        if not isinstance(user, dict):
            user = {}
            users[str(user_id)] = user
        user[section] = settings

        self._write_payload(payload)


user_preferences_store = UserPreferencesStore()
