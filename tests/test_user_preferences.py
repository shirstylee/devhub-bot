import json
import tempfile
import unittest
from pathlib import Path

from bot.services.user_preferences import STORE_VERSION, UserPreferencesStore


class UserPreferencesStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_sections_survive_reload_and_are_isolated_by_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = UserPreferencesStore(path)
            defaults = {"theme": "seti", "language": "javascript", "background": "carbon"}

            await store.save_section(
                42,
                "code_screenshot",
                {"theme": "nord", "language": "python", "background": "#123456"},
            )

            reloaded = UserPreferencesStore(path)
            self.assertEqual(
                await reloaded.load_section(42, "code_screenshot", defaults),
                {"theme": "nord", "language": "python", "background": "#123456"},
            )
            self.assertEqual(
                await reloaded.load_section(99, "code_screenshot", defaults),
                defaults,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], STORE_VERSION)
            self.assertFalse(path.with_suffix(".tmp").exists())

    async def test_unknown_saved_keys_do_not_leak_into_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            path.write_text(
                json.dumps(
                    {
                        "version": STORE_VERSION,
                        "users": {"7": {"password": {"length": 24, "unexpected": True}}},
                    }
                ),
                encoding="utf-8",
            )
            store = UserPreferencesStore(path)
            loaded = await store.load_section(7, "password", {"length": 16, "count": 1})
            self.assertEqual(loaded, {"length": 24, "count": 1})


if __name__ == "__main__":
    unittest.main()
