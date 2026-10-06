import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bot.config import get_settings
from bot.services.administrators import AdministratorStore, parse_admin_id
from bot.services.private_storage import SessionCache
from bot.services.render_history import RenderHistoryStore
from bot.services.render_models import RenderSettings, RenderSource, SourceKind
from bot.services.render_settings import RenderSettingsStore
from bot.services.user_preferences import UserPreferencesStore


class SessionCacheTests(unittest.TestCase):
    def test_expiry_capacity_and_copies(self) -> None:
        now = [0.0]
        cache = SessionCache(ttl=10, max_users=2, clock=lambda: now[0])
        source = {"nested": {"value": 1}}
        cache.put(1, source)
        source["nested"]["value"] = 99
        self.assertEqual(cache.get(1)["nested"]["value"], 1)
        cache.put(2, {})
        cache.put(3, {"value": 3})
        self.assertEqual(cache.get(1), {})
        self.assertEqual(cache.get(3), {"value": 3})
        now[0] = 11.0
        self.assertEqual(cache.get(3), {})
        self.assertEqual(len(cache._users), 0)

    def test_read_refreshes_idle_expiry(self) -> None:
        now = [0.0]
        cache = SessionCache(ttl=10, clock=lambda: now[0])
        cache.put(1, {"value": 1})
        now[0] = 9.0
        self.assertEqual(cache.get(1), {"value": 1})
        now[0] = 11.0
        self.assertEqual(cache.get(1), {"value": 1})


class AdminStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_primary_admins_can_manage_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "administrators.json"
            store = AdministratorStore(path, frozenset({42}))
            self.assertFalse(path.exists())
            self.assertTrue(await store.add(42, 7))
            self.assertFalse(await store.add(42, 7))
            self.assertTrue(store.is_admin(7))
            self.assertFalse(store.can_manage(7))
            with self.assertRaises(PermissionError):
                await store.add(7, 99)
            with self.assertRaises(PermissionError):
                await store.remove(7, 42)
            with self.assertRaises(ValueError):
                await store.remove(42, 42)
            reloaded = AdministratorStore(path, frozenset({42}))
            self.assertEqual(reloaded.list_ids(), [7, 42])
            self.assertTrue(await store.remove(42, 7))
            self.assertFalse(store.is_admin(7))
            self.assertEqual(json.loads(path.read_text())["admin_ids"], [])
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_invalid_admin_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "administrators.json"
            path.write_text('{"admin_ids": ["@user"]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                AdministratorStore(path, frozenset({42}))

    def test_id_and_environment_validation(self) -> None:
        for value in ("", "0", "-1", "@name", "1.5", "١٢", str(2**52)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_admin_id(value)
        with patch.dict("os.environ", {"BOT_TOKEN": "test-token", "ADMIN_IDS": " 42,7,42 "}):
            self.assertEqual(get_settings().admin_ids, frozenset({42, 7}))
        with patch.dict("os.environ", {"BOT_TOKEN": "test-token", "ADMIN_IDS": ""}):
            self.assertEqual(get_settings().admin_ids, frozenset())
        with patch.dict("os.environ", {"BOT_TOKEN": "test-token", "ADMIN_IDS": "@name"}):
            with self.assertRaises(RuntimeError):
                get_settings()


class PrivacyStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_guest_preferences_work_only_in_current_process_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = UserPreferencesStore(path, is_admin=lambda _: False)
            await store.save_section(7, "code_screenshot", {"theme": "nord"})
            await store.save_section(7, "password", {"length": 24})
            self.assertEqual(await store.load_section(7, "code_screenshot", {"theme": "seti"}), {"theme": "nord"})
            self.assertEqual(await store.load_section(7, "password", {"length": 16}), {"length": 24})
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])
            reloaded = UserPreferencesStore(path, is_admin=lambda _: False)
            self.assertEqual(await reloaded.load_section(7, "code_screenshot", {"theme": "seti"}), {"theme": "seti"})

    async def test_guest_language_is_never_saved_even_in_session_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = UserPreferencesStore(path, is_admin=lambda _: False)
            await store.save_section(7, "language", {"code": "en"})
            self.assertEqual(await store.load_section(7, "language", {"code": None}), {"code": None})
            self.assertEqual(len(store._sessions._users), 0)
            self.assertFalse(path.exists())

    async def test_guest_saves_do_not_modify_existing_admin_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = UserPreferencesStore(path, is_admin=lambda user_id: user_id == 42)
            await store.save_section(42, "language", {"code": "ru"})
            before = path.read_bytes()
            await store.save_section(7, "password", {"length": 24})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(set(json.loads(before)["users"]), {"42"})

    async def test_guest_render_settings_are_temporary_and_history_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            history_path = Path(directory) / "history.json"
            settings = RenderSettingsStore(settings_path, is_admin=lambda _: False)
            history = RenderHistoryStore(history_path, is_admin=lambda _: False)
            expected = RenderSettings(background_color="#112233")
            await settings.save(7, expected)
            self.assertEqual(await settings.load(7), expected)
            await history.add(7, expected, [RenderSource(SourceKind.STICKER, "private-file", ".webp")], None, 1.0)
            self.assertEqual(await history.load(7), [])
            await history.clear(7)
            self.assertEqual(list(Path(directory).iterdir()), [])
            reloaded = RenderSettingsStore(settings_path, is_admin=lambda _: False)
            self.assertEqual(await reloaded.load(7), RenderSettings())

    async def test_startup_cleanup_preserves_only_admin_records_in_all_stores(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for store_class in (UserPreferencesStore, RenderSettingsStore, RenderHistoryStore):
                with self.subTest(store=store_class.__name__):
                    path = Path(directory) / f"{store_class.__name__}.json"
                    original = {"version": 1, "users": {"42": {}, "7": {}, "042": {}, "invalid": {}}}
                    path.write_text(json.dumps(original), encoding="utf-8")
                    path.with_suffix(".tmp").write_text(json.dumps(original), encoding="utf-8")
                    store = store_class(path, is_admin=lambda user_id: user_id == 42)
                    self.assertEqual(await store.prune_non_admins(), 6)
                    self.assertEqual(json.loads(path.read_text())["users"], {"42": {}})
                    self.assertFalse(path.with_suffix(".tmp").exists())

    async def test_empty_admin_list_prunes_all_legacy_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            path.write_text('{"users": {"7": {"language": {"code": "ru"}}}}', encoding="utf-8")
            store = UserPreferencesStore(path, is_admin=lambda _: False)
            self.assertEqual(await store.prune_non_admins(), 1)
            self.assertEqual(json.loads(path.read_text())["users"], {})

    async def test_corrupt_cleanup_fails_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            original = '{"users": {"7": {}}}'
            path.write_text(original, encoding="utf-8")
            path.with_suffix(".tmp").write_text("{broken", encoding="utf-8")
            store = UserPreferencesStore(path, is_admin=lambda _: False)
            with self.assertRaises(RuntimeError):
                await store.prune_non_admins()
            self.assertEqual(path.read_text(), original)

    async def test_revocation_deletes_settings_and_cannot_persist_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admin_ids = {7, 42}
            path = Path(directory) / "preferences.json"
            store = UserPreferencesStore(path, is_admin=admin_ids.__contains__)
            await store.save_section(7, "language", {"code": "en"})
            await store.save_section(42, "language", {"code": "ru"})
            admin_ids.remove(7)
            await store.forget_user(7)
            await store.save_section(7, "language", {"code": "en"})
            self.assertEqual(set(json.loads(path.read_text())["users"]), {"42"})

    async def test_forget_clears_guest_session_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = UserPreferencesStore(path, is_admin=lambda _: False)
            await store.save_section(7, "password", {"length": 24})
            await store.forget_user(7)
            self.assertEqual(await store.load_section(7, "password", {"length": 16}), {"length": 16})
            self.assertFalse(path.exists())
