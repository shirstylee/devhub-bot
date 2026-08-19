import gzip
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import av
import numpy as np
from PIL import Image, ImageDraw

from bot.handlers.recolor import (
    RecolorSource,
    _recolor_and_send,
    _resolve_recolor_source,
    _show_recolor_palette,
    _source_from_sticker,
)
from bot.services.media_renderer import AvFrameProvider
from bot.services.recolor import (
    MAX_STATIC_STICKER_BYTES,
    MAX_VIDEO_STICKER_BYTES,
    recolor_asset,
    recolor_frame,
    recolor_tgs,
    recolor_video,
    render_unicode_emoji,
)


class RecolorStickerTests(unittest.TestCase):
    def test_tgs_recolors_both_keyframe_ends_gradients_and_neutral_details(self) -> None:
        animation = {
            "layers": [
                {
                    "ty": 4,
                    "shapes": [
                        {
                            "ty": "fl",
                            "c": {
                                "a": 1,
                                "k": [
                                    {"t": 0, "s": [0.6, 0.6, 0.6, 1], "e": [0.8, 0.3, 0.1, 1]}
                                ],
                            },
                        },
                        {
                            "ty": "gf",
                            "g": {"p": 2, "k": {"a": 0, "k": [0, 0.7, 0.4, 0.2, 1, 0.5, 0.5, 0.5]}},
                        },
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "blink.tgs"
            output = Path(directory) / "blink-blue.tgs"
            with gzip.open(source, "wt", encoding="utf-8") as file:
                json.dump(animation, file)

            recolor_tgs(source, output, "#0A84FF")

            with gzip.open(output, "rt", encoding="utf-8") as file:
                recolored = json.load(file)
            shapes = recolored["layers"][0]["shapes"]
            keyframe = shapes[0]["c"]["k"][0]
            self.assertGreater(keyframe["s"][2], keyframe["s"][0])
            self.assertGreater(keyframe["e"][2], keyframe["e"][0])
            gradient = shapes[1]["g"]["k"]["k"]
            self.assertGreater(gradient[3], gradient[1])
            self.assertGreater(gradient[7], gradient[5])

    def test_tgs_recolors_bright_yellow_and_cyan_but_keeps_white(self) -> None:
        animation = {
            "layers": [
                {
                    "ty": 4,
                    "shapes": [
                        {"ty": "fl", "c": {"a": 0, "k": [1, 1, 0, 1]}},
                        {"ty": "fl", "c": {"a": 0, "k": [0, 0.8, 1, 1]}},
                        {"ty": "fl", "c": {"a": 0, "k": [1, 1, 1, 1]}},
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bright.tgs"
            output = Path(directory) / "bright-green.tgs"
            with gzip.open(source, "wt", encoding="utf-8") as file:
                json.dump(animation, file)

            recolor_tgs(source, output, "#20D050")

            with gzip.open(output, "rt", encoding="utf-8") as file:
                colors = [shape["c"]["k"] for shape in json.load(file)["layers"][0]["shapes"]]
            self.assertGreater(colors[0][1], colors[0][0])
            self.assertGreater(colors[1][1], colors[1][2])
            self.assertEqual(colors[2], [1, 1, 1, 1])

    def test_adaptive_tgs_recolors_black_placeholder_shapes(self) -> None:
        animation = {
            "layers": [
                {
                    "ty": 4,
                    "shapes": [
                        {"ty": "fl", "c": {"a": 0, "k": [0, 0, 0, 1]}},
                        {"ty": "st", "c": {"a": 0, "k": [1, 1, 1, 0.5]}},
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "adaptive.tgs"
            output = Path(directory) / "adaptive-blue.tgs"
            with gzip.open(source, "wt", encoding="utf-8") as file:
                json.dump(animation, file)

            recolor_tgs(source, output, "#0A84FF", adaptive=True)

            with gzip.open(output, "rt", encoding="utf-8") as file:
                colors = [shape["c"]["k"] for shape in json.load(file)["layers"][0]["shapes"]]
            expected = [round(channel / 255, 4) for channel in (10, 132, 255)]
            self.assertEqual(colors[0], [*expected, 1])
            self.assertEqual(colors[1], [*expected, 0.5])

    def test_adaptive_raster_recolors_opaque_black_but_keeps_alpha(self) -> None:
        image = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
        image.putpixel((0, 0), (0, 0, 0, 255))

        recolored = recolor_frame(image, "#20D050", adaptive=True)

        self.assertEqual(recolored.getpixel((0, 0)), (32, 208, 80, 255))
        self.assertEqual(recolored.getpixel((1, 0)), (0, 0, 0, 0))
        image.close()
        recolored.close()

    def test_static_result_is_telegram_webp_sticker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "result.png"
            image = Image.new("RGBA", (900, 600), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((80, 40, 820, 560), fill=(220, 80, 80, 255))
            image.save(source)

            result = recolor_asset(source, output, "#0A84FF")

            self.assertEqual(result.suffix, ".webp")
            self.assertLessEqual(result.stat().st_size, MAX_STATIC_STICKER_BYTES)
            with Image.open(result) as sticker:
                self.assertEqual(sticker.format, "WEBP")
                self.assertEqual(max(sticker.size), 512)
                self.assertEqual(sticker.mode, "RGBA")

    def test_unicode_emoji_can_be_rendered_and_recolored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = render_unicode_emoji("😀", Path(directory) / "emoji.png")
            result = recolor_asset(source, Path(directory) / "result.webp", "#20D050")

            self.assertTrue(source.exists())
            self.assertTrue(result.exists())
            with Image.open(result) as sticker:
                self.assertEqual(sticker.mode, "RGBA")
                self.assertIsNotNone(sticker.getchannel("A").getbbox())

    def test_transparent_webm_is_recolored_as_telegram_video_sticker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.webm"
            output = Path(directory) / "result.webm"
            with av.open(str(source), "w", format="webm") as container:
                stream = container.add_stream("libvpx-vp9", rate=10)
                stream.width = 128
                stream.height = 128
                stream.pix_fmt = "yuva420p"
                stream.metadata["alpha_mode"] = "1"
                stream.options = {"lossless": "1", "auto-alt-ref": "0"}
                for offset in range(10):
                    pixels = np.zeros((128, 128, 4), dtype=np.uint8)
                    left = 16 + offset * 4
                    pixels[40:88, left : left + 40, :3] = (220, 60, 40)
                    pixels[40:88, left : left + 40, 3] = 255
                    frame = av.VideoFrame.from_ndarray(pixels, format="rgba")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)

            result = recolor_video(source, output, "#0A84FF")

            self.assertEqual(result.suffix, ".webm")
            self.assertLessEqual(result.stat().st_size, MAX_VIDEO_STICKER_BYTES)
            provider = AvFrameProvider(result)
            try:
                first = np.asarray(provider.frame_at(0))
                middle = np.asarray(provider.frame_at(0.5))
                self.assertEqual(provider.current_image.getchannel("A").getextrema(), (0, 255))
                visible = middle[..., 3] > 0
                self.assertGreater(float(middle[..., 2][visible].mean()), float(middle[..., 0][visible].mean()))
                self.assertGreater(np.mean(np.abs(first.astype(int) - middle.astype(int))), 1)
            finally:
                provider.close()


class RecolorHandlerTests(unittest.IsolatedAsyncioTestCase):
    def test_sticker_variants_keep_their_native_animation_format(self) -> None:
        variants = (
            (False, False, ".webp"),
            (False, True, ".tgs"),
            (True, False, ".webm"),
        )
        for is_video, is_animated, expected_suffix in variants:
            sticker = SimpleNamespace(
                is_video=is_video,
                is_animated=is_animated,
                emoji="🙂",
                file_id="file-id",
                file_size=1024,
            )
            self.assertEqual(_source_from_sticker(sticker, "🙂").suffix, expected_suffix)

    async def test_premium_emoji_entity_is_resolved_to_telegram_sticker(self) -> None:
        sticker = SimpleNamespace(
            is_video=True,
            is_animated=False,
            emoji="🙂",
            file_id="premium-file-id",
            file_size=1024,
            needs_repainting=True,
        )
        bot = SimpleNamespace(
            get_custom_emoji_stickers=AsyncMock(return_value=[sticker]),
        )
        entity = SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-id")
        message = SimpleNamespace(
            text="🙂",
            entities=[entity],
            caption_entities=None,
            sticker=None,
            photo=None,
            animation=None,
            video=None,
            document=None,
            bot=bot,
        )

        source = await _resolve_recolor_source(message)

        self.assertEqual(
            source,
            RecolorSource(
                ".webm",
                "🙂",
                file_id="premium-file-id",
                adaptive=True,
            ),
        )
        bot.get_custom_emoji_stickers.assert_awaited_once_with(["premium-id"])

    async def test_plain_emoji_uses_official_animated_emoji_asset(self) -> None:
        sticker = SimpleNamespace(
            is_video=False,
            is_animated=True,
            emoji="🙂",
            file_id="animated-file-id",
            file_size=1024,
        )
        bot = SimpleNamespace(
            get_sticker_set=AsyncMock(
                return_value=SimpleNamespace(stickers=[sticker]),
            )
        )
        message = SimpleNamespace(
            text="🙂",
            entities=None,
            caption_entities=None,
            sticker=None,
            photo=None,
            animation=None,
            video=None,
            document=None,
            bot=bot,
        )
        with patch("bot.handlers.recolor._ANIMATED_EMOJI_SOURCES", None):
            source = await _resolve_recolor_source(message)

        self.assertEqual(source.suffix, ".tgs")
        self.assertEqual(source.file_id, "animated-file-id")
        bot.get_sticker_set.assert_awaited_once_with("AnimatedEmojies")

    async def test_second_sticker_replaces_previous_result_panel(self) -> None:
        bot = SimpleNamespace(delete_message=AsyncMock())
        message = SimpleNamespace(bot=bot)
        state = SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "recolor_panel_is_sticker": True,
                    "panel_chat_id": 42,
                    "panel_message_id": 900,
                }
            ),
            update_data=AsyncMock(),
        )
        new_panel = SimpleNamespace(chat=SimpleNamespace(id=42), message_id=901)
        with patch(
            "bot.handlers.recolor.answer_tool_photo",
            new=AsyncMock(return_value=new_panel),
        ):
            await _show_recolor_palette(message, state)

        bot.delete_message.assert_awaited_once_with(42, 900)
        state.update_data.assert_awaited_once_with(
            recolor_panel_is_sticker=False,
            panel_chat_id=42,
            panel_message_id=901,
            panel_tool_key="recolor",
        )

    async def test_handler_sends_result_as_sticker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.webp"
            Image.new("RGBA", (512, 512), (120, 60, 210, 255)).save(source, "WEBP")
            result_message = SimpleNamespace(chat=SimpleNamespace(id=42), message_id=900)
            events: list[str] = []

            async def delete_panel(*args, **kwargs):
                events.append("delete_progress")

            async def send_result(*args, **kwargs):
                events.append("send_result")
                return result_message

            bot = SimpleNamespace(
                id=1,
                delete_message=AsyncMock(side_effect=delete_panel),
                send_sticker=AsyncMock(side_effect=send_result),
                send_chat_action=AsyncMock(),
            )
            message = SimpleNamespace(
                bot=bot,
                chat=SimpleNamespace(id=42),
                from_user=SimpleNamespace(is_bot=True),
            )
            state = SimpleNamespace(
                get_data=AsyncMock(
                    return_value={
                        "recolor_input_path": str(source),
                        "panel_chat_id": 42,
                        "panel_message_id": 100,
                        "recolor_adaptive": True,
                    }
                ),
                set_state=AsyncMock(),
                update_data=AsyncMock(),
            )

            with (
                patch(
                    "bot.handlers.recolor.edit_stored_panel",
                    new=AsyncMock(),
                ),
                patch(
                    "bot.handlers.recolor.recolor_asset",
                    wraps=recolor_asset,
                ) as recolor,
            ):
                await _recolor_and_send(message, state, "#0A84FF")

            bot.delete_message.assert_awaited_once_with(42, 100)
            bot.send_sticker.assert_awaited_once()
            bot.send_chat_action.assert_awaited()
            self.assertEqual(events, ["send_result", "delete_progress"])
            self.assertTrue(recolor.call_args.args[3])
            state.update_data.assert_awaited_once_with(
                recolor_input_path=None,
                recolor_source_emoji=None,
                recolor_adaptive=False,
                recolor_panel_is_sticker=True,
                panel_chat_id=42,
                panel_message_id=900,
                panel_tool_key="recolor",
            )


if __name__ == "__main__":
    unittest.main()
