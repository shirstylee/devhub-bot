import gzip
import json
import colorsys
from fractions import Fraction
from pathlib import Path
from typing import Any
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.services.colors import hex_to_rgb
from bot.services.media_renderer import AvFrameProvider, RenderError


TGS_SUFFIX = ".tgs"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".webm", ".gif", ".mp4", ".mov", ".mkv"}
STATIC_STICKER_SIDE = 512
MAX_STATIC_STICKER_BYTES = 512 * 1024
MAX_ANIMATED_STICKER_BYTES = 64 * 1024
MAX_VIDEO_STICKER_BYTES = 256 * 1024
MAX_VIDEO_STICKER_DURATION = 3.0
MAX_VIDEO_STICKER_FPS = 30
EMOJI_FONT_PATHS = (
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
)


def recolor_asset(
    input_path: Path,
    output_path: Path,
    hex_color: str,
    adaptive: bool = False,
) -> Path:
    suffix = input_path.suffix.lower()
    if suffix == TGS_SUFFIX:
        return recolor_tgs(
            input_path,
            output_path.with_suffix(".tgs"),
            hex_color,
            adaptive=adaptive,
        )
    if suffix in IMAGE_SUFFIXES:
        return recolor_image(
            input_path,
            output_path.with_suffix(".webp"),
            hex_color,
            adaptive=adaptive,
        )
    if suffix in VIDEO_SUFFIXES:
        return recolor_video(
            input_path,
            output_path.with_suffix(".webm"),
            hex_color,
            adaptive=adaptive,
        )
    raise ValueError(
        "Поддерживаются TGS/WEBM, GIF/MP4 и статичные изображения PNG/JPG/WEBP."
    )


def recolor_tgs(
    input_path: Path,
    output_path: Path,
    hex_color: str,
    adaptive: bool = False,
) -> Path:
    target_rgb = tuple(channel / 255 for channel in hex_to_rgb(hex_color))
    target_hue, target_saturation, _ = colorsys.rgb_to_hsv(*target_rgb)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(input_path, "rt", encoding="utf-8") as file:
        animation = json.load(file)

    _replace_lottie_colors(
        animation,
        target_hue,
        target_saturation,
        target_rgb,
        adaptive,
    )

    with gzip.open(output_path, "wt", encoding="utf-8") as file:
        json.dump(animation, file, ensure_ascii=False, separators=(",", ":"))
    if output_path.stat().st_size > MAX_ANIMATED_STICKER_BYTES:
        output_path.unlink(missing_ok=True)
        raise ValueError("TGS-анимация превышает лимит Telegram 64 КБ.")
    return output_path


def recolor_image(
    input_path: Path,
    output_path: Path,
    hex_color: str,
    adaptive: bool = False,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(input_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    recolored = recolor_frame(image, hex_color, adaptive=adaptive)
    image.close()
    scale = STATIC_STICKER_SIDE / max(recolored.size)
    sticker_size = tuple(max(1, round(side * scale)) for side in recolored.size)
    image = recolored.resize(sticker_size, Image.Resampling.LANCZOS)
    recolored.close()

    try:
        image.save(output_path, "WEBP", lossless=True, method=6)
        if output_path.stat().st_size > MAX_STATIC_STICKER_BYTES:
            for quality in (92, 84, 76, 68, 60):
                image.save(output_path, "WEBP", quality=quality, method=6)
                if output_path.stat().st_size <= MAX_STATIC_STICKER_BYTES:
                    break
        if output_path.stat().st_size > MAX_STATIC_STICKER_BYTES:
            raise ValueError("Статичный стикер не удалось уменьшить до лимита Telegram 512 КБ.")
    finally:
        image.close()
    return output_path


def recolor_video(
    input_path: Path,
    output_path: Path,
    hex_color: str,
    adaptive: bool = False,
) -> Path:
    """Recolour animated media and encode it as a Telegram VP9 video sticker."""
    try:
        import av
    except ImportError as exc:
        raise ValueError("Для WEBM/GIF/MP4 требуется PyAV.") from exc

    try:
        probe = AvFrameProvider(input_path)
    except RenderError as exc:
        raise ValueError(str(exc)) from exc
    try:
        source_width = int(probe.stream.width or 512)
        source_height = int(probe.stream.height or 512)
        source_rate = float(probe.stream.average_rate or MAX_VIDEO_STICKER_FPS)
        fps = max(1, min(MAX_VIDEO_STICKER_FPS, round(source_rate)))
        duration = min(MAX_VIDEO_STICKER_DURATION, probe.duration)
    finally:
        probe.close()

    width, height = _video_sticker_size(source_width, source_height)
    frame_count = max(1, min(MAX_VIDEO_STICKER_FPS * 3, round(duration * fps)))
    duration = frame_count / fps
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Start visually lossless, then increase CRF only when Telegram's strict
    # 256 KB video-sticker limit requires it.
    for crf in (18, 24, 30, 36, 42, 48, 54):
        output_path.unlink(missing_ok=True)
        provider = AvFrameProvider(input_path)
        try:
            with av.open(str(output_path), "w", format="webm") as container:
                stream = container.add_stream("libvpx-vp9", rate=fps)
                stream.width = width
                stream.height = height
                stream.pix_fmt = "yuva420p"
                stream.time_base = Fraction(1, fps)
                stream.metadata["alpha_mode"] = "1"
                stream.options = {
                    "crf": str(crf),
                    "b": "0",
                    "auto-alt-ref": "0",
                    "deadline": "good",
                    "cpu-used": "2",
                }
                for frame_index in range(frame_count):
                    seconds = min(duration - 1 / fps, frame_index / fps)
                    source_frame = provider.frame_at(max(0.0, seconds))
                    recolored = recolor_frame(
                        source_frame,
                        hex_color,
                        adaptive=adaptive,
                    )
                    source_frame.close()
                    fitted = ImageOps.contain(
                        recolored,
                        (width, height),
                        Image.Resampling.LANCZOS,
                    )
                    recolored.close()
                    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                    canvas.alpha_composite(
                        fitted,
                        ((width - fitted.width) // 2, (height - fitted.height) // 2),
                    )
                    fitted.close()
                    video_frame = av.VideoFrame.from_ndarray(
                        np.asarray(canvas, dtype=np.uint8),
                        format="rgba",
                    )
                    canvas.close()
                    video_frame.pts = frame_index
                    video_frame.time_base = Fraction(1, fps)
                    for packet in stream.encode(video_frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise ValueError(f"Не удалось обработать анимацию: {exc}") from exc
        finally:
            provider.close()

        if output_path.stat().st_size <= MAX_VIDEO_STICKER_BYTES:
            return output_path

    output_path.unlink(missing_ok=True)
    raise ValueError("Анимацию не удалось уменьшить до лимита Telegram 256 КБ.")


def recolor_frame(
    image: Image.Image,
    hex_color: str,
    adaptive: bool = False,
) -> Image.Image:
    """Apply one hue while preserving original shading, outlines and highlights."""
    converted = image.convert("RGBA")
    rgba = np.asarray(converted, dtype=np.uint8).copy()
    converted.close()
    target = np.asarray(hex_to_rgb(hex_color), dtype=np.float32)
    rgb = rgba[..., :3].astype(np.float32)
    maximum = rgb.max(axis=-1)
    minimum = rgb.min(axis=-1)
    saturation = np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0,
    )
    luminance = (
        0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    ) / 255
    visible = rgba[..., 3] > 0
    if adaptive:
        mask = visible
        tinted = np.broadcast_to(target.astype(np.uint8), rgb.shape)
    else:
        black_outline = luminance < 0.035
        white_highlight = (luminance > 0.985) & (saturation < 0.08)
        mask = visible & ~black_outline & ~white_highlight
        scale = (0.45 + luminance * 0.85)[..., None]
        tinted = np.clip(target * scale, 0, 255).astype(np.uint8)
    rgba[..., :3][mask] = tinted[mask]
    return Image.fromarray(rgba, "RGBA")


def render_unicode_emoji(emoji: str, output_path: Path) -> Path:
    """Render one Unicode emoji to a transparent high-resolution PNG."""
    emoji = emoji.strip()
    if not is_single_emoji(emoji):
        raise ValueError("Отправьте ровно один обычный эмодзи.")
    font = _load_emoji_font()
    if font is None:
        raise ValueError("На сервере не найден шрифт для обычных эмодзи.")

    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    try:
        bounds = draw.textbbox((0, 0), emoji, font=font, embedded_color=True)
    except ValueError:
        bounds = draw.textbbox((0, 0), emoji, font=font)
    width = max(1, bounds[2] - bounds[0])
    height = max(1, bounds[3] - bounds[1])
    padding = 48
    glyph = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
    glyph_draw = ImageDraw.Draw(glyph)
    position = (padding - bounds[0], padding - bounds[1])
    try:
        glyph_draw.text(position, emoji, font=font, embedded_color=True)
    except ValueError:
        glyph_draw.text(position, emoji, font=font, fill="white")
    alpha_bounds = glyph.getchannel("A").getbbox()
    if alpha_bounds is None:
        glyph.close()
        raise ValueError("Этот обычный эмодзи не поддерживается шрифтом сервера.")
    cropped = glyph.crop(alpha_bounds)
    glyph.close()
    cropped.thumbnail((440, 440), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (STATIC_STICKER_SIDE, STATIC_STICKER_SIDE), (0, 0, 0, 0))
    canvas.alpha_composite(
        cropped,
        ((STATIC_STICKER_SIDE - cropped.width) // 2, (STATIC_STICKER_SIDE - cropped.height) // 2),
    )
    cropped.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path.with_suffix(".png"), "PNG", optimize=True)
    canvas.close()
    return output_path.with_suffix(".png")


def is_single_emoji(value: str) -> bool:
    value = value.strip()
    clusters = _grapheme_clusters(value)
    return len(clusters) == 1 and any(_is_emoji_codepoint(ord(char)) for char in value)


def _video_sticker_size(width: int, height: int) -> tuple[int, int]:
    scale = STATIC_STICKER_SIDE / max(1, width, height)
    result_width = max(2, round(width * scale))
    result_height = max(2, round(height * scale))
    result_width -= result_width % 2
    result_height -= result_height % 2
    return result_width, result_height


def _load_emoji_font() -> ImageFont.FreeTypeFont | None:
    for path in EMOJI_FONT_PATHS:
        for size in (384, 256, 160, 128, 109):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return None


def _grapheme_clusters(text: str) -> list[str]:
    clusters: list[str] = []
    current = ""
    regional_count = 0
    for character in text:
        codepoint = ord(character)
        is_regional = 0x1F1E6 <= codepoint <= 0x1F1FF
        joins_previous = bool(current) and (
            current.endswith("\u200d")
            or character == "\u200d"
            or codepoint in {0xFE0E, 0xFE0F, 0x20E3}
            or 0x1F3FB <= codepoint <= 0x1F3FF
            or bool(unicodedata.combining(character))
            or (is_regional and regional_count % 2 == 1)
        )
        if current and not joins_previous:
            clusters.append(current)
            current = ""
            regional_count = 0
        current += character
        regional_count = regional_count + 1 if is_regional else 0
    if current:
        clusters.append(current)
    return clusters


def _is_emoji_codepoint(codepoint: int) -> bool:
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2300 <= codepoint <= 0x27FF
        or 0x1F1E6 <= codepoint <= 0x1F1FF
        or codepoint in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x20E3, 0x2122, 0x2139, 0x3030, 0x303D}
    )


def _replace_lottie_colors(
    node: Any,
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> None:
    if isinstance(node, dict):
        if node.get("ty") in {"fl", "st"} and isinstance(node.get("c"), dict):
            _replace_color_value(
                node["c"],
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            )
        if node.get("ty") in {"gf", "gs"} and isinstance(node.get("g"), dict):
            _replace_gradient_value(
                node["g"],
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            )
        # Lottie colour-control effects store the value under `v`.
        if node.get("ty") == 2 and isinstance(node.get("v"), dict):
            _replace_color_value(
                node["v"],
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            )
        # Solid layers use a hexadecimal `sc` value instead of a colour property.
        if node.get("ty") == 1 and isinstance(node.get("sc"), str):
            node["sc"] = _shift_hex_color(
                node["sc"],
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            )
        # Text documents can contain direct fill/stroke arrays.
        for key in ("fc", "sc"):
            value = node.get(key)
            if isinstance(value, list) and len(value) >= 3:
                node[key] = _shift_color_array(
                    value,
                    target_hue,
                    target_saturation,
                    target_rgb,
                    adaptive,
                )
        for value in node.values():
            _replace_lottie_colors(
                value,
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            )
    elif isinstance(node, list):
        for item in node:
            _replace_lottie_colors(
                item,
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            )


def _replace_color_value(
    color_node: dict[str, Any],
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> None:
    value = color_node.get("k")
    if isinstance(value, list) and len(value) >= 3 and all(isinstance(item, (int, float)) for item in value[:3]):
        if not _is_recolorable(value, adaptive):
            return
        alpha = value[3] if len(value) > 3 else 1
        color_node["k"] = [
            *_shift_color(
                value,
                target_hue,
                target_saturation,
                target_rgb,
                adaptive,
            ),
            alpha,
        ]
    elif isinstance(value, list):
        for keyframe in value:
            if not isinstance(keyframe, dict):
                continue
            # Both endpoints are required. Recolouring only `s` makes the
            # original colour flash back at the end of a blink/morph keyframe.
            for endpoint in ("s", "e"):
                endpoint_value = keyframe.get(endpoint)
                if not isinstance(endpoint_value, list) or len(endpoint_value) < 3:
                    continue
                if not _is_recolorable(endpoint_value, adaptive):
                    continue
                alpha = endpoint_value[3] if len(endpoint_value) > 3 else 1
                keyframe[endpoint] = [
                    *_shift_color(
                        endpoint_value,
                        target_hue,
                        target_saturation,
                        target_rgb,
                        adaptive,
                    ),
                    alpha,
                ]


def _replace_gradient_value(
    gradient: dict[str, Any],
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> None:
    points = int(gradient.get("p", 0) or 0)
    color_node = gradient.get("k")
    if points <= 0 or not isinstance(color_node, dict):
        return
    value = color_node.get("k")
    if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
        _replace_gradient_array(
            value,
            points,
            target_hue,
            target_saturation,
            target_rgb,
            adaptive,
        )
        return
    if not isinstance(value, list):
        return
    for keyframe in value:
        if not isinstance(keyframe, dict):
            continue
        for endpoint in ("s", "e"):
            endpoint_value = keyframe.get(endpoint)
            if not isinstance(endpoint_value, list):
                continue
            target = (
                endpoint_value[0]
                if len(endpoint_value) == 1 and isinstance(endpoint_value[0], list)
                else endpoint_value
            )
            if isinstance(target, list):
                _replace_gradient_array(
                    target,
                    points,
                    target_hue,
                    target_saturation,
                    target_rgb,
                    adaptive,
                )


def _replace_gradient_array(
    values: list[Any],
    points: int,
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> None:
    for point in range(min(points, len(values) // 4)):
        start = point * 4 + 1
        color = values[start : start + 3]
        if len(color) < 3 or not all(isinstance(item, (int, float)) for item in color):
            continue
        if not _is_recolorable(color, adaptive):
            continue
        values[start : start + 3] = _shift_color(
            color,
            target_hue,
            target_saturation,
            target_rgb,
            adaptive,
        )


def _shift_color(
    value: list[Any],
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> list[float]:
    if adaptive:
        return [round(channel, 4) for channel in target_rgb]
    red, green, blue = (float(value[0]), float(value[1]), float(value[2]))
    _, original_saturation, original_brightness = colorsys.rgb_to_hsv(red, green, blue)
    saturation = max(0.0, min(1.0, target_saturation * (0.65 + original_saturation * 0.35)))
    shifted = colorsys.hsv_to_rgb(target_hue, saturation, original_brightness)
    return [round(channel, 4) for channel in shifted]


def _is_recolorable(value: list[Any], adaptive: bool = False) -> bool:
    red, green, blue = (float(value[0]), float(value[1]), float(value[2]))
    _, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
    alpha = float(value[3]) if len(value) > 3 and isinstance(value[3], (int, float)) else 1
    if alpha < 0.15:
        return False
    if adaptive:
        return True
    if brightness < 0.035:
        return False
    # A saturated yellow, cyan or blue often has HSV brightness == 1.0.
    # Preserve only genuinely white highlights, not every bright colour.
    if brightness > 0.985 and saturation < 0.08:
        return False
    return True


def _shift_color_array(
    value: list[Any],
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> list[Any]:
    if not _is_recolorable(value, adaptive):
        return value
    result = [
        *_shift_color(
            value,
            target_hue,
            target_saturation,
            target_rgb,
            adaptive,
        )
    ]
    result.extend(value[3:])
    return result


def _shift_hex_color(
    value: str,
    target_hue: float,
    target_saturation: float,
    target_rgb: tuple[float, float, float],
    adaptive: bool,
) -> str:
    raw = value.lstrip("#")
    if len(raw) not in {6, 8}:
        return value
    try:
        channels = [int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    except ValueError:
        return value
    if not _is_recolorable(channels, adaptive):
        return value
    shifted = _shift_color(
        channels,
        target_hue,
        target_saturation,
        target_rgb,
        adaptive,
    )
    rgb = "".join(f"{round(channel * 255):02X}" for channel in shifted)
    return f"#{rgb}{raw[6:].upper()}"
