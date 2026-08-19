import tempfile
import unittest
from pathlib import Path

from PIL import Image

from bot.services.code_screenshot import _font_bundle, _font_runs, create_code_screenshot


class CarbonScreenshotTests(unittest.TestCase):
    def test_carbon_layout_uses_high_resolution_seti_window(self) -> None:
        code = "const greet = (name) => `Hello ${name}`;\nconsole.log(greet('DevHub'));"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "carbon.png"
            create_code_screenshot(code, output, "javascript", "seti", "carbon")

            with Image.open(output) as image:
                self.assertGreaterEqual(image.width, 1580)
                self.assertGreaterEqual(image.height, 540)
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.getpixel((0, 0)), (171, 184, 195))
                self.assertEqual(image.getpixel((120, 120)), (21, 23, 24))
                red_dot = image.getpixel((160, 152))
                self.assertGreater(red_dot[0], 200)
                self.assertLess(red_dot[1], 130)

    def test_transparent_background_keeps_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "transparent.png"
            create_code_screenshot("print('ok')", output, "python", "seti", "transparent")
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_emoji_uses_fallback_font_instead_of_hack_tofu(self) -> None:
        fonts = _font_bundle(28)
        if fonts.emoji is None:
            self.skipTest("No emoji font is installed on this platform")
        runs = _font_runs("const launch = '🚀 😀 ✅'; // ⬅️ назад", fonts)
        emoji_runs = [value for value, _, embedded_color in runs if embedded_color]
        self.assertTrue(emoji_runs)
        self.assertIn("🚀", "".join(emoji_runs))
        self.assertIn("⬅", "".join(emoji_runs))
        self.assertNotIn("\ufe0f", "".join(value for value, _, _ in runs))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "emoji.png"
            create_code_screenshot(
                "const launch = '🚀 😀 ✅';",
                output,
                "javascript",
                "seti",
                "carbon",
            )
            with Image.open(output) as image:
                code_region = image.crop((140, 200, image.width - 100, image.height - 100))
                saturated_red = sum(
                    1
                    for red, green, blue in code_region.get_flattened_data()
                    if red > 210 and green < 100 and blue < 140
                )
                self.assertGreater(saturated_red, 20)


if __name__ == "__main__":
    unittest.main()
