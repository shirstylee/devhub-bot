from __future__ import annotations

import asyncio
from pathlib import Path

from bot.config import BASE_DIR
from bot.services.render_models import RenderSettings
from bot.services.private_storage import AdminOnlyJsonStore


STORE_VERSION = 1
SETTINGS_PATH = BASE_DIR / "bot" / "data" / "render_settings.json"


class RenderSettingsStore(AdminOnlyJsonStore):
    def __init__(self, path: Path = SETTINGS_PATH, *, is_admin=None) -> None:
        super().__init__(path, is_admin=is_admin)

    async def load(self, user_id: int) -> RenderSettings:
        async with self._lock:
            if not self._is_admin(user_id):
                return RenderSettings.from_dict(self._sessions.get(user_id))
            payload = await asyncio.to_thread(self._read_payload)
        raw = payload.get("users", {}).get(str(user_id), {})
        return RenderSettings.from_dict(raw) if isinstance(raw, dict) else RenderSettings()

    async def save(self, user_id: int, settings: RenderSettings) -> None:
        async with self._lock:
            if not self._is_admin(user_id):
                self._sessions.put(user_id, settings.to_dict())
                return
            await asyncio.to_thread(self._save_sync, user_id, settings)

    def _save_sync(self, user_id: int, settings: RenderSettings) -> None:
        if not self._is_admin(user_id):
            return
        payload = self._read_payload()
        payload["version"] = STORE_VERSION
        payload.setdefault("users", {})[str(user_id)] = settings.to_dict()
        self._write_payload(payload)


render_settings_store = RenderSettingsStore()
