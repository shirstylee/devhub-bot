from __future__ import annotations

from typing import Literal


Language = Literal["ru", "en"]
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"ru", "en"})
DEFAULT_LANGUAGE: Language = "ru"


def normalize_language(value: object, default: Language = DEFAULT_LANGUAGE) -> Language:
    return value if value in SUPPORTED_LANGUAGES else default  # type: ignore[return-value]


def tr(language: str, russian: str, english: str) -> str:
    """Return a short interface translation without hiding copy in a global catalog."""
    return english if language == "en" else russian
