from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
import json
import logging
from pathlib import Path
from time import monotonic
from typing import Any

from bot.services.administrators import administrator_store


LOGGER = logging.getLogger(__name__)
SESSION_TTL = 3600
MAX_SESSION_USERS = 512


class SessionCache:
    """Bounded, expiring process memory; nothing in this cache is written to disk."""

    def __init__(self, *, ttl: float = SESSION_TTL, max_users: int = MAX_SESSION_USERS,
                 clock: Callable[[], float] = monotonic) -> None:
        self.ttl = ttl
        self.max_users = max_users
        self.clock = clock
        self._users: OrderedDict[int, tuple[float, dict[str, Any]]] = OrderedDict()

    def _expire(self) -> None:
        now = self.clock()
        while self._users and next(iter(self._users.values()))[0] <= now:
            self._users.popitem(last=False)

    def get(self, user_id: int) -> dict[str, Any]:
        self._expire()
        entry = self._users.pop(user_id, None)
        if entry is None:
            return {}
        self._users[user_id] = (self.clock() + self.ttl, entry[1])
        return deepcopy(entry[1])

    def put(self, user_id: int, payload: dict[str, Any]) -> None:
        self._expire()
        self._users.pop(user_id, None)
        self._users[user_id] = (self.clock() + self.ttl, deepcopy(payload))
        while len(self._users) > self.max_users:
            self._users.popitem(last=False)

    def forget(self, user_id: int) -> None:
        self._users.pop(user_id, None)


class AdminOnlyJsonStore:
    def __init__(self, path: Path, *, is_admin: Callable[[int], bool] | None = None) -> None:
        self.path = path
        self._is_admin = administrator_store.is_admin if is_admin is None else is_admin
        self._lock = asyncio.Lock()
        self._sessions = SessionCache()

    def _filter_users(self, users: dict) -> dict:
        return {
            key: value for key, value in users.items()
            if isinstance(key, str) and key.isascii() and key.isdigit()
            and key == str(int(key)) and self._is_admin(int(key))
        }

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "users": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("users"), dict):
                raise ValueError("Invalid settings structure")
            return {"version": 1, "users": self._filter_users(payload["users"])}
        except (OSError, ValueError):
            LOGGER.error("Could not read settings file %s", self.path.name)
            return {"version": 1, "users": {}}

    def _write_payload(self, payload: dict[str, Any]) -> None:
        clean = {"version": 1, "users": self._filter_users(payload.get("users", {}))}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    async def prune_non_admins(self) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._prune_sync)

    def _prune_sync(self) -> int:
        removed = 0
        copies = []
        # A previous atomic write may have left a temporary copy containing old users.
        for path in (self.path, self.path.with_suffix(".tmp")):
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("users"), dict):
                    raise ValueError("Invalid settings structure")
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"Cannot safely clean {path.name}; fix this local file before startup.") from exc
            filtered = self._filter_users(payload["users"])
            removed += len(payload["users"]) - len(filtered)
            copies.append((path, payload["users"], filtered))
        # Validate both copies before changing either file.
        for path, original, filtered in copies:
            if path == self.path and filtered != original:
                self._write_payload({"version": 1, "users": filtered})
        temporary = self.path.with_suffix(".tmp")
        if temporary.exists():
            temporary.unlink()
        return removed

    async def forget_user(self, user_id: int) -> None:
        async with self._lock:
            self._sessions.forget(user_id)
            await asyncio.to_thread(self._forget_sync, user_id)

    def _forget_sync(self, user_id: int) -> None:
        if self.path.exists():
            payload = self._read_payload()
            payload["users"].pop(str(user_id), None)
            self._write_payload(payload)
