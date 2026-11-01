from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import re
import shutil
from threading import RLock
from time import monotonic, time
from typing import Any, Callable
from uuid import uuid4

from bot.config import TEMP_DIR


TEMP_FILE_TTL = 10 * 60
_OWNED_NAME = re.compile(r"[0-9a-f]{32}(?:\.[^/\\]*)?\Z")
_PATH_FIELDS = ("file_input_path", "pdf_input_path", "recolor_input_path")
_current_scope: ContextVar[TempScope | None] = ContextVar("temporary_file_scope", default=None)


class TempScope:
    def __init__(self, manager: TemporaryFileManager) -> None:
        self.manager = manager
        self.protected: set[Path] = set()
        self.created: set[Path] = set()
        self.retained: set[Path] = set()
        self.closed = False

    def protect(self, path: str | Path) -> None:
        owner = self.manager.owner(path)
        if owner is not None and owner not in self.protected:
            self.manager._pins[owner] = self.manager._pins.get(owner, 0) + 1
            self.protected.add(owner)

    def retain(self, paths: Iterable[str | Path]) -> None:
        self.retained = {owner for path in paths if (owner := self.manager.owner(path)) is not None}

    def close(self) -> None:
        with self.manager._lock:
            if self.closed:
                return
            self.closed = True
            for owner in self.created - self.retained:
                self.manager.delete(owner)
            for owner in self.protected:
                count = self.manager._pins[owner] - 1
                if count:
                    self.manager._pins[owner] = count
                else:
                    del self.manager._pins[owner]
                    self.manager._touched[owner] = self.manager.clock()
                    self.manager._flush(owner)


class TemporaryFileManager:
    """Own UUID-named temporary files only; active requests hold deletion leases.

    Bookkeeping is in RAM. On restart, old unregistered UUID entries are found by
    mtime. Neither .gitkeep, arbitrary files, symlinks nor paths outside this root
    are deletion targets. A failed deletion remains pending for the next sweep.
    """

    def __init__(self, root: Path = TEMP_DIR, *, ttl: float = TEMP_FILE_TTL,
                 clock: Callable[[], float] = monotonic, wall_clock: Callable[[], float] = time) -> None:
        if ttl <= 0:
            raise ValueError("Temporary file TTL must be positive")
        self.root = root.resolve()
        self.ttl = ttl
        self.clock = clock
        self.wall_clock = wall_clock
        self._lock = RLock()
        self._pins: dict[Path, int] = {}
        self._touched: dict[Path, float] = {}
        self._pending: dict[Path, set[Path]] = {}
        self._deleted: set[Path] = set()

    def safe_path(self, value: str | Path) -> Path | None:
        try:
            path = Path(value).absolute()
            resolved = path.resolve()
            # Reject traversal, links and junctions, including intermediate ones.
            if resolved != path or not resolved.is_relative_to(self.root) or resolved == self.root:
                return None
            relative = resolved.relative_to(self.root)
            if not _OWNED_NAME.fullmatch(relative.parts[0]):
                return None
            return resolved
        except (OSError, RuntimeError, ValueError, TypeError):
            return None

    def owner(self, value: str | Path) -> Path | None:
        path = self.safe_path(value)
        return self.root / path.relative_to(self.root).parts[0] if path is not None else None

    def paths_in(self, data: dict[str, Any]) -> set[Path]:
        values = [data.get(key) for key in _PATH_FIELDS]
        images = data.get("pdf_images", [])
        if isinstance(images, (list, tuple)):
            values.extend(images)
        return {path for value in values if isinstance(value, (str, Path))
                and (path := self.safe_path(value)) is not None}

    def without_paths(self, data: dict[str, Any], owners: set[Path]) -> dict[str, Any]:
        cleaned = data.copy()
        for key in _PATH_FIELDS:
            value = cleaned.get(key)
            if isinstance(value, (str, Path)) and self.owner(value) in owners:
                cleaned.pop(key)
        images = cleaned.get("pdf_images")
        if isinstance(images, (list, tuple)):
            cleaned["pdf_images"] = [value for value in images
                                     if not isinstance(value, (str, Path)) or self.owner(value) not in owners]
        return cleaned

    def _register(self, path: Path) -> None:
        with self._lock:
            self._touched[path] = self.clock()
            scope = _current_scope.get()
            if scope is not None and scope.manager is self and not scope.closed:
                scope.protect(path)
                scope.created.add(path)

    def make_path(self, suffix: str) -> Path:
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        if (suffix in {".", ".."} or len(suffix) > 64
                or any(char in suffix for char in '/\\\x00<>:"|?*\r\n')):
            raise ValueError("Invalid temporary file suffix")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{uuid4().hex}{suffix}"
        self._register(path)
        return path

    def make_dir(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / uuid4().hex
        self._register(path)
        path.mkdir()
        return path

    @contextmanager
    def scope(self, paths: Iterable[str | Path] = (), *, parent: TempScope | None = None) -> Iterator[TempScope]:
        scope = TempScope(self)
        with self._lock:
            if parent is not None and parent.closed:
                raise RuntimeError("Request already finished before worker startup")
            for path in paths:
                scope.protect(path)
        token = _current_scope.set(scope)
        try:
            yield scope
        finally:
            _current_scope.reset(token)
            scope.close()

    def _remove(self, path: Path) -> bool:
        if self.safe_path(path) is None:
            return False
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def _flush(self, owner: Path) -> None:
        if self._pins.get(owner):
            return
        pending = self._pending.get(owner, set())
        for path in sorted(tuple(pending), key=lambda value: len(value.parts), reverse=True):
            if self._remove(path):
                pending.discard(path)
        if not pending:
            self._pending.pop(owner, None)
        if not owner.exists() and owner not in self._pending:
            self._touched.pop(owner, None)
            self._deleted.add(owner)

    def delete(self, *paths: str | Path | Iterable[str | Path] | None) -> None:
        for value in paths:
            if value is None:
                continue
            if isinstance(value, Iterable) and not isinstance(value, (str, Path)):
                self.delete(*value)
                continue
            path = self.safe_path(value)
            if path is None:
                continue
            owner = self.root / path.relative_to(self.root).parts[0]
            with self._lock:
                self._pending.setdefault(owner, set()).add(path)
                self._flush(owner)

    def sweep(self) -> set[Path]:
        expired: set[Path] = set()
        with self._lock:
            expired.update(self._deleted)
            self._deleted.clear()
            for owner in tuple(self._pending):
                self._flush(owner)
            candidates = set(self._touched)
            try:
                candidates.update(self.root.iterdir())
            except FileNotFoundError:
                pass
            for owner in candidates:
                if self.safe_path(owner) is None or self._pins.get(owner):
                    continue
                touched = self._touched.get(owner)
                try:
                    age = (self.clock() - touched if touched is not None
                           else self.wall_clock() - owner.stat().st_mtime)
                except FileNotFoundError:
                    age = self.ttl
                if age < self.ttl:
                    continue
                if self._remove(owner):
                    expired.add(owner)
                    self._touched.pop(owner, None)
                    self._pending.pop(owner, None)
                else:
                    self._pending.setdefault(owner, set()).add(owner)
            expired.update(self._deleted)
            self._deleted.clear()
        return expired

    @property
    def pending_count(self) -> int:
        with self._lock:
            return sum(len(paths) for owner, paths in self._pending.items() if not self._pins.get(owner))


temporary_files = TemporaryFileManager()


def make_temp_path(suffix: str) -> Path:
    return temporary_files.make_path(suffix)


def make_temp_dir() -> Path:
    return temporary_files.make_dir()


def cleanup_paths(*paths: str | Path | Iterable[str | Path] | None) -> None:
    temporary_files.delete(*paths)


def run_temp_worker(callback: Callable, *args, input_paths: Iterable[str | Path] = (), **kwargs):
    """Keep leases inside the thread even if its awaiting coroutine is cancelled.

    asyncio.to_thread cannot stop a native encoder. Its input/output files must
    remain protected until the actual worker returns, not just until cancellation.
    """
    outer = _current_scope.get()
    manager = outer.manager if outer is not None else temporary_files
    with manager.scope(input_paths, parent=outer) as scope:
        result = callback(*args, **kwargs)
        with manager._lock:
            if outer is None or not outer.closed:
                if outer is not None:
                    for path in scope.created:
                        outer.protect(path)
                        outer.created.add(path)
                scope.retain(scope.created)
        return result
