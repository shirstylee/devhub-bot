import re
import unittest

from bot.keyboards.code_screenshot import code_settings_keyboard
from bot.keyboards.color import color_tools_keyboard
from bot.keyboards.emoji_renderer import renderer_main_keyboard
from bot.keyboards.fake_data import fake_settings_keyboard
from bot.keyboards.file import file_actions_keyboard
from bot.keyboards.language import language_keyboard
from bot.keyboards.main_menu import back_keyboard, main_menu_keyboard
from bot.keyboards.password import password_settings_keyboard
from bot.keyboards.pdf import pdf_tools_keyboard
from bot.keyboards.qr import qr_tools_keyboard
from bot.keyboards.recolor import recolor_result_keyboard
from bot.keyboards.shortener import shortener_keyboard
from bot.keyboards.text_tools import text_tools_keyboard
from bot.services.render_models import RenderSettings
from bot.utils.premium_emoji import BACK, BRUSH, IMAGE, SETTINGS, SUCCESS


EMOJI_PATTERN = re.compile(r"[\U0001F000-\U0001FAFF\u2300-\u27FF]")


class PremiumEmojiTests(unittest.TestCase):
    def test_html_markup_uses_the_provided_custom_emoji_id(self) -> None:
        self.assertEqual(
            SETTINGS.html,
            '<tg-emoji emoji-id="5904258298764334001">⚙️</tg-emoji>',
        )

    def test_selected_state_uses_single_checkmark(self) -> None:
        self.assertEqual(SUCCESS.emoji_id, "5774022692642492953")

    def test_code_summary_buttons_have_premium_icons(self) -> None:
        keyboard = code_settings_keyboard("dracula_pro", "python", "navy")
        summary_buttons = keyboard.inline_keyboard[3]
        self.assertEqual(summary_buttons[0].icon_custom_emoji_id, BRUSH.emoji_id)
        self.assertEqual(summary_buttons[1].icon_custom_emoji_id, IMAGE.emoji_id)

    def test_interface_buttons_do_not_duplicate_plain_emoji(self) -> None:
        password_settings = {
            "length": 16,
            "count": 1,
            "digits": True,
            "symbols": False,
            "uppercase": True,
            "lowercase": True,
        }
        keyboards = (
            main_menu_keyboard(),
            main_menu_keyboard("en"),
            back_keyboard(),
            language_keyboard(),
            text_tools_keyboard(),
            color_tools_keyboard(),
            code_settings_keyboard(),
            renderer_main_keyboard(RenderSettings(), has_source=True),
            fake_settings_keyboard("ru", 1),
            file_actions_keyboard(),
            password_settings_keyboard(password_settings),
            pdf_tools_keyboard(),
            qr_tools_keyboard(),
            recolor_result_keyboard(),
            shortener_keyboard("https://example.com"),
        )

        for keyboard in keyboards:
            for row in keyboard.inline_keyboard:
                for button in row:
                    self.assertIsNone(
                        EMOJI_PATTERN.search(button.text.replace(BACK, "")),
                        msg=f"Обычный эмодзи остался в кнопке: {button.text}",
                    )


if __name__ == "__main__":
    unittest.main()
