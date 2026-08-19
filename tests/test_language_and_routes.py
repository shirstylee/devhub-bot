import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, Message, User

from bot.handlers import setup_routers
from bot.keyboards.language import language_keyboard
from bot.keyboards.main_menu import main_menu_keyboard
from bot.services.language import get_user_language, set_user_language
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

    async def test_language_is_missing_until_explicitly_selected(self) -> None:
        store = AsyncMock()
        store.load_section.return_value = {"code": None}
        with patch("bot.services.language.user_preferences_store", store):
            self.assertIsNone(await get_user_language(42))

    async def test_language_selection_is_persisted(self) -> None:
        store = AsyncMock()
        with patch("bot.services.language.user_preferences_store", store):
            self.assertEqual(await set_user_language(42, "en"), "en")
        store.save_section.assert_awaited_once_with(42, "language", {"code": "en"})

    async def test_middleware_blocks_handlers_without_language(self) -> None:
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
