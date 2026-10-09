import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Document, Message, PhotoSize, Update, User

from bot import main as bot_main
from bot.handlers import code_screenshot, file_converter, link_shortener, pdf_tools, qr_tools
from bot.middlewares import (
    AdminAccessMiddleware, AntiSpamMiddleware, HeavyRequestMiddleware,
    LanguageMiddleware, StatisticsMiddleware,
)
from bot.middlewares.anti_spam import upload_size
from bot.services.administrators import AdministratorStore
from bot.services.anti_spam import AntiSpamLimiter, AntiSpamPolicy
from bot.services.statistics import Statistics


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def message(user_id: int = 7, text: str = "light", language: str = "ru", **kwargs) -> Message:
    return Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=user_id, type="private"),
                   from_user=User(id=user_id, is_bot=False, first_name="Not retained", language_code=language),
                   text=text, **kwargs)


def callback(user_id: int = 7, language: str = "ru") -> CallbackQuery:
    return CallbackQuery(id="callback", from_user=message(user_id, language=language).from_user,
                         chat_instance="test", message=message(user_id), data="light")


class AntiSpamLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.limiter = AntiSpamLimiter(clock=self.clock)

    def accept(self, user_id: int = 7) -> None:
        self.assertIsNone(self.limiter.begin(user_id))
        self.limiter.finish(user_id)

    def test_default_burst_then_ten_second_pause(self) -> None:
        for _ in range(6):
            self.accept()
        denial = self.limiter.begin(7)
        self.assertEqual((denial.reason, denial.retry_after, denial.notify), ("rate", 10, True))
        self.clock.advance(9)
        denial = self.limiter.begin(7)
        self.assertEqual((denial.retry_after, denial.notify), (1, False))
        self.clock.advance(1)
        self.accept()

    def test_attempts_during_pause_do_not_extend_it(self) -> None:
        for _ in range(6):
            self.accept()
        self.limiter.begin(7)
        deadline = self.limiter._users[7].blocked_until
        for _ in range(9):
            self.clock.advance(1)
            self.assertIsNotNone(self.limiter.begin(7))
        self.assertEqual(self.limiter._users[7].blocked_until, deadline)
        self.clock.advance(1)
        self.accept()

    def test_one_token_recovers_every_two_seconds(self) -> None:
        for _ in range(6):
            self.accept()
        self.clock.advance(2)
        self.accept()
        self.assertEqual(self.limiter.begin(7).reason, "rate")

    def test_only_one_request_per_user_but_other_users_are_independent(self) -> None:
        self.assertIsNone(self.limiter.begin(7))
        self.assertEqual(self.limiter.begin(7).reason, "busy")
        self.accept(8)
        self.limiter.finish(7)
        self.accept(7)

    def test_global_rate_limit_also_covers_rotating_user_ids(self) -> None:
        for user_id in range(30):
            self.accept(user_id)
        self.assertEqual(self.limiter.begin(31).reason, "capacity")
        self.assertNotIn(31, self.limiter._users)
        self.clock.advance(0.11)
        self.accept(31)

    def test_global_rate_limit_covers_known_users_too(self) -> None:
        self.limiter = AntiSpamLimiter(replace(AntiSpamPolicy(), global_burst=2), clock=self.clock)
        self.accept(7)
        self.accept(8)
        self.assertEqual(self.limiter.begin(7).reason, "capacity")
        self.assertFalse(self.limiter._users[7].active)

    def test_cache_is_bounded_and_does_not_evict_existing_limits(self) -> None:
        self.limiter = AntiSpamLimiter(replace(AntiSpamPolicy(), max_users=2), clock=self.clock)
        self.accept(7)
        self.accept(8)
        for user_id in range(100, 200):
            self.assertEqual(self.limiter.begin(user_id).reason, "capacity")
        self.assertEqual(set(self.limiter._users), {7, 8})

    def test_idle_entries_expire_after_ten_minutes(self) -> None:
        self.accept()
        self.clock.advance(600)
        self.accept(8)
        self.assertNotIn(7, self.limiter._users)

    def test_active_requests_are_never_pruned(self) -> None:
        self.limiter = AntiSpamLimiter(replace(AntiSpamPolicy(), max_users=2), clock=self.clock)
        self.assertIsNone(self.limiter.begin(7))
        self.accept(8)
        self.clock.advance(601)
        self.accept(9)
        self.assertEqual(set(self.limiter._users), {7, 9})
        self.assertTrue(self.limiter._users[7].active)

    def test_warnings_have_per_user_and_global_budgets(self) -> None:
        self.accept(7)
        self.assertTrue(self.limiter.reject(7, "busy").notify)
        self.assertFalse(self.limiter.reject(7, "busy").notify)
        self.assertTrue(self.limiter.reject(8, "capacity").notify)
        self.assertTrue(self.limiter.reject(9, "capacity").notify)
        self.assertFalse(self.limiter.reject(10, "capacity").notify)
        self.clock.advance(3)
        self.assertTrue(self.limiter.reject(10, "capacity").notify)
        self.clock.advance(7)
        self.assertTrue(self.limiter.reject(7, "busy").notify)

    def test_two_heavy_slots_with_no_queue(self) -> None:
        for user_id in (7, 8, 9):
            self.assertIsNone(self.limiter.begin(user_id))
        self.assertIsNone(self.limiter.begin_heavy(7))
        self.assertIsNone(self.limiter.begin_heavy(8))
        self.assertEqual(self.limiter.begin_heavy(9).reason, "capacity")
        self.assertEqual(self.limiter.active_heavy, 2)
        self.limiter.finish_heavy()
        self.assertIsNone(self.limiter.begin_heavy(9))

    def test_heavy_processing_has_five_second_interval(self) -> None:
        self.assertIsNone(self.limiter.begin(7))
        self.assertIsNone(self.limiter.begin_heavy(7))
        self.limiter.finish_heavy()
        self.limiter.finish(7)
        self.assertIsNone(self.limiter.begin(7))
        denial = self.limiter.begin_heavy(7)
        self.assertEqual((denial.reason, denial.retry_after), ("heavy", 5))
        self.clock.advance(5)
        self.assertIsNone(self.limiter.begin_heavy(7))

    def test_upload_slots_do_not_start_or_enforce_processing_cooldown(self) -> None:
        self.assertIsNone(self.limiter.begin(7))
        self.assertIsNone(self.limiter.begin_heavy(7, cooldown=False))
        self.limiter.finish_heavy()
        self.assertIsNone(self.limiter.begin_heavy(7))
        self.limiter.finish_heavy()
        self.assertIsNone(self.limiter.begin_heavy(7, cooldown=False))

    def test_cache_contains_no_user_names_texts_or_languages(self) -> None:
        self.accept()
        activity = self.limiter._users[7]
        self.assertEqual(set(activity.__dataclass_fields__),
                         {"bucket", "last_seen", "active", "blocked_until", "heavy_after", "notice_after"})

    def test_invalid_policy_is_rejected(self) -> None:
        for field in AntiSpamPolicy.__dataclass_fields__:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(AntiSpamPolicy(), **{field: 0})


class AntiSpamMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.limiter = AntiSpamLimiter(clock=self.clock)
        self.outer = AntiSpamMiddleware(self.limiter)
        self.inner = HeavyRequestMiddleware(self.limiter)
        self.admin_ids = {42, 43}
        self.counters = Statistics()
        for patcher in (
            patch("bot.middlewares.anti_spam.administrator_store.is_admin", side_effect=lambda uid: uid in self.admin_ids),
            patch("bot.middlewares.anti_spam.statistics", self.counters),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def dispatch(self, event, handler, heavy=False):
        async def inner(event, data):
            data["handler"] = SimpleNamespace(flags={"heavy": heavy})
            return await self.inner(handler, event, data)
        return await self.outer(inner, event, {})

    async def test_messages_and_callbacks_share_one_user_budget(self) -> None:
        handler = AsyncMock()
        with patch.object(Message, "answer", AsyncMock()), patch.object(CallbackQuery, "answer", AsyncMock()) as answer:
            for _ in range(3):
                await self.dispatch(message(), handler)
                await self.dispatch(callback(), handler)
            await self.dispatch(callback(), handler)
        self.assertEqual(handler.await_count, 6)
        answer.assert_awaited_once()
        self.assertEqual(self.counters.rejected_requests, 1)

    async def test_same_user_in_different_chats_cannot_bypass_budget(self) -> None:
        handler = AsyncMock()
        with patch.object(Message, "answer", AsyncMock()):
            for chat_id in range(7):
                event = message().model_copy(update={"chat": Chat(id=chat_id, type="private")})
                await self.dispatch(event, handler)
        self.assertEqual(handler.await_count, 6)

    async def test_primary_and_additional_administrators_bypass_every_limit(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        admins = AdministratorStore(Path(directory.name) / "admins.json", frozenset({42}))
        await admins.add(42, 43)
        self.limiter = AntiSpamLimiter(replace(AntiSpamPolicy(), max_users=1, global_burst=1, max_heavy=1), clock=self.clock)
        self.outer = AntiSpamMiddleware(self.limiter)
        self.inner = HeavyRequestMiddleware(self.limiter)
        self.assertIsNone(self.limiter.begin(7))
        self.assertIsNone(self.limiter.begin_heavy(7))
        handler = AsyncMock()
        oversized = Document(file_id="file", file_unique_id="file", file_size=100 * 1024 * 1024)
        with patch("bot.middlewares.anti_spam.administrator_store", admins), \
             patch.object(Message, "answer", AsyncMock()) as answer:
            for _ in range(20):
                for user_id in (42, 43):
                    await self.dispatch(message(user_id, document=oversized), handler, heavy=True)
                    await self.dispatch(callback(user_id), handler, heavy=True)
        self.assertEqual(handler.await_count, 80)
        self.assertEqual(set(self.limiter._users), {7})
        self.assertEqual(self.limiter.active_heavy, 1)
        self.assertEqual(self.counters.rejected_requests, 0)
        answer.assert_not_awaited()

    async def test_concurrent_admin_requests_are_not_serialized(self) -> None:
        started = 0
        both_started = asyncio.Event()
        release = asyncio.Event()
        async def handler(event, data):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await release.wait()
        tasks = [asyncio.create_task(self.dispatch(message(42), handler, heavy=True)) for _ in range(2)]
        try:
            await asyncio.wait_for(both_started.wait(), 1)
        finally:
            release.set()
            await asyncio.gather(*tasks)
        self.assertEqual(self.limiter.active_heavy, 0)

    async def test_revoked_administrator_is_limited_from_next_update(self) -> None:
        handler = AsyncMock()
        await self.dispatch(message(43), handler)
        self.admin_ids.remove(43)
        with patch.object(Message, "answer", AsyncMock()):
            for _ in range(7):
                await self.dispatch(message(43), handler)
        self.assertEqual(handler.await_count, 7)
        self.assertEqual(self.counters.rejected_requests, 1)

    async def test_promotion_during_request_can_bypass_heavy_guard(self) -> None:
        async def promoted(event, data):
            self.admin_ids.add(7)
            data["handler"] = SimpleNamespace(flags={"heavy": True})
            return await self.inner(AsyncMock(return_value="ok"), event, data)
        self.assertEqual(await self.outer(promoted, message(), {}), "ok")
        self.assertEqual(self.limiter.active_heavy, 0)
        self.assertFalse(self.limiter._users[7].active)

    async def test_revocation_during_admin_request_does_not_require_missing_guest_state(self) -> None:
        async def revoked(event, data):
            self.admin_ids.remove(42)
            data["handler"] = SimpleNamespace(flags={"heavy": True})
            return await self.inner(AsyncMock(return_value="ok"), event, data)
        self.assertEqual(await self.outer(revoked, message(42), {}), "ok")

    async def test_concurrent_guest_request_is_rejected_without_running_handler(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        async def handler(event, data):
            started.set()
            await release.wait()
        task = asyncio.create_task(self.dispatch(message(), handler, heavy=True))
        try:
            await asyncio.wait_for(started.wait(), 1)
            second = AsyncMock()
            with patch.object(Message, "answer", AsyncMock()):
                await self.dispatch(message(), second, heavy=True)
            second.assert_not_awaited()
        finally:
            release.set()
            await task
        self.assertFalse(self.limiter._users[7].active)
        self.assertEqual(self.limiter.active_heavy, 0)

    async def test_heavy_slots_and_user_slot_release_after_error_and_cancellation(self) -> None:
        for exception in (ValueError("handler failed"), asyncio.CancelledError()):
            with self.subTest(exception=type(exception).__name__):
                self.clock.advance(10)
                with self.assertRaises(type(exception)):
                    await self.dispatch(message(), AsyncMock(side_effect=exception), heavy=True)
                self.assertEqual(self.limiter.active_heavy, 0)
                self.assertFalse(self.limiter._users[7].active)

    async def test_guest_upload_is_rejected_before_handler_or_download(self) -> None:
        oversized = Document(file_id="file", file_unique_id="file", file_size=20 * 1024 * 1024 + 1)
        handler = AsyncMock()
        with patch.object(Message, "answer", AsyncMock()) as answer:
            await self.dispatch(message(document=oversized), handler, heavy="upload")
        handler.assert_not_awaited()
        self.assertIn("20", answer.call_args.args[0])
        self.assertFalse(self.limiter._users[7].active)
        self.assertEqual(self.limiter.active_heavy, 0)

    async def test_saturated_heavy_pool_rejects_work_but_not_light_menu(self) -> None:
        for user_id in (8, 9):
            self.assertIsNone(self.limiter.begin(user_id))
            self.assertIsNone(self.limiter.begin_heavy(user_id))
        work = AsyncMock()
        menu = AsyncMock(return_value="menu")
        with patch.object(Message, "answer", AsyncMock()):
            await self.dispatch(message(), work, heavy=True)
            result = await self.dispatch(message(), menu)
        work.assert_not_awaited()
        self.assertEqual(result, "menu")
        self.assertEqual(self.limiter.active_heavy, 2)

    async def test_file_at_limit_and_unknown_size_are_allowed(self) -> None:
        for size in (20 * 1024 * 1024, None):
            handler = AsyncMock()
            document = Document(file_id="file", file_unique_id="file", file_size=size)
            await self.dispatch(message(document=document), handler, heavy="upload")
            handler.assert_awaited_once()

    def test_upload_size_checks_photos_and_documents(self) -> None:
        photo = PhotoSize(file_id="photo", file_unique_id="photo", width=20, height=20, file_size=42)
        self.assertEqual(upload_size(message(photo=[photo])), 42)
        self.assertEqual(upload_size(message()), 0)

    async def test_rejection_warning_uses_current_telegram_language(self) -> None:
        handler = AsyncMock()
        for _ in range(6):
            await self.dispatch(message(), handler)
        with patch.object(Message, "answer", AsyncMock()) as answer:
            await self.dispatch(message(language="en-GB"), handler)
        self.assertIn("Too many requests", answer.call_args.args[0])

    async def test_repeated_rejections_do_not_flood_replies(self) -> None:
        handler = AsyncMock()
        with patch.object(Message, "answer", AsyncMock()) as answer:
            for _ in range(100):
                await self.dispatch(message(), handler)
        self.assertEqual(handler.await_count, 6)
        answer.assert_awaited_once()
        self.assertEqual(self.counters.rejected_requests, 94)

    async def test_telegram_warning_errors_do_not_retry_or_leak_slots(self) -> None:
        method = SendMessage(chat_id=7, text="warning")
        for error in (TelegramBadRequest(method=method, message="query is too old"),
                      TelegramRetryAfter(method=method, message="flood", retry_after=60)):
            with self.subTest(error=type(error).__name__):
                self.clock.advance(10)
                oversized = Document(file_id="file", file_unique_id="file", file_size=30 * 1024 * 1024)
                with patch.object(Message, "answer", AsyncMock(side_effect=error)) as answer:
                    await self.dispatch(message(document=oversized), AsyncMock())
                answer.assert_awaited_once()
                self.assertFalse(self.limiter._users[7].active)


class AntiSpamIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clock = Clock()
        self.limiter = AntiSpamLimiter(clock=self.clock)
        self.bot = Bot(token="123456:testing-token")
        self.bot.session = AsyncMock()
        self.dp = Dispatcher()
        self.addAsyncCleanup(self.dp.storage.close)
        self.addAsyncCleanup(self.bot.session.close)
        for observer in (self.dp.message, self.dp.callback_query):
            observer.outer_middleware(AdminAccessMiddleware())
            observer.outer_middleware(AntiSpamMiddleware(self.limiter))
            observer.outer_middleware(StatisticsMiddleware())
            observer.middleware(HeavyRequestMiddleware(self.limiter))
        self.router = Router()
        self.dp.include_router(self.router)
        self.admin_patch = patch("bot.middlewares.anti_spam.administrator_store.is_admin", return_value=False)
        self.admin_patch.start()
        self.addCleanup(self.admin_patch.stop)

    async def test_real_dispatcher_shares_message_and_callback_limits(self) -> None:
        captured = []
        async def capture(event):
            captured.append(event)
        self.router.message.register(capture)
        self.router.callback_query.register(capture)
        with patch.object(CallbackQuery, "answer", AsyncMock()) as answer:
            for update_id in range(3):
                await self.dp.feed_update(self.bot, Update(update_id=update_id, message=message()))
                await self.dp.feed_update(self.bot, Update(update_id=update_id + 10, callback_query=callback()))
            await self.dp.feed_update(self.bot, Update(update_id=30, callback_query=callback()))
        self.assertEqual(len(captured), 6)
        answer.assert_awaited_once()

    async def test_heavy_flags_resolve_in_child_router_and_light_menu_is_not_delayed(self) -> None:
        captured = []
        async def capture(event):
            captured.append(event.text)
        self.router.message.register(capture, F.text == "heavy", flags={"heavy": True})
        self.router.message.register(capture, F.text == "light")
        with patch.object(Message, "answer", AsyncMock()):
            for update_id, text in enumerate(("heavy", "heavy", "light")):
                await self.dp.feed_update(self.bot, Update(update_id=update_id, message=message(text=text)))
        self.assertEqual(captured, ["heavy", "light"])
        self.assertEqual(self.limiter.active_heavy, 0)

    async def test_unauthorized_admin_stays_silent_even_during_flood_pause(self) -> None:
        async def capture(event):
            pass
        self.router.message.register(capture)
        with patch("bot.middlewares.admin_access.administrator_store.is_admin", return_value=False), \
             patch.object(Message, "answer", AsyncMock()) as answer, \
             patch.object(CallbackQuery, "answer", AsyncMock()) as callback_answer:
            for update_id in range(7):
                await self.dp.feed_update(self.bot, Update(update_id=update_id, message=message()))
            answer.reset_mock()
            for update_id in range(10, 30):
                await self.dp.feed_update(self.bot, Update(update_id=update_id, message=message(text="/admin")))
                event = callback().model_copy(update={"data": "admin:statistics"})
                await self.dp.feed_update(self.bot, Update(update_id=update_id + 30, callback_query=event))
        answer.assert_not_awaited()
        callback_answer.assert_not_awaited()

    async def test_production_registration_shares_limiter_and_preserves_middleware_order(self) -> None:
        dp = Dispatcher()
        self.addAsyncCleanup(dp.storage.close)
        with patch.object(bot_main, "Dispatcher", return_value=dp), \
             patch.object(bot_main, "Bot", return_value=self.bot), \
             patch.object(bot_main, "setup_routers", return_value=(Router(),)), \
             patch.object(bot_main.logging, "basicConfig"), \
             patch.object(bot_main, "prune_non_admin_data", AsyncMock(return_value=0)), \
             patch.object(bot_main, "poll_bot", AsyncMock()):
            await bot_main.run_bot()
        limiters = []
        for observer in (dp.message, dp.callback_query):
            self.assertEqual([type(m) for m in observer.outer_middleware],
                             [AdminAccessMiddleware, AntiSpamMiddleware, StatisticsMiddleware, LanguageMiddleware])
            self.assertEqual([type(m) for m in observer.middleware], [HeavyRequestMiddleware])
            limiters.extend((observer.outer_middleware[1].limiter, observer.middleware[0].limiter))
        self.assertTrue(all(limiter is limiters[0] for limiter in limiters))

    def test_all_active_expensive_handlers_have_guard_flags(self) -> None:
        expected = {
            code_screenshot.router: {"render_code": True},
            file_converter.router: {"receive_file": "upload", "handle_file_action": True},
            pdf_tools.router: {"receive_pdf": True, "receive_pdf_image": "upload", "create_pdf_from_images": True},
            qr_tools.router: {"handle_qr_text": True, "handle_wifi_password": True, "handle_phone": True,
                              "handle_telegram": True, "scan_qr": True},
            link_shortener.router: {"handle_url": True},
        }
        for router, required in expected.items():
            actual = {handler.callback.__name__: handler.flags.get("heavy")
                      for observer in (router.message, router.callback_query) for handler in observer.handlers}
            for name, flag in required.items():
                with self.subTest(router=router.name, handler=name):
                    self.assertEqual(actual[name], flag)
