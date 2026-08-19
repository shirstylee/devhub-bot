import json
import tempfile
import unittest
from pathlib import Path

from bot.services.render_models import OutputFormat, RenderSettings, WatermarkPosition
from bot.services.render_settings import RenderSettingsStore


class RenderSettingsStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_trip_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = RenderSettingsStore(path)
            settings = RenderSettings(
                background_color="#112233",
                width=1080,
                height=1080,
                output_format=OutputFormat.FILE,
                watermark_text="Привет",
                watermark_position=WatermarkPosition.TOP_LEFT,
                watermark_size=9,
                custom_background_file_id="saved-background",
                custom_background_suffix=".png",
                custom_background_label="Фон",
            )
            await store.save(42, settings)
            loaded = await store.load(42)
            self.assertEqual(loaded, settings)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)
            self.assertIn("42", payload["users"])

    async def test_corrupt_file_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{broken", encoding="utf-8")
            loaded = await RenderSettingsStore(path).load(7)
            self.assertEqual(loaded, RenderSettings())


if __name__ == "__main__":
    unittest.main()
