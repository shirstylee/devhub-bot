import tempfile
import unittest
from pathlib import Path

from bot.services.render_history import HISTORY_LIMIT, RenderHistoryStore
from bot.services.render_models import OutputFormat, RenderSettings, RenderSource, SourceKind


class RenderHistoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_ten_newest_complete_snapshots_per_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RenderHistoryStore(Path(directory) / "history.json")
            for index in range(HISTORY_LIMIT + 2):
                await store.add(
                    42,
                    RenderSettings(
                        width=256 + index * 2,
                        height=256,
                        output_format=OutputFormat.GIF,
                        background_color=f"#{index:06X}",
                    ),
                    [
                        RenderSource(
                            SourceKind.STICKER,
                            f"sticker-{index}",
                            ".tgs",
                            f"Эмодзи {index}",
                            True,
                        )
                    ],
                    RenderSource(
                        SourceKind.USER_MEDIA,
                        f"background-{index}",
                        ".mp4",
                        "Видео-фон",
                    ),
                    float(index),
                )
            await store.add(
                7,
                RenderSettings(),
                [RenderSource(SourceKind.STICKER, "other-user", ".webp")],
                None,
                3.0,
            )

            entries = await store.load(42)
            self.assertEqual(len(entries), HISTORY_LIMIT)
            self.assertEqual(entries[0].sources[0].file_id, "sticker-11")
            self.assertEqual(entries[-1].sources[0].file_id, "sticker-2")
            self.assertEqual(entries[0].settings.width, 278)
            self.assertEqual(entries[0].background_source.file_id, "background-11")
            self.assertEqual(entries[0].duration, 11.0)

            await store.clear(42)
            self.assertEqual(await store.load(42), [])
            self.assertEqual((await store.load(7))[0].sources[0].file_id, "other-user")


if __name__ == "__main__":
    unittest.main()
