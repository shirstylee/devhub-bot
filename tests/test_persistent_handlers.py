import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.code_screenshot import open_code_screenshot
from bot.handlers.fake_data_generator import open_fake_data
from bot.handlers.password_generator import open_password_generator


class PersistentHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_code_screenshot_reopens_with_saved_theme_language_and_background(self) -> None:
        callback = SimpleNamespace(from_user=SimpleNamespace(id=42))
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        saved = {"theme": "nord", "language": "python", "background": "navy"}
        with (
            patch(
                "bot.handlers.code_screenshot._load_code_preferences",
                new=AsyncMock(return_value=saved),
            ),
            patch(
                "bot.handlers.code_screenshot.edit_tool_photo",
                new=AsyncMock(),
            ) as edit_panel,
        ):
            await open_code_screenshot(callback, state)

        state.update_data.assert_awaited_once_with(
            code_theme="nord",
            code_language="python",
            code_background="navy",
        )
        markup = edit_panel.await_args.kwargs["reply_markup"]
        summary = [button.text for button in markup.inline_keyboard[3]]
        self.assertIn("Тема: Nord", summary)
        self.assertIn("Фон: Темно-синий", summary)

    async def test_password_generator_reopens_with_saved_settings(self) -> None:
        callback = SimpleNamespace(from_user=SimpleNamespace(id=42))
        state = SimpleNamespace(update_data=AsyncMock())
        saved = {
            "length": 32,
            "count": 4,
            "digits": True,
            "symbols": False,
            "uppercase": True,
            "lowercase": True,
        }
        with (
            patch(
                "bot.handlers.password_generator._load_password_preferences",
                new=AsyncMock(return_value=saved),
            ),
            patch(
                "bot.handlers.password_generator.edit_tool_photo",
                new=AsyncMock(),
            ),
        ):
            await open_password_generator(callback, state)
        state.update_data.assert_awaited_once_with(password_settings=saved)

    async def test_fake_data_reopens_with_saved_country_and_count(self) -> None:
        callback = SimpleNamespace(from_user=SimpleNamespace(id=42))
        state = SimpleNamespace(update_data=AsyncMock())
        with (
            patch(
                "bot.handlers.fake_data_generator._load_fake_preferences",
                new=AsyncMock(return_value={"country": "de", "count": 5}),
            ),
            patch(
                "bot.handlers.fake_data_generator.edit_tool_photo",
                new=AsyncMock(),
            ) as edit_panel,
        ):
            await open_fake_data(callback, state)
        state.update_data.assert_awaited_once_with(fake_country="de", fake_count=5)
        markup = edit_panel.await_args.kwargs["reply_markup"]
        selected = [
            button
            for row in markup.inline_keyboard
            for button in row
            if button.style == "success"
        ]
        self.assertEqual([button.text for button in selected], ["Германия"])


if __name__ == "__main__":
    unittest.main()
