from __future__ import annotations

import math
import re


MIN_SIDE = 256
MAX_SIDE = 1920
MAX_PIXELS = 1920 * 1080

_HEX_PATTERN = re.compile(r"^#?([0-9A-Fa-f]{6})$")
_SIZE_PATTERN = re.compile(r"^(\d{2,4})\s*[xх×]\s*(\d{2,4})$", re.IGNORECASE)
_RATIO_PATTERN = re.compile(r"^(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)$")


def normalize_hex(value: str) -> str:
    match = _HEX_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("Введите HEX в формате #RRGGBB, например #0A84FF.")
    return f"#{match.group(1).upper()}"


def parse_resolution(value: str) -> tuple[int, int]:
    normalized = value.strip()
    size_match = _SIZE_PATTERN.fullmatch(normalized)
    if size_match:
        width, height = (int(part) for part in size_match.groups())
        _validate_resolution(width, height)
        return width, height

    ratio_match = _RATIO_PATTERN.fullmatch(normalized)
    if not ratio_match:
        raise ValueError("Введите размер как 1920x530 или соотношение как 16:9.")

    left, right = (float(part.replace(",", ".")) for part in ratio_match.groups())
    if left <= 0 or right <= 0:
        raise ValueError("Стороны соотношения должны быть больше нуля.")

    ratio = left / right
    if math.isclose(ratio, 1.0, rel_tol=0.001):
        return 1080, 1080
    if math.isclose(ratio, 16 / 9, rel_tol=0.001):
        return 1920, 1080
    if math.isclose(ratio, 2.35, rel_tol=0.001):
        return 1920, 818

    if ratio >= 1:
        width = MAX_SIDE
        height = _even_round(width / ratio)
    else:
        height = MAX_SIDE
        width = _even_round(height * ratio)

    if width * height > MAX_PIXELS:
        factor = math.sqrt(MAX_PIXELS / (width * height))
        width = _even_floor(width * factor)
        height = _even_floor(height * factor)

    _validate_resolution(width, height)
    return width, height


def row_layout(
    count: int,
    canvas_width: int,
    canvas_height: int,
    size_percent: int,
) -> list[tuple[int, int, int, int]]:
    if count < 1 or count > 10:
        raise ValueError("В одном рендере поддерживается от 1 до 10 элементов.")

    gap = max(8, round(canvas_width * 0.012))
    max_by_height = round(canvas_height * size_percent / 100)
    max_by_width = (canvas_width - gap * (count - 1)) // count
    item_size = max(1, min(max_by_height, max_by_width))
    total_width = item_size * count + gap * (count - 1)
    start_x = (canvas_width - total_width) // 2
    y = (canvas_height - item_size) // 2
    return [
        (start_x + index * (item_size + gap), y, item_size, item_size)
        for index in range(count)
    ]


def frame_source_time(frame_index: int, fps: int, source_duration: float) -> float:
    if source_duration <= 0:
        return 0.0
    return (frame_index / fps) % source_duration


def _validate_resolution(width: int, height: int) -> None:
    if width % 2 or height % 2:
        raise ValueError("Ширина и высота должны быть чётными числами.")
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise ValueError("Каждая сторона должна быть от 256 до 1920 пикселей.")
    if width * height > MAX_PIXELS:
        raise ValueError("Разрешение не должно превышать 2 073 600 пикселей.")


def _even_round(value: float) -> int:
    return max(2, int(round(value / 2) * 2))


def _even_floor(value: float) -> int:
    return max(2, int(value) // 2 * 2)
