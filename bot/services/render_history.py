from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bot.config import BASE_DIR
from bot.services.render_models import RenderSettings, RenderSource
from bot.services.private_storage import AdminOnlyJsonStore


STORE_VERSION = 1
HISTORY_LIMIT = 10
HISTORY_PATH = BASE_DIR / "bot" / "data" / "render_history.json"


@dataclass(frozen=True, slots=True)
class RenderHistoryEntry:
    entry_id: str
    created_at: str
    settings: RenderSettings
    sources: list[RenderSource]
    background_source: RenderSource | None
    duration: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.entry_id,
            "created_at": self.created_at,
            "settings": self.settings.to_dict(),
            "sources": [source.to_session_dict() for source in self.sources],
            "background_source": (
                self.background_source.to_session_dict()
                if self.background_source is not None
                else None
            ),
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RenderHistoryEntry":
        source_items = raw.get("sources")
        if not isinstance(source_items, list) or not source_items:
            raise ValueError("Render history entry has no sources")
        background = raw.get("background_source")
        settings = raw.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("Render history entry has no settings")
        return cls(
            entry_id=str(raw["id"]),
            created_at=str(raw["created_at"]),
            settings=RenderSettings.from_dict(settings),
            sources=[RenderSource.from_session_dict(item) for item in source_items],
            background_source=(
                RenderSource.from_session_dict(background)
                if isinstance(background, dict)
                else None
            ),
            duration=max(0.0, float(raw.get("duration", 0.0))),
        )


class RenderHistoryStore(AdminOnlyJsonStore):
    def __init__(self, path: Path = HISTORY_PATH, *, is_admin=None) -> None:
        super().__init__(path, is_admin=is_admin)

    async def load(self, user_id: int) -> list[RenderHistoryEntry]:
        async with self._lock:
            if not self._is_admin(user_id):
                return []
            payload = await asyncio.to_thread(self._read_payload)
        entries: list[RenderHistoryEntry] = []
        raw_entries = payload.get("users", {}).get(str(user_id), [])
        if not isinstance(raw_entries, list):
            return entries
        for raw in raw_entries[:HISTORY_LIMIT]:
            if not isinstance(raw, dict):
                continue
            try:
                entries.append(RenderHistoryEntry.from_dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
        return entries

    async def add(
        self,
        user_id: int,
        settings: RenderSettings,
        sources: list[RenderSource],
        background_source: RenderSource | None,
        duration: float,
    ) -> RenderHistoryEntry:
        entry = RenderHistoryEntry(
            entry_id=secrets.token_hex(6),
            created_at=datetime.now(UTC).isoformat(),
            settings=RenderSettings.from_dict(settings.to_dict()),
            sources=[
                RenderSource.from_session_dict(source.to_session_dict())
                for source in sources
            ],
            background_source=(
                RenderSource.from_session_dict(background_source.to_session_dict())
                if background_source is not None
                else None
            ),
            duration=max(0.0, float(duration)),
        )
        async with self._lock:
            if self._is_admin(user_id):
                await asyncio.to_thread(self._add_sync, user_id, entry)
        return entry

    async def clear(self, user_id: int) -> None:
        async with self._lock:
            if self._is_admin(user_id):
                await asyncio.to_thread(self._clear_sync, user_id)

    def _add_sync(self, user_id: int, entry: RenderHistoryEntry) -> None:
        if not self._is_admin(user_id):
            return
        payload = self._read_payload()
        entries = payload.setdefault("users", {}).get(str(user_id), [])
        if not isinstance(entries, list):
            entries = []
        payload["users"][str(user_id)] = [entry.to_dict(), *entries][:HISTORY_LIMIT]
        self._write_payload(payload)

    def _clear_sync(self, user_id: int) -> None:
        payload = self._read_payload()
        payload.setdefault("users", {})[str(user_id)] = []
        self._write_payload(payload)


render_history_store = RenderHistoryStore()
