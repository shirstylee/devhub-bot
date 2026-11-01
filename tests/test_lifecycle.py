import asyncio
from contextvars import copy_context
from datetime import UTC, datetime
import os
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Chat, Message, Update, User

from bot import main as bot_main
from bot.handlers import file_converter, pdf_tools, qr_tools, color_picker
from bot.middlewares import LifecycleMiddleware
from bot.services.maintenance import PrivacyMaintenance
from bot.services.sessions import ExpiringMemoryStorage
from bot.services.user_preferences import UserPreferencesStore
from bot.states import FileStates
from bot.utils.temp_files import TemporaryFileManager, run_temp_worker


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def wall(self) -> float:
        return 1_700_000_000 + self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FilesFixture:
    def init_files(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.root = self.directory / "temp"
        self.root.mkdir()
        self.clock = Clock()
        self.files = TemporaryFileManager(self.root, clock=self.clock, wall_clock=self.clock.wall)

    def file(self, suffix=".png") -> Path:
        path = self.files.make_path(suffix)
        path.write_bytes(b"temporary user data")
        return path


class TemporaryFileTests(FilesFixture, unittest.TestCase):
    def setUp(self) -> None:
        self.init_files()

    def test_generated_paths_are_unique_and_confined(self) -> None:
        first = self.file()
        second = self.file()
        directory = self.files.make_dir()
        self.assertNotEqual(first, second)
        self.assertRegex(first.name, r"^[a-f0-9]{32}\.png$")
        self.assertEqual(first.parent, self.root)
        self.assertTrue(directory.is_dir())

    def test_unused_files_expire_after_ten_minutes(self) -> None:
        path = self.file()
        self.clock.advance(599)
        self.assertEqual(self.files.sweep(), set())
        self.clock.advance(1)
        self.assertEqual(self.files.sweep(), {path})
        self.assertFalse(path.exists())

    def test_active_file_is_protected_even_after_an_hour(self) -> None:
        path = self.file()
        with self.files.scope([path]):
            self.clock.advance(3600)
            self.assertEqual(self.files.sweep(), set())
            self.assertTrue(path.exists())
        self.clock.advance(599)
        self.assertEqual(self.files.sweep(), set())
        self.clock.advance(1)
        self.assertEqual(self.files.sweep(), {path})

    def test_unretained_created_files_are_deleted_at_scope_exit(self) -> None:
        with self.files.scope():
            path = self.file()
            directory = self.files.make_dir()
            (directory / "page.png").write_bytes(b"output")
            self.clock.advance(700)
            self.assertEqual(self.files.sweep(), set())
        self.assertFalse(path.exists())
        self.assertFalse(directory.exists())

    def test_retained_input_survives_scope_exit_then_expires(self) -> None:
        with self.files.scope() as scope:
            path = self.file()
            scope.retain([path])
        self.assertTrue(path.exists())
        self.clock.advance(600)
        self.assertEqual(self.files.sweep(), {path})

    def test_explicit_delete_waits_for_all_active_readers(self) -> None:
        path = self.file()
        with self.files.scope([path]):
            with self.files.scope([path]):
                self.files.delete(path)
                self.assertTrue(path.exists())
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_startup_sweep_removes_old_orphans_but_not_fresh_ones(self) -> None:
        old = self.root / ("a" * 32 + ".png")
        fresh = self.root / ("b" * 32 + ".png")
        old.write_bytes(b"old process")
        fresh.write_bytes(b"recent process")
        os.utime(old, (self.clock.wall() - 601,) * 2)
        os.utime(fresh, (self.clock.wall() - 599,) * 2)
        self.assertEqual(self.files.sweep(), {old})
        self.assertTrue(fresh.exists())

    def test_sweep_preserves_unowned_files_gitkeep_and_admin_data(self) -> None:
        paths = [self.root / ".gitkeep", self.root / "notes.txt", self.directory / "administrators.json"]
        for path in paths:
            path.write_text("not temporary", encoding="utf-8")
            os.utime(path, (self.clock.wall() - 7200,) * 2)
        self.clock.advance(7200)
        self.files.sweep()
        self.files.delete(self.root, self.directory, *paths)
        for path in paths:
            self.assertEqual(path.read_text(encoding="utf-8"), "not temporary")

    def test_traversal_suffixes_and_external_paths_are_rejected(self) -> None:
        for suffix in ("../.env", ".png/../../.env", ".png\\secret", ".png:stream", ".", ".."):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.files.make_path(suffix)
        outside = self.directory / ("f" * 32 + ".png")
        outside.write_bytes(b"keep")
        self.files.delete(outside, self.root / ".." / outside.name)
        self.assertTrue(outside.exists())

    def test_symlink_targets_are_never_deleted(self) -> None:
        outside = self.directory / "outside.png"
        outside.write_bytes(b"keep")
        link = self.root / ("c" * 32 + ".png")
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Creating symlinks is not permitted")
        self.files.delete(link)
        self.clock.advance(7200)
        self.files.sweep()
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_bytes(), b"keep")

    def test_failed_unlink_is_retried(self) -> None:
        path = self.file()
        with patch.object(Path, "unlink", side_effect=PermissionError("busy")):
            self.files.delete(path)
        self.assertTrue(path.exists())
        self.assertEqual(self.files.pending_count, 1)
        self.files.sweep()
        self.assertFalse(path.exists())
        self.assertEqual(self.files.pending_count, 0)

    def test_only_known_file_fields_are_interpreted_as_paths(self) -> None:
        path = self.file()
        data = {"watermark_text": str(path), "file_id": str(path)}
        self.assertEqual(self.files.paths_in(data), set())
        self.assertEqual(self.files.without_paths(data, {path}), data)

    def test_worker_does_not_start_after_parent_scope_is_closed(self) -> None:
        called = []
        with self.files.scope():
            context = copy_context()
        with self.assertRaisesRegex(RuntimeError, "already finished"):
            context.run(run_temp_worker, lambda: called.append(True))
        self.assertEqual(called, [])

    def test_failed_worker_deletes_its_partial_output(self) -> None:
        paths = []
        def worker():
            paths.append(self.file())
            raise RuntimeError("encoding failed")
        with patch("bot.utils.temp_files.temporary_files", self.files):
            with self.assertRaisesRegex(RuntimeError, "encoding failed"):
                run_temp_worker(worker)
        self.assertFalse(paths[0].exists())


class SessionFixture(FilesFixture):
    def init_session(self) -> None:
        self.init_files()
        self.storage = ExpiringMemoryStorage(files=self.files, clock=self.clock)
        self.key = StorageKey(bot_id=123456, chat_id=7, user_id=7)
        self.state = FSMContext(self.storage, self.key)
        self.addAsyncCleanup(self.storage.close)
        self.middleware = LifecycleMiddleware(self.files)


class SessionLifecycleTests(SessionFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.init_session()

    async def test_missing_reads_do_not_retain_user_ids(self) -> None:
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})
        self.assertEqual(await self.state.get_value("missing", "default"), "default")
        await self.state.clear()
        self.assertEqual(self.storage.dialogs, {})

    async def test_dialog_data_and_files_expire_without_new_messages(self) -> None:
        path = self.file()
        await self.state.set_state(FileStates.waiting_file)
        await self.state.set_data({"file_input_path": str(path), "wifi_ssid": "private name"})
        self.clock.advance(899)
        self.assertEqual(self.storage.expire(), 0)
        self.clock.advance(1)
        self.assertEqual(self.storage.expire(), 1)
        self.assertFalse(path.exists())
        self.assertEqual(self.storage.dialogs, {})

    async def test_expired_state_is_not_returned_to_aiogram_filters(self) -> None:
        await self.state.set_state(FileStates.waiting_file)
        await self.state.set_data({"private": "input"})
        self.clock.advance(900)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})

    async def test_user_activity_renews_idle_timeout(self) -> None:
        await self.state.set_state(FileStates.waiting_file)
        self.clock.advance(600)
        await self.state.get_data()
        self.clock.advance(899)
        self.assertEqual(self.storage.expire(), 0)
        self.clock.advance(1)
        self.assertEqual(self.storage.expire(), 1)

    async def test_clear_and_replacing_input_remove_old_files(self) -> None:
        old = self.file()
        new = self.file()
        await self.state.set_data({"file_input_path": str(old)})
        await self.state.update_data(file_input_path=str(new))
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        await self.state.clear()
        self.assertFalse(new.exists())
        self.assertEqual(self.storage.dialogs, {})

    async def test_resetting_pdf_collection_removes_all_previous_images(self) -> None:
        paths = [self.file(), self.file()]
        await self.state.set_data({"pdf_images": list(map(str, paths))})
        await self.state.update_data(pdf_images=[])
        self.assertFalse(any(path.exists() for path in paths))

    async def test_successful_deletion_retry_also_removes_stale_state_reference(self) -> None:
        path = self.file()
        await self.state.set_state(FileStates.waiting_file)
        await self.state.set_data({"file_input_path": str(path)})
        maintenance = PrivacyMaintenance(self.storage, self.files)
        self.clock.advance(600)
        with patch.object(Path, "unlink", side_effect=PermissionError("busy")), \
             self.assertLogs("bot.services.maintenance", "WARNING"):
            await maintenance.sweep()
        self.assertTrue(path.exists())
        self.assertIn("file_input_path", self.storage.dialogs[self.key].data)
        await maintenance.sweep()
        self.assertFalse(path.exists())
        self.assertNotIn("file_input_path", self.storage.dialogs[self.key].data)

    async def test_saved_administrator_preferences_are_untouched(self) -> None:
        store = UserPreferencesStore(self.directory / "user_preferences.json", is_admin=lambda uid: uid == 42)
        await store.save_section(42, "code_screenshot", {"theme": "nord"})
        snapshot = store.path.read_bytes()
        admin_key = StorageKey(bot_id=123456, chat_id=42, user_id=42)
        await self.storage.set_data(admin_key, {"wifi_ssid": "private"})
        self.clock.advance(900)
        self.assertEqual(self.storage.expire(), 1)
        self.assertEqual(store.path.read_bytes(), snapshot)
        self.assertEqual(await store.load_section(42, "code_screenshot", {"theme": "seti"}), {"theme": "nord"})

    async def test_file_expiry_removes_references_without_renewing_dialog(self) -> None:
        path = self.file()
        await self.state.set_state(FileStates.waiting_file)
        await self.state.set_data({"file_input_path": str(path), "wifi_ssid": "private"})
        maintenance = PrivacyMaintenance(self.storage, self.files)
        self.clock.advance(600)
        await maintenance.sweep()
        self.assertFalse(path.exists())
        self.assertNotIn("file_input_path", self.storage.dialogs[self.key].data)
        self.assertIn("wifi_ssid", self.storage.dialogs[self.key].data)
        self.clock.advance(300)
        self.assertEqual(self.storage.expire(), 1)

    async def test_active_handler_protects_files_and_dialog_beyond_ttls(self) -> None:
        path = self.file()
        await self.state.set_state(FileStates.waiting_file)
        await self.state.set_data({"file_input_path": str(path)})
        maintenance = PrivacyMaintenance(self.storage, self.files)
        async def process(event, data):
            self.clock.advance(3600)
            await maintenance.sweep()
            self.assertTrue(path.exists())
            self.assertEqual(await self.state.get_state(), FileStates.waiting_file.state)
            return "done"
        self.assertEqual(await self.middleware(process, SimpleNamespace(), {"state": self.state}), "done")
        self.clock.advance(599)
        await maintenance.sweep()
        self.assertTrue(path.exists())
        self.clock.advance(1)
        await maintenance.sweep()
        self.assertFalse(path.exists())

    async def test_successful_output_is_deleted_only_after_handler_finishes(self) -> None:
        paths = []
        async def process(event, data):
            path = self.file()
            paths.append(path)
            self.files.delete(path)
            self.assertTrue(path.exists())
        await self.middleware(process, SimpleNamespace(), {"state": self.state})
        self.assertFalse(paths[0].exists())

    async def test_failed_and_cancelled_handlers_remove_partial_files_and_references(self) -> None:
        for error in (RuntimeError("failed"), asyncio.CancelledError()):
            paths = []
            async def process(event, data):
                path = self.file()
                paths.append(path)
                await self.state.update_data(file_input_path=str(path))
                raise error
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                await self.middleware(process, SimpleNamespace(), {"state": self.state})
            self.assertFalse(paths[0].exists())
            self.assertNotIn("file_input_path", await self.state.get_data())
            self.assertEqual(self.storage._active, {})

    async def test_worker_result_lease_is_transferred_until_sending_finishes(self) -> None:
        paths = []
        async def process(event, data):
            path = await asyncio.to_thread(run_temp_worker, self.file)
            paths.append(path)
            self.clock.advance(3600)
            self.files.sweep()
            self.assertTrue(path.exists())
        with patch("bot.utils.temp_files.temporary_files", self.files):
            await self.middleware(process, SimpleNamespace(), {"state": self.state})
        self.assertFalse(paths[0].exists())

    async def test_cancelling_awaiter_does_not_delete_files_under_running_native_worker(self) -> None:
        source = self.file()
        paths = []
        observed = []
        started = asyncio.Event()
        finished = asyncio.Event()
        release = Event()
        loop = asyncio.get_running_loop()
        def worker():
            paths.append(self.file())
            loop.call_soon_threadsafe(started.set)
            release.wait(3)
            observed.append(source.exists())
        def invoke():
            try:
                return run_temp_worker(worker, input_paths=[source])
            finally:
                loop.call_soon_threadsafe(finished.set)
        async def process(event, data):
            try:
                await asyncio.to_thread(invoke)
            finally:
                self.files.delete(source)
        with patch("bot.utils.temp_files.temporary_files", self.files):
            task = asyncio.create_task(self.middleware(process, SimpleNamespace(), {"state": self.state}))
            try:
                await asyncio.wait_for(started.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.clock.advance(3600)
                self.files.sweep()
                self.assertTrue(source.exists())
                self.assertTrue(paths[0].exists())
            finally:
                release.set()
                await asyncio.wait_for(finished.wait(), 3)
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(observed, [True])
        self.assertFalse(source.exists())
        self.assertFalse(paths[0].exists())

    async def test_periodic_cleanup_runs_without_incoming_updates_and_stops(self) -> None:
        path = self.file()
        await self.state.set_data({"file_input_path": str(path)})
        maintenance = PrivacyMaintenance(self.storage, self.files, interval=0.005)
        self.addAsyncCleanup(maintenance.close)
        cleaned = asyncio.Event()
        sweep = maintenance.sweep
        async def observe_sweep():
            await sweep()
            if not self.storage.dialogs:
                cleaned.set()
        with patch.object(maintenance, "sweep", side_effect=observe_sweep):
            await maintenance.start()
            self.clock.advance(901)
            await asyncio.wait_for(cleaned.wait(), 2)
        self.assertFalse(path.exists())
        await maintenance.close()
        self.assertIsNone(maintenance._task)

    async def test_startup_cleans_old_orphans_before_starting_background_task(self) -> None:
        path = self.root / ("e" * 32 + ".png")
        path.write_bytes(b"previous process")
        os.utime(path, (self.clock.wall() - 601,) * 2)
        maintenance = PrivacyMaintenance(self.storage, self.files)
        self.addAsyncCleanup(maintenance.close)
        await maintenance.start()
        self.assertFalse(path.exists())
        self.assertIsNotNone(maintenance._task)

    async def test_cleanup_error_is_retried_without_logging_sensitive_values(self) -> None:
        maintenance = PrivacyMaintenance(self.storage, self.files)
        with patch.object(maintenance, "sweep", AsyncMock(side_effect=[RuntimeError("private path"), None])) as sweep, \
             patch("bot.services.maintenance.asyncio.sleep", AsyncMock(side_effect=[None, None, asyncio.CancelledError()])), \
             self.assertLogs("bot.services.maintenance", "WARNING") as captured:
            with self.assertRaises(asyncio.CancelledError):
                await maintenance._run()
        self.assertEqual(sweep.await_count, 2)
        self.assertNotIn("private path", str(captured.output))

    async def test_real_dispatcher_does_not_route_expired_state(self) -> None:
        dp = Dispatcher(storage=self.storage)
        dp.message.outer_middleware(self.middleware)
        bot = Bot(token="123456:testing-token")
        self.addAsyncCleanup(bot.session.close)
        router = Router()
        capture = AsyncMock()
        async def capture_input(event):
            await capture(event)
        router.message.register(capture_input, FileStates.waiting_file)
        dp.include_router(router)
        await self.state.set_state(FileStates.waiting_file)
        self.clock.advance(900)
        event = Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=7, type="private"),
                        from_user=User(id=7, is_bot=False, first_name="test"), text="old input")
        await dp.feed_update(bot, Update(update_id=1, message=event))
        capture.assert_not_awaited()
        self.assertEqual(self.storage.dialogs, {})

    async def test_production_registers_startup_shutdown_and_expiring_storage(self) -> None:
        dispatchers = []
        def dispatcher_factory(**kwargs):
            dp = Dispatcher(**kwargs)
            dispatchers.append(dp)
            return dp
        with patch.object(bot_main, "Dispatcher", side_effect=dispatcher_factory), \
             patch.object(bot_main, "Bot"), \
             patch.object(bot_main, "setup_routers", return_value=(Router(),)), \
             patch.object(bot_main, "prune_non_admin_data", AsyncMock(return_value=0)), \
             patch.object(bot_main, "poll_bot", AsyncMock()), \
             patch.object(bot_main.logging, "basicConfig"):
            await bot_main.run_bot()
        dp = dispatchers[0]
        self.assertIsInstance(dp.storage, ExpiringMemoryStorage)
        startup = [handler.callback for handler in dp.startup.handlers]
        shutdown = [handler.callback for handler in dp.shutdown.handlers]
        self.assertTrue(any(isinstance(getattr(callback, "__self__", None), PrivacyMaintenance) for callback in startup))
        self.assertTrue(any(isinstance(getattr(callback, "__self__", None), PrivacyMaintenance) for callback in shutdown))
        await dp.storage.close()


class HandlerCleanupTests(SessionFixture, unittest.IsolatedAsyncioTestCase):
    # Use the real storage and temporary manager with fake Telegram methods.
    def setUp(self) -> None:
        self.init_session()

    def message(self, download, *, fail_send=False):
        async def answer(*args, **kwargs):
            if fail_send:
                raise RuntimeError("send failed")
        return SimpleNamespace(
            photo=None, document=SimpleNamespace(file_id="fake", file_name="input.png"),
            bot=SimpleNamespace(download=download), answer=AsyncMock(side_effect=answer),
        )

    async def download_ok(self, file_id, *, destination):
        destination.write_bytes(b"input")

    async def test_failed_upload_removes_partial_file(self) -> None:
        for receive in (file_converter.receive_file, pdf_tools.receive_pdf_image):
            downloaded = []
            async def fail(file_id, *, destination):
                destination.write_bytes(b"partial")
                downloaded.append(destination)
                raise RuntimeError("download failed")
            with self.subTest(handler=receive.__name__), \
                 patch("bot.utils.temp_files.temporary_files", self.files):
                with self.assertRaisesRegex(RuntimeError, "download failed"):
                    await receive(self.message(fail), self.state, "en")
            self.assertFalse(downloaded[0].exists())
        self.assertEqual(self.files.paths_in(await self.state.get_data()), set())

    async def test_successful_upload_is_retained_for_next_step(self) -> None:
        with patch("bot.utils.temp_files.temporary_files", self.files):
            await file_converter.receive_file(self.message(self.download_ok), self.state, "en")
        path = Path((await self.state.get_data())["file_input_path"])
        self.assertTrue(path.exists())
        await self.state.clear()
        self.assertFalse(path.exists())

    async def test_failed_upload_acknowledgement_does_not_retain_data(self) -> None:
        for receive in (file_converter.receive_file, pdf_tools.receive_pdf_image):
            with self.subTest(handler=receive.__name__), patch("bot.utils.temp_files.temporary_files", self.files):
                with self.assertRaisesRegex(RuntimeError, "send failed"):
                    await receive(self.message(self.download_ok, fail_send=True), self.state, "en")
            self.assertEqual(self.files.paths_in(await self.state.get_data()), set())
            self.assertEqual(list(self.root.iterdir()), [])

    async def test_file_processing_error_removes_source_and_output(self) -> None:
        source = self.file()
        await self.state.set_data({"file_input_path": str(source)})
        callback = SimpleNamespace(data="file:compress:50", answer=AsyncMock())
        with patch("bot.utils.temp_files.temporary_files", self.files), \
             patch.object(file_converter, "compress_image", side_effect=ValueError("invalid image")), \
             patch.object(file_converter, "answer_callback", AsyncMock()):
            await file_converter.handle_file_action(callback, self.state, "en")
        self.assertFalse(source.exists())
        self.assertFalse((await self.state.get_data()).get("file_input_path"))

    async def test_pdf_build_failure_removes_all_collected_images(self) -> None:
        sources = [self.file(), self.file()]
        await self.state.set_data({"pdf_images": list(map(str, sources))})
        callback = SimpleNamespace(answer=AsyncMock())
        with patch("bot.utils.temp_files.temporary_files", self.files), \
             patch.object(pdf_tools, "images_to_pdf", side_effect=RuntimeError("bad PDF")), \
             patch.object(pdf_tools, "answer_callback", AsyncMock()):
            with self.assertRaisesRegex(RuntimeError, "bad PDF"):
                await pdf_tools.create_pdf_from_images(callback, self.state, "en")
        self.assertFalse(any(source.exists() for source in sources))
        self.assertEqual((await self.state.get_data()).get("pdf_images"), [])

    async def test_qr_and_color_creation_failures_remove_partial_output(self) -> None:
        outputs = []
        def fail_image(*args):
            destination = args[-1]
            destination.write_bytes(b"partial image")
            outputs.append(destination)
            raise RuntimeError("image failed")
        with patch("bot.utils.temp_files.temporary_files", self.files), \
             patch.object(qr_tools, "create_qr_image", side_effect=fail_image), \
             patch.object(color_picker, "create_color_image", side_effect=fail_image):
            with self.assertRaisesRegex(RuntimeError, "image failed"):
                await qr_tools._send_qr(SimpleNamespace(), "text", "caption", "en")
            with self.assertRaisesRegex(RuntimeError, "image failed"):
                await color_picker._send_color(SimpleNamespace(), "#ffffff", (255, 255, 255), "en")
        self.assertTrue(outputs)
        self.assertFalse(any(path.exists() for path in outputs))
