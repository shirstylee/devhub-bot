from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bot.config import BASE_DIR
from bot.services.render_models import RenderSettings, RenderSource


LOGGER = logging.getLogger(__name__)
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


class RenderHistoryStore:
    def __init__(self, path: Path = HISTORY_PATH) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load(self, user_id: int) -> list[RenderHistoryEntry]:
        async with self._lock:
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
            await asyncio.to_thread(self._add_sync, user_id, entry)
        return entry

    async def clear(self, user_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._clear_sync, user_id)

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": STORE_VERSION, "users": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("users", {}), dict):
                raise ValueError("Invalid render history structure")
            return payload
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.error("Could not read render history: %s", exc)
            return {"version": STORE_VERSION, "users": {}}

    def _add_sync(self, user_id: int, entry: RenderHistoryEntry) -> None:
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

    def _write_payload(self, payload: dict[str, Any]) -> None:
        payload["version"] = STORE_VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


render_history_store = RenderHistoryStore()
