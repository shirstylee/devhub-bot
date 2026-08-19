import shutil
from pathlib import Path
from collections.abc import Iterable
from uuid import uuid4

from bot.config import TEMP_DIR


def make_temp_path(suffix: str) -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return TEMP_DIR / f"{uuid4().hex}{normalized_suffix}"


def make_temp_dir() -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_DIR / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_paths(*paths: str | Path | Iterable[str | Path] | None) -> None:
    for raw_path in paths:
        if raw_path is None:
            continue
        if isinstance(raw_path, Iterable) and not isinstance(raw_path, (str, Path)):
            cleanup_paths(*raw_path)
            continue
        path = Path(raw_path)
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir() and path.resolve().is_relative_to(TEMP_DIR.resolve()):
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
