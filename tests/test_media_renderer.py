import gzip
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import av
import numpy as np
from PIL import Image, ImageDraw

from bot.services.media_renderer import (
    AvFrameProvider,
    LottieFrameProvider,
    _draw_watermark,
    _watermark_runs,
    media_renderer,
)
from bot.handlers.emoji_renderer import _send_result
from bot.services.render_fonts import BUNDLED_NOTO_PATH, ResolvedFontBundle
from bot.services.render_models import (
    OutputFormat,
    RenderRequest,
    RenderSettings,
    RenderSource,
    SourceKind,
    WatermarkPosition,
)
from bot.utils.temp_files import cleanup_paths


class MediaRendererTests(unittest.IsolatedAsyncioTestCase):
    async def test_gif_mode_mp4_is_sent_as_telegram_animation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "telegram-animation.mp4"
            output.touch()
            bot = SimpleNamespace(
                send_animation=AsyncMock(),
                send_video=AsyncMock(),
                send_document=AsyncMock(),
            )
            anchor = SimpleNamespace(bot=bot, chat=SimpleNamespace(id=42))
            result = SimpleNamespace(
                path=output,
                output_format=OutputFormat.GIF,
                width=1920,
                height=530,
                fps=60,
                duration=3.0,
            )

            await _send_result(anchor, result, preview=False)

            bot.send_animation.assert_awaited_once()
            bot.send_video.assert_not_awaited()
            bot.send_document.assert_not_awaited()
            sent_file = bot.send_animation.await_args.args[1]
            self.assertEqual(Path(sent_file.path).suffix, ".mp4")

    async def test_result_replaces_renderer_panel_and_keeps_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "telegram-animation.mp4"
            output.touch()
            edited = SimpleNamespace(chat=SimpleNamespace(id=42), message_id=77)
            bot = SimpleNamespace(edit_message_media=AsyncMock(return_value=edited))
            anchor = SimpleNamespace(bot=bot, chat=SimpleNamespace(id=42))
            state = SimpleNamespace(
                get_data=AsyncMock(
                    return_value={
                        "renderer_panel_chat_id": 42,
                        "renderer_panel_message_id": 77,
                    }
                ),
                update_data=AsyncMock(),
            )
            result = SimpleNamespace(
                path=output,
                output_format=OutputFormat.GIF,
                width=1920,
                height=530,
                fps=60,
                duration=2.2,
            )

            await _send_result(anchor, result, preview=False, state=state)

            bot.edit_message_media.assert_awaited_once()
            kwargs = bot.edit_message_media.await_args.kwargs
            self.assertEqual((kwargs["chat_id"], kwargs["message_id"]), (42, 77))
            callbacks = [
                button.callback_data
                for row in kwargs["reply_markup"].inline_keyboard
                for button in row
            ]
            self.assertEqual(
                callbacks,
                ["render:again", "render:settings", "render:history", "menu:back"],
            )

    async def test_sixty_fps_telegram_gif_is_high_quality_mp4_animation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "source.png"
            Image.new("RGBA", (128, 128), (80, 200, 120, 255)).save(input_path)
            source = RenderSource(
                SourceKind.STICKER,
                "local",
                ".png",
                local_path=input_path,
            )
            settings = RenderSettings(
                width=256,
                height=256,
                fps=60,
                output_format=OutputFormat.GIF,
            )
            result = await media_renderer.render(RenderRequest([source], settings))
            try:
                self.assertLess(result.path.stat().st_size, 1024 * 1024)
                self.assertEqual(result.path.suffix, ".mp4")
                with av.open(str(result.path)) as container:
                    stream = container.streams.video[0]
                    frames = list(container.decode(stream))
                    self.assertEqual(stream.codec_context.name, "h264")
                    self.assertEqual(stream.codec_context.format.name, "yuv420p")
                    self.assertEqual(len(frames), 180)
                    self.assertAlmostEqual(float(stream.duration * stream.time_base), 3.0, places=1)
            finally:
                cleanup_paths(result.path)

    def test_watermark_uses_all_four_corners_and_fallback_runs(self) -> None:
        bundle = ResolvedFontBundle(
            primary_path=BUNDLED_NOTO_PATH,
            fallback_path=BUNDLED_NOTO_PATH,
            primary_codepoints=frozenset({ord("D")}),
            fallback_codepoints=frozenset({ord("т")}),
        )
        runs = _watermark_runs("Dт", bundle, 20)
        self.assertEqual([text for text, _ in runs], ["D", "т"])

        expected_quadrants = {
            WatermarkPosition.TOP_LEFT: (False, False),
            WatermarkPosition.TOP_RIGHT: (True, False),
            WatermarkPosition.BOTTOM_LEFT: (False, True),
            WatermarkPosition.BOTTOM_RIGHT: (True, True),
        }
        full_bundle = ResolvedFontBundle(
            primary_path=BUNDLED_NOTO_PATH,
            fallback_path=None,
            primary_codepoints=frozenset({ord("W")}),
        )
        for position, (right, bottom) in expected_quadrants.items():
            canvas = Image.new("RGBA", (400, 200), "#000000")
            settings = RenderSettings(
                width=400,
                height=200,
                watermark_text="W",
                watermark_position=position,
            )
            _draw_watermark(canvas, settings, full_bundle)
            pixels = np.asarray(canvas)[..., :3]
            y_values, x_values = np.where(np.any(pixels != 0, axis=2))
            self.assertEqual(float(x_values.mean()) > 200, right)
            self.assertEqual(float(y_values.mean()) > 100, bottom)

        small = Image.new("RGBA", (600, 300), "#000000")
        large = Image.new("RGBA", (600, 300), "#000000")
        _draw_watermark(
            small,
            RenderSettings(width=600, height=300, watermark_text="W", watermark_size=3),
            full_bundle,
        )
        _draw_watermark(
            large,
            RenderSettings(width=600, height=300, watermark_text="W", watermark_size=10),
            full_bundle,
        )
        small_pixels = np.count_nonzero(np.any(np.asarray(small)[..., :3] != 0, axis=2))
        large_pixels = np.count_nonzero(np.any(np.asarray(large)[..., :3] != 0, axis=2))
        self.assertGreater(large_pixels, small_pixels * 2)

    def test_tgs_is_decoded_with_rlottie(self) -> None:
        payload = {
            "v": "5.7.4",
            "fr": 30,
            "ip": 0,
            "op": 30,
            "w": 128,
            "h": 128,
            "nm": "shape",
            "ddd": 0,
            "assets": [],
            "layers": [
                {
                    "ddd": 0,
                    "ind": 1,
                    "ty": 4,
                    "nm": "circle",
                    "sr": 1,
                    "ks": {
                        "o": {"a": 0, "k": 100},
                        "r": {"a": 0, "k": 0},
                        "p": {
                            "a": 1,
                            "k": [
                                {
                                    "i": {"x": 0.833, "y": 0.833},
                                    "o": {"x": 0.167, "y": 0.167},
                                    "t": 0,
                                    "s": [32, 64, 0],
                                    "e": [96, 64, 0],
                                    "to": [10.667, 0, 0],
                                    "ti": [-10.667, 0, 0],
                                },
                                {"t": 29, "s": [96, 64, 0]},
                            ],
                        },
                        "a": {"a": 0, "k": [0, 0, 0]},
                        "s": {"a": 0, "k": [100, 100, 100]},
                    },
                    "ao": 0,
                    "shapes": [
                        {"ty": "el", "p": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [80, 80]}},
                        {"ty": "fl", "c": {"a": 0, "k": [0.2, 0.8, 0.4, 1]}, "o": {"a": 0, "k": 100}, "r": 1},
                    ],
                    "ip": 0,
                    "op": 30,
                    "st": 0,
                    "bm": 0,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "animated.tgs"
            with gzip.open(input_path, "wb") as compressed:
                compressed.write(json.dumps(payload).encode("utf-8"))
            provider = LottieFrameProvider(input_path)
            try:
                frame = provider.frame_at(0)
                self.assertEqual(frame.size, (128, 128))
                self.assertIsNotNone(frame.getbbox())
                self.assertAlmostEqual(provider.duration, 1.0, places=1)
                middle = provider.frame_at(0.5)
                self.assertGreater(
                    np.mean(
                        np.abs(
                            np.asarray(frame).astype(int) - np.asarray(middle).astype(int)
                        )
                    ),
                    1,
                )
                middle.close()
                frame.close()
            finally:
                provider.close()

    def test_transparent_webm_keeps_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "transparent.webm"
            with av.open(str(input_path), "w", format="webm") as container:
                stream = container.add_stream("libvpx-vp9", rate=30)
                stream.width = 128
                stream.height = 128
                stream.pix_fmt = "yuva420p"
                stream.metadata["alpha_mode"] = "1"
                stream.options = {"lossless": "1", "auto-alt-ref": "0"}
                for offset in range(3):
                    pixels = np.zeros((128, 128, 4), dtype=np.uint8)
                    pixels[24:104, 24 + offset : 104 + offset, :3] = (20, 180, 250)
                    pixels[24:104, 24 + offset : 104 + offset, 3] = 255
                    frame = av.VideoFrame.from_ndarray(pixels, format="rgba")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)

            provider = AvFrameProvider(input_path)
            try:
                frame = provider.frame_at(0)
                alpha_min, alpha_max = frame.getchannel("A").getextrema()
                self.assertEqual((alpha_min, alpha_max), (0, 255))
            finally:
                provider.close()

    def test_webm_provider_keeps_frame_timing_and_motion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "moving.webm"
            with av.open(str(input_path), "w", format="webm") as container:
                stream = container.add_stream("libvpx-vp9", rate=10)
                stream.width = 128
                stream.height = 128
                stream.pix_fmt = "yuva420p"
                stream.metadata["alpha_mode"] = "1"
                stream.options = {"lossless": "1", "auto-alt-ref": "0"}
                for offset in range(10):
                    pixels = np.zeros((128, 128, 4), dtype=np.uint8)
                    left = 8 + offset * 8
                    pixels[40:80, left : left + 24, :3] = (30, 210, 90)
                    pixels[40:80, left : left + 24, 3] = 255
                    frame = av.VideoFrame.from_ndarray(pixels, format="rgba")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)

            provider = AvFrameProvider(input_path)
            try:
                first = np.asarray(provider.frame_at(0))
                middle = np.asarray(provider.frame_at(0.5))
                self.assertGreater(np.mean(np.abs(first.astype(int) - middle.astype(int))), 1)
            finally:
                provider.close()

    async def test_static_source_to_mp4_and_gif(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "source.png"
            background_path = Path(directory) / "background.png"
            image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((12, 12, 116, 116), fill=(220, 80, 60, 255))
            image.save(input_path)
            Image.new("RGB", (320, 180), (24, 88, 160)).save(background_path)
            source = RenderSource(
                SourceKind.STICKER,
                "local",
                ".png",
                recolorable=True,
                local_path=input_path,
            )
            background = RenderSource(
                SourceKind.USER_MEDIA,
                "background",
                ".png",
                recolorable=False,
                local_path=background_path,
            )
            settings = RenderSettings(
                width=256,
                height=256,
                fps=2,
                output_format=OutputFormat.VIDEO,
                emoji_color="#0A84FF",
            )
            stages: list[str] = []
            mp4 = await media_renderer.render(
                RenderRequest(
                    [source],
                    settings,
                    background_source=background,
                    progress=stages.append,
                )
            )
            self.assertTrue(mp4.path.exists())
            self.assertGreater(mp4.path.stat().st_size, 0)
            self.assertEqual((mp4.width, mp4.height, mp4.fps), (256, 256, 2))
            with av.open(str(mp4.path)) as container:
                stream = container.streams.video[0]
                self.assertEqual((stream.width, stream.height), (256, 256))
                self.assertEqual(float(stream.average_rate), 2.0)
                frame = next(container.decode(stream)).to_image().convert("RGB")
                corner = frame.getpixel((8, 8))
                self.assertLess(abs(corner[0] - 24), 12)
                self.assertLess(abs(corner[1] - 88), 12)
                self.assertLess(abs(corner[2] - 160), 12)
            self.assertEqual(stages[:2], ["frames", "encoding"])

            settings.output_format = OutputFormat.GIF
            gif = await media_renderer.render(
                RenderRequest([source], settings, background_source=background)
            )
            self.assertTrue(gif.path.exists())
            self.assertGreater(gif.path.stat().st_size, 0)
            cleanup_paths(mp4.path, gif.path)

    async def test_static_background_does_not_change_foreground_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            foreground_path = Path(directory) / "foreground.mp4"
            background_path = Path(directory) / "background.png"
            with av.open(str(foreground_path), "w", format="mp4") as container:
                stream = container.add_stream("libx264", rate=10)
                stream.width = 128
                stream.height = 128
                stream.pix_fmt = "yuv420p"
                for index in range(22):
                    pixels = np.zeros((128, 128, 3), dtype=np.uint8)
                    pixels[:, :, index % 3] = 80 + index
                    frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            Image.new("RGB", (320, 180), (80, 40, 20)).save(background_path)
            source = RenderSource(
                SourceKind.STICKER,
                "foreground",
                ".mp4",
                local_path=foreground_path,
            )
            background = RenderSource(
                SourceKind.USER_MEDIA,
                "background",
                ".png",
                local_path=background_path,
            )
            settings = RenderSettings(width=256, height=256, fps=10, output_format=OutputFormat.VIDEO)

            without_background = await media_renderer.render(RenderRequest([source], settings))
            with_background = await media_renderer.render(
                RenderRequest([source], settings, background_source=background)
            )
            try:
                self.assertEqual(without_background.duration, with_background.duration)
                self.assertAlmostEqual(with_background.duration, 2.2, places=1)
                with av.open(str(with_background.path)) as container:
                    frames = list(container.decode(container.streams.video[0]))
                self.assertEqual(len(frames), 22)
                first = frames[0].to_ndarray(format="rgb24")
                middle = frames[len(frames) // 2].to_ndarray(format="rgb24")
                self.assertGreater(np.mean(np.abs(first.astype(int) - middle.astype(int))), 1)
            finally:
                cleanup_paths(without_background.path, with_background.path)


if __name__ == "__main__":
    unittest.main()
