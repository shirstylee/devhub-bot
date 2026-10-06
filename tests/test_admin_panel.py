from datetime import datetime, UTC
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.handlers import admin
from bot.keyboards.admin import admin_keyboard
from bot.middlewares import AdminAccessMiddleware, LanguageMiddleware, StatisticsMiddleware
from bot.services.administrators import AdministratorStore
from bot.services.statistics import Statistics
from bot.states import AdminStates, JsonStates


def message(user_id: int = 7, text: str = "/admin", chat_type: str = "private") -> Message:
    return Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=user_id, type=chat_type),
                   from_user=User(id=user_id, is_bot=False, first_name="Private name", language_code="ru"), text=text)


def callback(user_id: int = 7, data: str = "admin:home") -> CallbackQuery:
    return CallbackQuery(id="callback", from_user=message(user_id).from_user,
                         chat_instance="test", message=message(user_id), data=data)


class AdminPanelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.admins = AdministratorStore(Path(self.directory.name) / "admins.json", frozenset({42}))
        self.access_patch = patch("bot.middlewares.admin_access.administrator_store", self.admins)
        self.handler_patch = patch("bot.handlers.admin.administrator_store", self.admins)
        self.keyboard_patch = patch("bot.keyboards.admin.administrator_store", self.admins)
        for patcher in (self.access_patch, self.handler_patch, self.keyboard_patch):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.storage = MemoryStorage()
        self.state = FSMContext(self.storage, StorageKey(bot_id=123456, chat_id=42, user_id=42))
        self.addAsyncCleanup(self.storage.close)

    async def test_admin_sections_have_catalog_premium_emoji_in_both_languages(self) -> None:
        await self.admins.add(42, 7)
        for lang in ("ru", "en"):
            self.assertGreaterEqual(admin.home_text(lang).count("<tg-emoji "), 6)
            for action in ("admins:0", "statistics", "privacy", "add", "remove:7", "reset", "prune", "home"):
                with self.subTest(lang=lang, action=action), \
                     patch.object(CallbackQuery, "answer", AsyncMock()), \
                     patch.object(Message, "edit_text", AsyncMock()) as edit:
                    await admin.admin_callback(callback(42, "admin:" + action), self.state, lang)
                self.assertGreaterEqual(edit.call_args.args[0].count("<tg-emoji "), 2)

    def test_admin_keyboard_rows_match_requested_layout(self) -> None:
        expected = [
            ["admin:admins:0", "admin:statistics"],
            ["admin:privacy"],
            ["admin:reset", "admin:home"],
            ["admin:menu"],
        ]
        for lang, label in (("ru", "Главное меню"), ("en", "Main menu")):
            rows = admin_keyboard(lang).inline_keyboard
            self.assertEqual([[button.callback_data for button in row] for row in rows], expected)
            self.assertEqual(rows[-1][0].text, label)
            self.assertIsNotNone(rows[-1][0].icon_custom_emoji_id)

    async def test_main_menu_button_clears_state_and_opens_real_main_menu(self) -> None:
        for action in ("menu", "close"):
            await self.state.set_state(AdminStates.waiting_admin_id)
            with patch.object(CallbackQuery, "answer", AsyncMock()) as acknowledge, \
                 patch("bot.handlers.admin.answer_tool_photo", AsyncMock()) as answer, \
                 patch.object(Message, "delete", AsyncMock()) as delete:
                await admin.admin_callback(callback(42, "admin:" + action), self.state, "ru")
            self.assertIsNone(await self.state.get_state())
            acknowledge.assert_awaited_once()
            delete.assert_awaited_once()
            self.assertEqual(answer.call_args.args[1], "main")
            self.assertIn("<b>DevHub Bot</b>", answer.call_args.args[2])
            buttons = {button.callback_data for row in answer.call_args.kwargs["reply_markup"].inline_keyboard for button in row}
            self.assertTrue({"menu:json", "menu:password", "menu:language"} <= buttons)
            self.assertFalse(any(button.startswith("admin:") for button in buttons))

    async def test_main_menu_still_opens_when_old_panel_cannot_be_deleted(self) -> None:
        error = TelegramBadRequest(method=DeleteMessage(chat_id=42, message_id=1), message="message can't be deleted")
        with patch.object(CallbackQuery, "answer", AsyncMock()), \
             patch("bot.handlers.admin.answer_tool_photo", AsyncMock()) as answer, \
             patch.object(Message, "delete", AsyncMock(side_effect=error)), \
             patch.object(Message, "edit_reply_markup", AsyncMock()) as remove_keyboard:
            await admin.admin_callback(callback(42, "admin:menu"), self.state)
        answer.assert_awaited_once()
        remove_keyboard.assert_awaited_once_with(reply_markup=None)

    async def test_unauthorized_admin_events_are_silent(self) -> None:
        for event in (message(), message(text="/ADMIN"), message(text="/admin@some_bot"),
                      message(text="/admin arguments"), callback(), callback(data="admin:confirm_reset")):
            handler = AsyncMock()
            await AdminAccessMiddleware()(handler, event, {})
            handler.assert_not_awaited()

    async def test_group_admin_and_revoked_state_are_silent(self) -> None:
        handler = AsyncMock()
        await AdminAccessMiddleware()(handler, message(42, chat_type="group"), {})
        await AdminAccessMiddleware()(handler, message(text="42"), {"raw_state": AdminStates.waiting_admin_id.state})
        handler.assert_not_awaited()

    async def test_private_admin_is_marked_and_language_prompt_is_bypassed(self) -> None:
        handler = AsyncMock()
        data = {"event_from_user": message(42).from_user}
        async def language_handler(event, event_data):
            return await LanguageMiddleware()(handler, event, event_data)
        with patch("bot.middlewares.language.get_user_language", AsyncMock(return_value=None)), \
             patch("bot.middlewares.language.answer_tool_photo", AsyncMock()) as prompt:
            await AdminAccessMiddleware()(language_handler, message(42), data)
        handler.assert_awaited_once()
        prompt.assert_not_awaited()
        self.assertTrue(data["admin_event"])
        self.assertEqual(data["lang"], "ru")

    async def test_direct_handlers_also_reject_ordinary_users(self) -> None:
        with patch.object(Message, "answer", AsyncMock()) as answer, \
             patch.object(CallbackQuery, "answer", AsyncMock()) as acknowledge:
            await admin.open_admin(message(), self.state)
            await admin.admin_callback(callback(data="admin:add"), self.state)
            await admin.admin_callback(callback(data="admin:menu"), self.state)
            await admin.receive_admin_id(message(text="99"), self.state)
        answer.assert_not_awaited()
        acknowledge.assert_not_awaited()
        self.assertFalse(self.admins.is_admin(99))

    async def test_panel_contains_useful_buttons_and_clears_tool_state(self) -> None:
        await self.state.set_state(JsonStates.waiting_json)
        with patch.object(Message, "answer", AsyncMock()) as answer:
            await admin.open_admin(message(42), self.state)
        self.assertIsNone(await self.state.get_state())
        buttons = {button.callback_data for row in answer.call_args.kwargs["reply_markup"].inline_keyboard for button in row}
        self.assertTrue({"admin:admins:0", "admin:statistics", "admin:privacy", "admin:reset"} <= buttons)

    async def test_add_validate_cancel_and_confirm_remove(self) -> None:
        with patch.object(CallbackQuery, "answer", AsyncMock()), patch.object(Message, "edit_text", AsyncMock()):
            await admin.admin_callback(callback(42, "admin:add"), self.state)
        self.assertEqual(await self.state.get_state(), AdminStates.waiting_admin_id.state)
        with patch.object(Message, "answer", AsyncMock()):
            await admin.receive_admin_id(message(42, "@username"), self.state)
            self.assertEqual(await self.state.get_state(), AdminStates.waiting_admin_id.state)
            await admin.receive_admin_id(message(42, "7"), self.state)
            self.assertTrue(self.admins.is_admin(7))
            await self.state.set_state(AdminStates.waiting_admin_id)
            await admin.receive_admin_id(message(42, "/cancel"), self.state)
        self.assertIsNone(await self.state.get_state())
        with patch.object(CallbackQuery, "answer", AsyncMock()), patch.object(Message, "edit_text", AsyncMock()), \
             patch("bot.handlers.admin.forget_user_data", AsyncMock()) as forget:
            await admin.admin_callback(callback(42, "admin:remove:7"), self.state)
            self.assertTrue(self.admins.is_admin(7))
            forget.assert_not_awaited()
            await admin.admin_callback(callback(42, "admin:confirm_remove:7"), self.state)
        self.assertFalse(self.admins.is_admin(7))
        forget.assert_awaited_once_with(7)

    async def test_additional_admin_cannot_manage_even_with_forged_callbacks(self) -> None:
        await self.admins.add(42, 7)
        with patch.object(CallbackQuery, "answer", AsyncMock()) as answer:
            for action in ("add", "remove:42", "confirm_remove:42"):
                await admin.admin_callback(callback(7, "admin:" + action), self.state)
        self.assertEqual(answer.await_count, 3)
        self.assertEqual(self.admins.list_ids(), [7, 42])
        self.assertIsNone(await self.state.get_state())

    async def test_primary_cannot_be_removed_and_own_reset_requires_confirmation(self) -> None:
        with patch.object(CallbackQuery, "answer", AsyncMock()), patch.object(Message, "edit_text", AsyncMock()), \
             patch("bot.handlers.admin.forget_user_data", AsyncMock()) as forget:
            await admin.admin_callback(callback(42, "admin:confirm_remove:42"), self.state)
            self.assertTrue(self.admins.is_admin(42))
            await admin.admin_callback(callback(42, "admin:reset"), self.state)
            forget.assert_not_awaited()
            await admin.admin_callback(callback(42, "admin:confirm_reset"), self.state)
        forget.assert_awaited_once_with(42)

    async def test_stale_remove_button_does_not_clear_an_ordinary_users_session(self) -> None:
        with patch.object(CallbackQuery, "answer", AsyncMock()), patch.object(Message, "edit_text", AsyncMock()), \
             patch("bot.handlers.admin.forget_user_data", AsyncMock()) as forget:
            await admin.admin_callback(callback(42, "admin:confirm_remove:7"), self.state)
        forget.assert_not_awaited()

    async def test_admin_traffic_is_excluded_and_errors_are_counted(self) -> None:
        counters = Statistics()
        with patch("bot.middlewares.statistics.statistics", counters):
            await StatisticsMiddleware()(AsyncMock(), message(42), {"admin_event": True})
            with self.assertRaises(RuntimeError):
                await StatisticsMiddleware()(AsyncMock(side_effect=RuntimeError("test")), message(), {})
        self.assertEqual(counters.messages, 1)
        self.assertEqual(counters.errors, 1)

    async def test_aggregate_statistics_never_store_personal_values(self) -> None:
        counters = Statistics()
        counters.record(message(text="Private message contents"))
        counters.record(callback(data="menu:json"))
        counters.record(callback(data="menu:unknown:private-value"))
        snapshot = counters.snapshot()
        self.assertEqual(snapshot["messages"], 1)
        self.assertEqual(snapshot["callbacks"], 2)
        self.assertEqual(snapshot["tool_opens"], {"json": 1})
        self.assertNotIn("Private", str(vars(counters)))
        self.assertNotIn("unknown", str(vars(counters)))

    async def test_real_dispatcher_silence_and_admin_command_in_other_state(self) -> None:
        bot = Bot(token="123456:testing-token")
        bot.session = AsyncMock(return_value=message(42))
        dp = Dispatcher(storage=self.storage)
        for observer in (dp.message, dp.callback_query):
            observer.outer_middleware(AdminAccessMiddleware())
            observer.outer_middleware(StatisticsMiddleware())
            observer.outer_middleware(LanguageMiddleware())
        router = Router()
        router.message.register(admin.open_admin, Command("admin", ignore_case=True))
        router.callback_query.register(admin.admin_callback, F.data.startswith("admin:"))
        router.message.register(admin.receive_admin_id, AdminStates.waiting_admin_id)
        dp.include_router(router)
        with patch("bot.middlewares.language.get_user_language", AsyncMock(return_value=None)), \
             patch("bot.middlewares.language.answer_tool_photo", AsyncMock()) as prompt:
            await dp.feed_update(bot, Update(update_id=1, message=message()))
            await dp.feed_update(bot, Update(update_id=2, callback_query=callback(data="admin:statistics")))
            guest_state = FSMContext(self.storage, StorageKey(bot_id=123456, chat_id=7, user_id=7))
            await guest_state.set_state(JsonStates.waiting_json)
            await dp.feed_update(bot, Update(update_id=4, message=message(text="/admin@some_bot")))
            bot.session.assert_not_awaited()
            prompt.assert_not_awaited()
            await self.state.set_state(JsonStates.waiting_json)
            await dp.feed_update(bot, Update(update_id=3, message=message(42)))
            bot.session.assert_awaited_once()
            prompt.assert_not_awaited()
        self.assertIsNone(await self.state.get_state())
