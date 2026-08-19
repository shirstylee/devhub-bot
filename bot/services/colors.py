import random
from pathlib import Path

from PIL import Image


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("HEX должен быть в формате #FF5733.")
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError as exc:
        raise ValueError("HEX содержит недопустимые символы.") from exc
    return red, green, blue


def rgb_to_hex(rgb_color: str) -> str:
    parts = rgb_color.replace(",", " ").split()
    if len(parts) != 3:
        raise ValueError("RGB должен быть в формате: 255 87 51.")
    try:
        values = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("RGB должен содержать только числа.") from exc
    if any(value < 0 or value > 255 for value in values):
        raise ValueError("Каждое RGB-значение должно быть от 0 до 255.")
    return "#{:02X}{:02X}{:02X}".format(*values)


def random_color() -> tuple[str, tuple[int, int, int]]:
    rgb = tuple(random.randint(0, 255) for _ in range(3))
    return "#{:02X}{:02X}{:02X}".format(*rgb), rgb


def create_color_image(rgb: tuple[int, int, int], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 512), rgb).save(output_path, "PNG")
    return output_path
