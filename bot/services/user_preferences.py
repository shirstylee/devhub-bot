from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import logging
from pathlib import Path
from typing import Any

from bot.config import BASE_DIR


LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1
PREFERENCES_PATH = BASE_DIR / "bot" / "data" / "user_preferences.json"


class UserPreferencesStore:
    """Atomic JSON storage for reusable settings outside the emoji renderer."""

    def __init__(self, path: Path = PREFERENCES_PATH) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load_section(
        self,
        user_id: int,
        section: str,
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._lock:
            payload = await asyncio.to_thread(self._read_payload)
        saved = payload.get("users", {}).get(str(user_id), {}).get(section, {})
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
            await asyncio.to_thread(
                self._save_section_sync,
                user_id,
                section,
                deepcopy(settings),
            )

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": STORE_VERSION, "users": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("users", {}), dict):
                raise ValueError("Invalid user preferences structure")
            return payload
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.error("Could not read user preferences: %s", exc)
            return {"version": STORE_VERSION, "users": {}}

    def _save_section_sync(
        self,
        user_id: int,
        section: str,
        settings: dict[str, Any],
    ) -> None:
        payload = self._read_payload()
        payload["version"] = STORE_VERSION
        users = payload.setdefault("users", {})
        user = users.setdefault(str(user_id), {})
        if not isinstance(user, dict):
            user = {}
            users[str(user_id)] = user
        user[section] = settings

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


user_preferences_store = UserPreferencesStore()
