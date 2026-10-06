import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.handlers import setup_routers
from bot.handlers import common, language as language_handlers
from bot.keyboards.language import language_keyboard
from bot.keyboards.main_menu import main_menu_keyboard
from bot.services.language import get_telegram_language, get_user_language, set_user_language
from bot.middlewares.language import LanguageMiddleware
from bot.utils.premium_emoji import EN_FLAG, RU_FLAG


class LanguageAndRoutesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user = User(id=42, is_bot=False, first_name="Test")
        self.message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=self.user,
            text="/start",
        )

    async def test_admin_language_is_missing_until_explicitly_selected(self) -> None:
        store = AsyncMock()
        store.load_section.return_value = {"code": None}
        with patch("bot.services.language.user_preferences_store", store), \
             patch("bot.services.language.administrator_store.is_admin", return_value=True):
            self.assertIsNone(await get_user_language(42))

    async def test_admin_language_selection_is_persisted(self) -> None:
        store = AsyncMock()
        with patch("bot.services.language.user_preferences_store", store), \
             patch("bot.services.language.administrator_store.is_admin", return_value=True):
            self.assertEqual(await set_user_language(42, "en"), "en")
        store.save_section.assert_awaited_once_with(42, "language", {"code": "en"})

    async def test_middleware_prompts_admins_without_selected_language(self) -> None:
        handler = AsyncMock()
        data = {"event_from_user": self.user}
        with (
            patch("bot.middlewares.language.get_user_language", AsyncMock(return_value=None)),
            patch("bot.middlewares.language.answer_tool_photo", AsyncMock()) as answer,
        ):
            await LanguageMiddleware()(handler, self.message, data)
        handler.assert_not_awaited()
        answer.assert_awaited_once()

    async def test_middleware_injects_selected_language(self) -> None:
        handler = AsyncMock(return_value="handled")
        data = {"event_from_user": self.user}
        with patch("bot.middlewares.language.get_user_language", AsyncMock(return_value="en")):
            result = await LanguageMiddleware()(handler, self.message, data)
        self.assertEqual(result, "handled")
        self.assertEqual(data["lang"], "en")
        handler.assert_awaited_once_with(self.message, data)

    def test_telegram_language_codes_and_english_fallback(self) -> None:
        for code, expected in (("ru", "ru"), ("ru-RU", "ru"), ("RU_ru", "ru"),
                               ("en", "en"), ("en-GB", "en"), ("de", "en"),
                               ("uk", "en"), (None, "en"), ("", "en")):
            with self.subTest(code=code):
                self.assertEqual(get_telegram_language(code), expected)

    async def test_guest_uses_current_telegram_language_without_accessing_preferences(self) -> None:
        store = AsyncMock()
        with patch("bot.services.language.user_preferences_store", store), \
             patch("bot.services.language.administrator_store.is_admin", return_value=False):
            self.assertEqual(await get_user_language(42, "ru"), "ru")
            self.assertEqual(await get_user_language(42, "en-US"), "en")
        store.load_section.assert_not_awaited()
        store.save_section.assert_not_awaited()

    async def test_guest_cannot_save_a_manual_language_preference(self) -> None:
        store = AsyncMock()
        with patch("bot.services.language.user_preferences_store", store), \
             patch("bot.services.language.administrator_store.is_admin", return_value=False):
            with self.assertRaises(PermissionError):
                await set_user_language(42, "en")
        store.save_section.assert_not_awaited()

    async def test_guest_messages_and_callbacks_immediately_use_telegram_locale(self) -> None:
        store = AsyncMock()
        handler = AsyncMock()
        with patch("bot.services.language.user_preferences_store", store), \
             patch("bot.services.language.administrator_store.is_admin", return_value=False), \
             patch("bot.middlewares.language.answer_tool_photo", AsyncMock()) as prompt:
            for code, expected in (("ru", "ru"), ("en-GB", "en")):
                actor = self.user.model_copy(update={"language_code": code})
                events = (
                    self.message.model_copy(update={"from_user": actor}),
                    CallbackQuery(id="test", from_user=actor, chat_instance="test", message=self.message, data="menu:json"),
                )
                for event in events:
                    data = {"event_from_user": actor}
                    await LanguageMiddleware()(handler, event, data)
                    self.assertEqual(data["lang"], expected)
        self.assertEqual(handler.await_count, 4)
        prompt.assert_not_awaited()
        store.load_section.assert_not_awaited()
        store.save_section.assert_not_awaited()

    async def test_stale_guest_language_button_does_not_save_or_clear_tool_state(self) -> None:
        actor = self.user.model_copy(update={"language_code": "en"})
        event = CallbackQuery(id="test", from_user=actor, chat_instance="test", message=self.message, data="lang:ru")
        state = AsyncMock()
        with patch("bot.handlers.language.administrator_store.is_admin", return_value=False), \
             patch("bot.handlers.language.set_user_language", AsyncMock()) as save, \
             patch("bot.handlers.language.answer_callback", AsyncMock()) as acknowledge:
            await language_handlers.save_language(event, state)
        save.assert_not_awaited()
        state.clear.assert_not_awaited()
        self.assertIn("Telegram", acknowledge.call_args.args[1])

    async def test_language_command_and_old_menu_button_offer_choice_only_to_admins(self) -> None:
        event = CallbackQuery(id="test", from_user=self.user, chat_instance="test", message=self.message, data="menu:language")
        for is_admin in (False, True):
            with self.subTest(is_admin=is_admin), \
                 patch("bot.handlers.language.administrator_store.is_admin", return_value=is_admin), \
                 patch("bot.handlers.language.answer_tool_photo", AsyncMock()) as answer, \
                 patch("bot.handlers.language.edit_tool_photo", AsyncMock()) as edit:
                await language_handlers.choose_language_command(self.message, "en")
                await language_handlers.choose_language_callback(event, "en")
            for call in (answer.call_args, edit.call_args):
                callbacks = {button.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for button in row}
                self.assertEqual("lang:ru" in callbacks, is_admin)
                self.assertEqual("lang:en" in callbacks, is_admin)
                self.assertIn("menu:back", callbacks)

    async def test_main_menu_language_button_follows_actual_administrator_role(self) -> None:
        state = AsyncMock()
        state.get_data.return_value = {}
        event = CallbackQuery(id="test", from_user=self.user, chat_instance="test", message=self.message, data="menu:back")
        for is_admin in (False, True):
            with self.subTest(is_admin=is_admin), \
                 patch("bot.handlers.common.administrator_store.is_admin", return_value=is_admin), \
                 patch("bot.handlers.common.answer_tool_photo", AsyncMock()) as answer, \
                 patch("bot.handlers.common.edit_tool_photo", AsyncMock()) as edit:
                await common.start(self.message, state, "ru")
                await common.menu(self.message, state, "ru")
                await common.callback_back_to_menu(event, state, "ru")
            calls = answer.call_args_list + edit.call_args_list
            self.assertEqual(len(calls), 3)
            for call in calls:
                callbacks = {button.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for button in row}
                self.assertEqual("menu:language" in callbacks, is_admin)

    async def test_real_dispatcher_uses_locale_from_each_guest_update(self) -> None:
        storage = MemoryStorage()
        self.addAsyncCleanup(storage.close)
        bot = Bot(token="123456:testing-token")
        bot.session = AsyncMock()
        dp = Dispatcher(storage=storage)
        dp.message.outer_middleware(LanguageMiddleware())
        dp.callback_query.outer_middleware(LanguageMiddleware())
        captured_languages = []
        async def capture_language(event, lang: str):
            captured_languages.append(lang)
        router = Router()
        router.message.register(capture_language)
        router.callback_query.register(capture_language)
        dp.include_router(router)
        store = AsyncMock()
        with patch("bot.services.language.user_preferences_store", store), \
             patch("bot.services.language.administrator_store.is_admin", return_value=False):
            russian_user = self.user.model_copy(update={"language_code": "ru"})
            english_user = self.user.model_copy(update={"language_code": "en-GB"})
            await dp.feed_update(bot, Update(update_id=1, message=self.message.model_copy(update={"from_user": russian_user})))
            await dp.feed_update(bot, Update(update_id=2, callback_query=CallbackQuery(
                id="test", from_user=english_user, chat_instance="test", message=self.message, data="menu:json")))
        self.assertEqual(captured_languages, ["ru", "en"])
        store.load_section.assert_not_awaited()
        store.save_section.assert_not_awaited()
        bot.session.assert_not_awaited()

    def test_language_keyboard_uses_catalog_premium_flags(self) -> None:
        buttons = language_keyboard().inline_keyboard[0]
        self.assertEqual(buttons[0].icon_custom_emoji_id, RU_FLAG.emoji_id)
        self.assertEqual(buttons[1].icon_custom_emoji_id, EN_FLAG.emoji_id)

    def test_language_settings_has_back_but_required_choice_does_not(self) -> None:
        required_callbacks = {
            button.callback_data
            for row in language_keyboard().inline_keyboard
            for button in row
        }
        settings_callbacks = {
            button.callback_data
            for row in language_keyboard("ru").inline_keyboard
            for button in row
        }
        self.assertNotIn("menu:back", required_callbacks)
        self.assertIn("menu:back", settings_callbacks)

    def test_removed_features_are_not_registered_or_shown(self) -> None:
        router_names = {router.name for router in setup_routers()}
        self.assertNotIn("emoji_renderer", router_names)
        self.assertNotIn("recolor", router_names)

        callbacks = {
            button.callback_data
            for row in main_menu_keyboard("en").inline_keyboard
            for button in row
        }
        self.assertNotIn("menu:emoji_renderer", callbacks)
        self.assertNotIn("menu:recolor", callbacks)
        self.assertIn("menu:text_tools", callbacks)


if __name__ == "__main__":
    unittest.main()
