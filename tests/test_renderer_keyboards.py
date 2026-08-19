import unittest
from datetime import UTC, datetime

from bot.keyboards.emoji_renderer import (
    COLOR_PICKER_URL,
    GOOGLE_FONTS_URL,
    color_input_keyboard,
    custom_media_keyboard,
    font_input_keyboard,
    format_keyboard,
    pack_keyboard,
    position_keyboard,
    render_history_keyboard,
    render_result_keyboard,
    renderer_back_keyboard,
    renderer_main_keyboard,
    size_keyboard,
    watermark_keyboard,
)
from bot.services.render_models import OutputFormat, RenderSettings, WatermarkPosition
from bot.services.render_history import RenderHistoryEntry
from bot.services.render_models import RenderSource, SourceKind


class RendererKeyboardTests(unittest.TestCase):
    def test_external_pages_are_web_apps(self) -> None:
        color_button = color_input_keyboard("render:home").inline_keyboard[0][0]
        font_button = font_input_keyboard().inline_keyboard[0][0]
        self.assertIsNone(color_button.url)
        self.assertEqual(color_button.web_app.url, COLOR_PICKER_URL)
        self.assertEqual(font_button.web_app.url, GOOGLE_FONTS_URL)

    def test_selected_controls_use_success_style(self) -> None:
        format_buttons = format_keyboard(OutputFormat.VIDEO).inline_keyboard[0]
        self.assertEqual(format_buttons[1].style, "success")
        positions = position_keyboard(WatermarkPosition.BOTTOM_RIGHT).inline_keyboard
        self.assertEqual(positions[1][1].style, "success")
        main = renderer_main_keyboard(RenderSettings(), False, has_background=True)
        self.assertEqual(main.inline_keyboard[1][1].style, "success")
        media_buttons = [button for row in custom_media_keyboard(True).inline_keyboard for button in row]
        self.assertTrue(any(button.callback_data == "render:media:clear" for button in media_buttons))
        size_buttons = [button for row in size_keyboard(55).inline_keyboard for button in row]
        self.assertTrue(any(button.callback_data == "render:size:down" for button in size_buttons))
        self.assertTrue(any(button.callback_data == "render:size:up" for button in size_buttons))
        self.assertTrue(any(button.callback_data == "render:size:input" for button in size_buttons))
        watermark_buttons = [
            button
            for row in watermark_keyboard(RenderSettings(watermark_size=8)).inline_keyboard
            for button in row
        ]
        self.assertTrue(any(button.text == "Размер: 8%" for button in watermark_buttons))
        main_buttons = [
            button
            for row in renderer_main_keyboard(RenderSettings(), False).inline_keyboard
            for button in row
        ]
        self.assertTrue(any(button.callback_data == "render:defaults" for button in main_buttons))

    def test_render_result_has_repeat_and_settings(self) -> None:
        buttons = [button for row in render_result_keyboard().inline_keyboard for button in row]
        self.assertEqual(
            [button.callback_data for button in buttons],
            ["render:again", "render:settings", "render:history", "menu:back"],
        )

    def test_history_has_repeat_clear_and_back_actions(self) -> None:
        entry = RenderHistoryEntry(
            entry_id="abc123",
            created_at=datetime.now(UTC).isoformat(),
            settings=RenderSettings(output_format=OutputFormat.GIF),
            sources=[RenderSource(SourceKind.STICKER, "file-id", ".webp", "🐝")],
            background_source=None,
            duration=3.0,
        )
        buttons = [
            button
            for row in render_history_keyboard([entry]).inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in buttons],
            [
                "render:history:repeat:abc123",
                "render:history:clear",
                "render:home",
            ],
        )
        self.assertEqual(buttons[1].style, "danger")

    def test_every_settings_screen_has_its_own_default_button(self) -> None:
        keyboards = (
            (
                color_input_keyboard(
                    "render:home",
                    default_callback="render:default:background",
                ),
                "render:default:background",
            ),
            (
                renderer_back_keyboard(default_callback="render:default:resolution"),
                "render:default:resolution",
            ),
            (format_keyboard(OutputFormat.VIDEO), "render:default:format"),
            (custom_media_keyboard(False), "render:default:media"),
            (
                color_input_keyboard(
                    "render:home",
                    allow_original=True,
                    default_callback="render:default:emoji_color",
                ),
                "render:default:emoji_color",
            ),
            (size_keyboard(80), "render:default:emoji_size"),
            (watermark_keyboard(RenderSettings()), "render:default:watermark"),
            (font_input_keyboard(), "render:default:watermark_font"),
            (
                color_input_keyboard(
                    "render:watermark",
                    default_callback="render:default:watermark_color",
                ),
                "render:default:watermark_color",
            ),
            (
                position_keyboard(WatermarkPosition.TOP_LEFT),
                "render:default:watermark_position",
            ),
        )
        for keyboard, expected_callback in keyboards:
            callbacks = {
                button.callback_data
                for row in keyboard.inline_keyboard
                for button in row
            }
            self.assertIn(expected_callback, callbacks)

    def test_pack_selection_is_limited_and_highlighted(self) -> None:
        items = [{"label": "⭐"} for _ in range(12)]
        keyboard = pack_keyboard(items, {1, 3}, 0)
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        selected = [button for button in buttons if button.style == "success"]
        self.assertGreaterEqual(len(selected), 2)
        self.assertTrue(any(button.callback_data == "render:pack:page:1" for button in buttons))


if __name__ == "__main__":
    unittest.main()
