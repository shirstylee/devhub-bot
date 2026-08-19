from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.services.render_fonts import ResolvedFontBundle, google_font_loader
from bot.services.render_models import (
    OutputFormat,
    RenderRequest,
    RenderResult,
    RenderSettings,
    RenderSource,
    WatermarkPosition,
)
from bot.services.render_validation import row_layout
from bot.utils.temp_files import make_temp_path


LOGGER = logging.getLogger(__name__)
MAX_DURATION = 10.0
MAX_OUTPUT_BYTES = 49 * 1024 * 1024
_RENDER_SEMAPHORE = asyncio.Semaphore(1)


class RenderError(RuntimeError):
    pass


class RenderTooLargeError(RenderError):
    pass


class FrameProvider(Protocol):
    duration: float
    is_static: bool

    def frame_at(self, seconds: float) -> Image.Image: ...

    def close(self) -> None: ...


class StaticFrameProvider:
    duration = 3.0
    is_static = True

    def __init__(self, path: Path) -> None:
        with Image.open(path) as source:
            self.image = ImageOps.exif_transpose(source).convert("RGBA")

    def frame_at(self, seconds: float) -> Image.Image:
        return self.image.copy()

    def close(self) -> None:
        self.image.close()


class LottieFrameProvider:
    is_static = False

    def __init__(self, path: Path) -> None:
        try:
            from rlottie_python import LottieAnimation
        except ImportError as exc:
            raise RenderError("Установите rlottie-python для TGS-рендера.") from exc
        self.animation = LottieAnimation.from_tgs(str(path))
        self.total_frames = max(1, int(self.animation.lottie_animation_get_totalframe()))
        self.framerate = max(1.0, float(self.animation.lottie_animation_get_framerate()))
        # total_frames / framerate is stable across rlottie builds. The native
        # duration helper has returned rounded or stale values for some TGS
        # files, which can clip the final motion cycle.
        self.duration = max(0.05, min(MAX_DURATION, self.total_frames / self.framerate))

    def frame_at(self, seconds: float) -> Image.Image:
        local_time = seconds % self.duration
        frame_number = min(
            self.total_frames - 1,
            int(local_time / self.duration * self.total_frames),
        )
        return self.animation.render_pillow_frame(frame_number).convert("RGBA")

    def close(self) -> None:
        close = getattr(self.animation, "close", None)
        if callable(close):
            close()


class AvFrameProvider:
    is_static = False

    def __init__(self, path: Path) -> None:
        try:
            import av
        except ImportError as exc:
            raise RenderError("Установите PyAV для GIF/WEBM/MP4.") from exc
        self.av = av
        self.path = path
        self.container = None
        self.stream = None
        self.iterator = None
        self.current_image: Image.Image | None = None
        self.current_time = 0.0
        self.next_frame = None
        self.next_time = 0.0
        self.decoded_index = 0
        self.duration = self._probe_duration()
        self._reset()

    def _probe_duration(self) -> float:
        with self.av.open(str(self.path)) as container:
            stream = next((item for item in container.streams if item.type == "video"), None)
            if stream is None:
                raise RenderError("В файле не найден видеопоток.")
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration:
                duration = float(container.duration / self.av.time_base)
            elif stream.frames and stream.average_rate:
                duration = float(stream.frames / stream.average_rate)
            else:
                duration = 3.0
        return max(0.05, min(MAX_DURATION, duration))

    def _reset(self) -> None:
        if self.container is not None:
            self.container.close()
        self.container = self.av.open(str(self.path))
        self.stream = next(item for item in self.container.streams if item.type == "video")
        self.iterator = iter(self._decoded_frames())
        self.current_image = None
        self.current_time = 0.0
        self.next_frame = None
        self.next_time = 0.0
        self.decoded_index = 0
        self._advance()

    def _decoded_frames(self):
        """Use libvpx for VP9 WEBM so Telegram sticker transparency is preserved."""
        if self.path.suffix.lower() == ".webm" and self.stream.codec_context.name == "vp9":
            try:
                decoder = self.av.CodecContext.create("libvpx-vp9", "r")
            except Exception as exc:
                LOGGER.warning("libvpx-vp9 decoder is unavailable: %s", exc)
                yield from self.container.decode(self.stream)
                return
            decoder.extradata = self.stream.codec_context.extradata
            for packet in self.container.demux(self.stream):
                yield from decoder.decode(packet)
            return
        yield from self.container.decode(self.stream)

    def _advance(self) -> None:
        try:
            frame = next(self.iterator)
        except StopIteration:
            self.next_frame = None
            return
        self.next_frame = frame
        if frame.time is not None:
            self.next_time = float(frame.time)
        elif frame.pts is not None and self.stream.time_base is not None:
            self.next_time = float(frame.pts * self.stream.time_base)
        else:
            rate = float(self.stream.average_rate or 30)
            self.next_time = self.decoded_index / max(1.0, rate)
        self.decoded_index += 1

    def frame_at(self, seconds: float) -> Image.Image:
        local_time = seconds % self.duration
        if local_time + 1e-6 < self.current_time:
            self._reset()
        while self.next_frame is not None and self.next_time <= local_time + 1e-6:
            if self.current_image is not None:
                self.current_image.close()
            array = self.next_frame.to_ndarray(format="rgba")
            self.current_image = Image.fromarray(array, "RGBA")
            self.current_time = self.next_time
            self._advance()
        if self.current_image is None and self.next_frame is not None:
            array = self.next_frame.to_ndarray(format="rgba")
            self.current_image = Image.fromarray(array, "RGBA")
        if self.current_image is None:
            raise RenderError("Не удалось декодировать кадр медиа.")
        return self.current_image.copy()

    def close(self) -> None:
        if self.current_image is not None:
            self.current_image.close()
        if self.container is not None:
            self.container.close()


class MediaRenderer:
    async def render(self, request: RenderRequest) -> RenderResult:
        if not request.sources:
            raise RenderError("Сначала отправьте эмодзи, стикер или медиа.")
        if len(request.sources) > 10:
            raise RenderError("В одном рендере можно использовать не больше 10 элементов.")
        if any(source.local_path is None for source in request.sources):
            raise RenderError("Не все исходники были загружены.")
        if request.background_source is not None and request.background_source.local_path is None:
            raise RenderError("Пользовательский фон не был загружен.")

        settings = request.settings
        duration_limit = MAX_DURATION
        if request.preview:
            width, height = _preview_size(settings.width, settings.height)
            settings = replace(
                settings,
                width=width,
                height=height,
                fps=30,
                output_format=OutputFormat.VIDEO,
            )
            duration_limit = 3.0

        font_bundle = None
        if settings.watermark_text:
            font_bundle = await google_font_loader.resolve_bundle(
                settings.watermark_font,
                settings.watermark_text,
            )

        prepared = replace(request, settings=settings)
        async with _RENDER_SEMAPHORE:
            try:
                return await asyncio.to_thread(
                    self._render_sync,
                    prepared,
                    font_bundle,
                    duration_limit,
                )
            except RenderError:
                raise
            except Exception as exc:
                LOGGER.exception("Media rendering failed")
                raise RenderError("Не удалось декодировать или закодировать это медиа.") from exc

    def _render_sync(
        self,
        request: RenderRequest,
        font_bundle: ResolvedFontBundle | None,
        duration_limit: float,
    ) -> RenderResult:
        output_format = request.settings.output_format
        # Telegram treats a silent H.264 MP4 sent through sendAnimation as a GIF.
        # Unlike a real GIF file, it keeps full colour and detail instead of being
        # reduced to a 256-colour palette. This also matches Telegram's own saved
        # animation format.
        output_path = make_temp_path(".mp4")
        bitrate = None

        self._encode(request, output_path, font_bundle, duration_limit, bitrate)
        if output_path.stat().st_size > MAX_OUTPUT_BYTES:
            duration = self._duration(
                request.sources,
                request.background_source,
                duration_limit,
                request.settings.fps,
            )
            bitrate = max(256_000, int(MAX_OUTPUT_BYTES * 8 * 0.84 / duration))
            self._encode(request, output_path, font_bundle, duration_limit, bitrate)

        if output_path.stat().st_size > MAX_OUTPUT_BYTES:
            output_path.unlink(missing_ok=True)
            raise RenderTooLargeError(
                "Результат больше 49 МБ. Выберите MP4 или уменьшите разрешение."
            )

        duration = self._duration(
            request.sources,
            request.background_source,
            duration_limit,
            request.settings.fps,
        )
        return RenderResult(
            path=output_path,
            output_format=output_format,
            width=request.settings.width,
            height=request.settings.height,
            duration=duration,
            fps=request.settings.fps,
            temporary_paths=[output_path],
        )

    def _encode(
        self,
        request: RenderRequest,
        output_path: Path,
        font_bundle: ResolvedFontBundle | None,
        duration_limit: float,
        bitrate: int | None,
    ) -> None:
        try:
            import av
        except ImportError as exc:
            raise RenderError("Установите PyAV для кодирования результата.") from exc

        output_path.unlink(missing_ok=True)
        providers = [_provider_for(source.local_path) for source in request.sources]
        background_provider = (
            _provider_for(request.background_source.local_path)
            if request.background_source is not None
            else None
        )
        # The foreground defines the clip. A static custom background must not
        # silently turn a 2.2 s sticker into a 3.0 s render (and an animated
        # background loops inside the same foreground timeline).
        duration = _timeline_duration(providers, duration_limit, request.settings.fps)
        frame_count = max(1, round(duration * request.settings.fps))
        duration = frame_count / request.settings.fps
        is_telegram_animation = request.settings.output_format == OutputFormat.GIF
        animated_timeline = any(not provider.is_static for provider in providers) or (
            background_provider is not None and not background_provider.is_static
        )
        loop_blend_frames = (
            min(max(2, round(request.settings.fps * 0.12)), frame_count // 6)
            if animated_timeline and frame_count >= 12
            else 0
        )
        first_canvas: Image.Image | None = None
        _report_progress(request, "frames")

        try:
            with av.open(
                str(output_path),
                "w",
                format="mp4",
                options={"movflags": "+faststart"},
            ) as container:
                stream = container.add_stream("libx264", rate=request.settings.fps)
                stream.pix_fmt = "yuv420p"
                if bitrate:
                    stream.options = {"preset": "slow" if is_telegram_animation else "medium"}
                    stream.bit_rate = bitrate
                else:
                    stream.options = {
                        "preset": "slow" if is_telegram_animation else "medium",
                        # Custom backgrounds can contain photos and fine text.
                        # CRF 12 avoids the blockiness users notice after saving
                        # the Telegram animation, while the 49 MB retry below
                        # still protects the Bot API upload limit.
                        "crf": "12" if is_telegram_animation else "18",
                    }
                stream.width = request.settings.width
                stream.height = request.settings.height
                stream.time_base = Fraction(1, request.settings.fps)

                for frame_index in range(frame_count):
                    seconds = frame_index * duration / frame_count
                    canvas = self._compose(
                        request.sources,
                        providers,
                        request.settings,
                        seconds,
                        font_bundle,
                        background_provider,
                    )
                    if frame_index == 0:
                        first_canvas = canvas.copy()
                    elif (
                        first_canvas is not None
                        and loop_blend_frames
                        and frame_index >= frame_count - loop_blend_frames
                    ):
                        blend_index = frame_index - (frame_count - loop_blend_frames) + 1
                        blended = Image.blend(
                            canvas,
                            first_canvas,
                            blend_index / loop_blend_frames,
                        )
                        canvas.close()
                        canvas = blended
                    if frame_index == 0:
                        _report_progress(request, "encoding")
                    rgb_canvas = canvas.convert("RGB")
                    video_frame = av.VideoFrame.from_image(rgb_canvas)
                    rgb_canvas.close()
                    video_frame.pts = frame_index
                    video_frame.time_base = Fraction(1, request.settings.fps)
                    for packet in stream.encode(video_frame):
                        container.mux(packet)
                    canvas.close()
                for packet in stream.encode():
                    container.mux(packet)
        finally:
            if first_canvas is not None:
                first_canvas.close()
            for provider in providers:
                provider.close()
            if background_provider is not None:
                background_provider.close()

    def _compose(
        self,
        sources: list[RenderSource],
        providers: list[FrameProvider],
        settings: RenderSettings,
        seconds: float,
        font_bundle: ResolvedFontBundle | None,
        background_provider: FrameProvider | None,
    ) -> Image.Image:
        background = settings.background_color.lstrip("#")
        canvas = Image.new(
            "RGBA",
            (settings.width, settings.height),
            tuple(int(background[index : index + 2], 16) for index in (0, 2, 4)) + (255,),
        )
        if background_provider is not None:
            background_frame = background_provider.frame_at(seconds)
            fitted_background = ImageOps.fit(
                background_frame,
                (settings.width, settings.height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            canvas.alpha_composite(fitted_background)
            fitted_background.close()
            background_frame.close()
        boxes = row_layout(len(sources), settings.width, settings.height, settings.emoji_size)
        for source, provider, (x, y, width, height) in zip(sources, providers, boxes, strict=True):
            frame = provider.frame_at(seconds)
            if source.recolorable and settings.emoji_color:
                frame = _recolor_frame(frame, settings.emoji_color)
            fitted = ImageOps.contain(frame, (width, height), Image.Resampling.LANCZOS)
            paste_x = x + (width - fitted.width) // 2
            paste_y = y + (height - fitted.height) // 2
            canvas.alpha_composite(fitted, (paste_x, paste_y))
            fitted.close()
            frame.close()
        if settings.watermark_text:
            _draw_watermark(canvas, settings, font_bundle)
        return canvas

    @staticmethod
    def _duration(
        sources: list[RenderSource],
        background_source: RenderSource | None,
        duration_limit: float,
        fps: int = 60,
    ) -> float:
        providers = [_provider_for(source.local_path) for source in sources]
        try:
            return _timeline_duration(providers, duration_limit, fps)
        finally:
            for provider in providers:
                provider.close()


def _timeline_duration(
    providers: list[FrameProvider],
    duration_limit: float,
    fps: int,
) -> float:
    raw_duration = min(duration_limit, max(provider.duration for provider in providers))
    frame_count = max(1, round(raw_duration * fps))
    return frame_count / fps


def _provider_for(path: Path | None) -> FrameProvider:
    if path is None:
        raise RenderError("Исходный файл не найден.")
    suffix = path.suffix.lower()
    if suffix == ".tgs":
        return LottieFrameProvider(path)
    if suffix in {".gif", ".webm", ".mp4", ".mov", ".mkv"}:
        return AvFrameProvider(path)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return StaticFrameProvider(path)
    raise RenderError(f"Формат {suffix or 'без расширения'} не поддерживается.")


def _recolor_frame(image: Image.Image, hex_color: str) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    target = np.array(
        [int(hex_color[index : index + 2], 16) for index in (1, 3, 5)],
        dtype=np.float32,
    )
    rgb = rgba[..., :3].astype(np.float32)
    luminance = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) / 255
    scale = (0.28 + luminance * 0.82)[..., None]
    recolored = np.clip(target * scale, 0, 255).astype(np.uint8)
    visible = rgba[..., 3] > 0
    rgba[..., :3][visible] = recolored[visible]
    return Image.fromarray(rgba, "RGBA")


def _draw_watermark(
    canvas: Image.Image,
    settings: RenderSettings,
    font_bundle: ResolvedFontBundle | None,
) -> None:
    text = settings.watermark_text or ""
    draw = ImageDraw.Draw(canvas)
    stroke_width = max(1, round(settings.height / 540))
    margin = max(8, round(min(settings.width, settings.height) * 0.03))
    font_size = max(8, round(settings.height * settings.watermark_size / 100))
    max_width = max(1, settings.width - 2 * margin)

    while True:
        runs = _watermark_runs(text, font_bundle, font_size)
        measured = [
            (
                run,
                font,
                float(draw.textlength(run, font=font)),
                draw.textbbox(
                    (0, 0),
                    run,
                    font=font,
                    stroke_width=stroke_width,
                    anchor="ls",
                ),
            )
            for run, font in runs
        ]
        text_width = sum(item[2] for item in measured)
        if text_width <= max_width or font_size <= 8:
            break
        next_size = max(8, int(font_size * max_width / text_width))
        font_size = next_size if next_size < font_size else font_size - 1

    top = min(item[3][1] for item in measured)
    bottom = max(item[3][3] for item in measured)
    positions = {
        WatermarkPosition.TOP_LEFT: (margin, margin - top),
        WatermarkPosition.TOP_RIGHT: (settings.width - text_width - margin, margin - top),
        WatermarkPosition.BOTTOM_LEFT: (margin, settings.height - bottom - margin),
        WatermarkPosition.BOTTOM_RIGHT: (
            settings.width - text_width - margin,
            settings.height - bottom - margin,
        ),
    }
    color = settings.watermark_color
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    stroke_fill = "#101216" if (red * 0.299 + green * 0.587 + blue * 0.114) > 150 else "#F4F6F8"
    cursor_x, baseline_y = positions[settings.watermark_position]
    for run, font, run_width, _ in measured:
        draw.text(
            (cursor_x, baseline_y),
            run,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
            anchor="ls",
        )
        cursor_x += run_width


def _watermark_runs(
    text: str,
    bundle: ResolvedFontBundle | None,
    font_size: int,
) -> list[tuple[str, ImageFont.ImageFont]]:
    if bundle is None:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default(size=font_size)
        return [(text, font)]

    primary = ImageFont.truetype(str(bundle.primary_path), font_size)
    fallback = (
        ImageFont.truetype(str(bundle.fallback_path), font_size)
        if bundle.fallback_path is not None
        else primary
    )
    runs: list[tuple[str, ImageFont.ImageFont]] = []
    current_text = ""
    current_font = None
    for character in text:
        font = fallback if bundle.use_fallback(character) else primary
        if current_font is not None and font is not current_font:
            runs.append((current_text, current_font))
            current_text = ""
        current_text += character
        current_font = font
    if current_text and current_font is not None:
        runs.append((current_text, current_font))
    return runs


def _preview_size(width: int, height: int) -> tuple[int, int]:
    factor = min(1.0, 640 / max(width, height))
    preview_width = max(2, int(width * factor) // 2 * 2)
    preview_height = max(2, int(height * factor) // 2 * 2)
    return preview_width, preview_height


def _report_progress(request: RenderRequest, stage: str) -> None:
    if request.progress is not None:
        request.progress(stage)


media_renderer = MediaRenderer()
