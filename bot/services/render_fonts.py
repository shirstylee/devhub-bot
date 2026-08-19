from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import aiohttp
from fontTools.ttLib import TTFont, TTLibError

from bot.config import BASE_DIR


LOGGER = logging.getLogger(__name__)
CACHE_DIR = BASE_DIR / "bot" / "cache" / "fonts"
BUNDLED_NOTO_PATH = BASE_DIR / "bot" / "assets" / "fonts" / "NotoSans.ttf"
MAX_FONT_BYTES = 5 * 1024 * 1024
_FAMILY_PATTERN = re.compile(r"^[\w .-]{1,80}$", re.UNICODE)
_FONT_URL_PATTERN = re.compile(r"url\((https://[^)]+)\)")


class FontLoadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedFontBundle:
    primary_path: Path
    fallback_path: Path | None
    primary_codepoints: frozenset[int]
    fallback_codepoints: frozenset[int] = frozenset()

    def use_fallback(self, character: str) -> bool:
        return not character.isspace() and ord(character) not in self.primary_codepoints


class GoogleFontLoader:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir

    async def resolve(self, family: str, text: str, *, allow_fallback: bool = True) -> Path | None:
        bundle = await self.resolve_bundle(family, text)
        if bundle.fallback_path is None:
            return bundle.primary_path
        if allow_fallback and all(
            character.isspace() or ord(character) in bundle.fallback_codepoints
            for character in text
        ):
            return bundle.fallback_path
        raise FontLoadError("Выбранный шрифт не содержит все символы watermark.")

    async def resolve_bundle(self, family: str, text: str) -> ResolvedFontBundle:
        family = family.strip()
        if not _FAMILY_PATTERN.fullmatch(family):
            raise FontLoadError("Название шрифта содержит недопустимые символы.")

        cache_key = hashlib.sha256(f"{family}\0{text}".encode("utf-8")).hexdigest()[:20]
        cached = self.cache_dir / f"{_safe_name(family)}-{cache_key}.ttf"
        if not cached.exists():
            try:
                await self._download(family, text, cached)
            except (aiohttp.ClientError, TimeoutError, OSError, TTLibError, FontLoadError) as exc:
                LOGGER.warning("Could not load Google Font %s: %s", family, exc)
                raise FontLoadError(
                    "Не удалось загрузить выбранный Google Font. Проверьте название и подключение."
                ) from exc

        primary_codepoints = _font_codepoints(cached)
        if not primary_codepoints:
            cached.unlink(missing_ok=True)
            raise FontLoadError("Загруженный файл шрифта повреждён.")
        missing = {
            ord(character)
            for character in text
            if not character.isspace() and ord(character) not in primary_codepoints
        }
        if not missing:
            return ResolvedFontBundle(cached, None, primary_codepoints)

        fallback_codepoints = _font_codepoints(BUNDLED_NOTO_PATH)
        unsupported = sorted(missing - fallback_codepoints)
        if unsupported:
            preview = ", ".join(f"U+{codepoint:04X}" for codepoint in unsupported[:5])
            raise FontLoadError(
                f"В Google Font и bundled Noto Sans нет нужных символов: {preview}."
            )
        return ResolvedFontBundle(
            cached,
            BUNDLED_NOTO_PATH,
            primary_codepoints,
            fallback_codepoints,
        )

    async def validate_family(self, family: str) -> None:
        await self.resolve_bundle(family, "Ag")

    async def _download(self, family: str, text: str, target: Path) -> Path:
        family_spec = quote_plus(family)
        text_spec = quote_plus(text)
        css_url = (
            "https://fonts.googleapis.com/css2"
            f"?family={family_spec}:wght@400&text={text_spec}&display=swap"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            )
        }
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(css_url) as response:
                if response.status != 200:
                    raise FontLoadError("Google Fonts не нашёл это семейство.")
                css = await response.text()

            urls = _FONT_URL_PATTERN.findall(css)
            if not urls:
                raise FontLoadError("Google Fonts не вернул файл шрифта.")
            font_url = urls[-1]
            parsed = urlparse(font_url)
            if parsed.scheme != "https" or parsed.hostname != "fonts.gstatic.com":
                raise FontLoadError("Получен небезопасный адрес файла шрифта.")

            async with session.get(font_url) as response:
                if response.status != 200:
                    raise FontLoadError("Не удалось загрузить файл шрифта.")
                length = int(response.headers.get("Content-Length", "0") or 0)
                if length > MAX_FONT_BYTES:
                    raise FontLoadError("Файл шрифта слишком большой.")
                data = await response.read()
                if len(data) > MAX_FONT_BYTES:
                    raise FontLoadError("Файл шрифта слишком большой.")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        font = TTFont(BytesIO(data))
        font.flavor = None
        temporary = target.with_suffix(".tmp")
        font.save(temporary)
        temporary.replace(target)
        return target


def _font_codepoints(path: Path) -> frozenset[int]:
    try:
        with TTFont(path, lazy=True) as font:
            cmap = font.getBestCmap() or {}
            return frozenset(cmap)
    except (OSError, TTLibError):
        return frozenset()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "font"


google_font_loader = GoogleFontLoader()
