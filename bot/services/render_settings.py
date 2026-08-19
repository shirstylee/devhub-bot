from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from bot.config import BASE_DIR
from bot.services.render_models import RenderSettings


LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1
SETTINGS_PATH = BASE_DIR / "bot" / "data" / "render_settings.json"


class RenderSettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load(self, user_id: int) -> RenderSettings:
        async with self._lock:
            payload = await asyncio.to_thread(self._read_payload)
        raw = payload.get("users", {}).get(str(user_id), {})
        return RenderSettings.from_dict(raw) if isinstance(raw, dict) else RenderSettings()

    async def save(self, user_id: int, settings: RenderSettings) -> None:
        async with self._lock:
            await asyncio.to_thread(self._save_sync, user_id, settings)

    def _read_payload(self) -> dict:
        if not self.path.exists():
            return {"version": STORE_VERSION, "users": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("users", {}), dict):
                raise ValueError("Invalid render settings structure")
            return payload
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.error("Could not read render settings: %s", exc)
            return {"version": STORE_VERSION, "users": {}}

    def _save_sync(self, user_id: int, settings: RenderSettings) -> None:
        payload = self._read_payload()
        payload["version"] = STORE_VERSION
        payload.setdefault("users", {})[str(user_id)] = settings.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


render_settings_store = RenderSettingsStore()
