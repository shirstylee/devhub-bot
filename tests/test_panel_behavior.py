import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.emoji_renderer import (
    PACK_PATTERN,
    _accept_and_home,
    _edit_panel,
    _ensure_background_in_state,
    _home_text,
    _settings_with_section_default,
    _source_from_message,
    pack_toggle,
    receive_preview_source,
    receive_render_source,
    repeat_history_render,
    render_preview,
    reset_render_defaults,
)
from bot.services.render_models import OutputFormat, RenderSettings, SourceKind, WatermarkPosition
from bot.services.render_history import RenderHistoryEntry
from bot.services.render_models import RenderSource
from bot.states import RenderStates
from bot.utils import messages as message_utils
from bot.utils.premium_emoji import APPS, SETTINGS


class PanelBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def test_section_default_does_not_reset_unrelated_settings(self) -> None:
        settings = RenderSettings(
            background_color="#123456",
            width=1280,
            height=720,
            output_format=OutputFormat.VIDEO,
            emoji_color="#ABCDEF",
            emoji_size=90,
            watermark_text="DevHub",
            watermark_font="Montserrat",
            watermark_color="#112233",
            watermark_position=WatermarkPosition.TOP_LEFT,
            watermark_size=12,
            custom_background_file_id="file-id",
            custom_background_suffix=".png",
            custom_background_label="Фон",
        )

        size_reset = _settings_with_section_default(settings, "emoji_size")
        self.assertEqual(size_reset.emoji_size, 55)
        self.assertEqual(size_reset.background_color, "#123456")
        self.assertEqual(size_reset.watermark_text, "DevHub")

        watermark_reset = _settings_with_section_default(settings, "watermark")
        self.assertIsNone(watermark_reset.watermark_text)
        self.assertEqual(watermark_reset.watermark_font, "Roboto")
        self.assertEqual(watermark_reset.watermark_color, "#FFFFFF")
        self.assertEqual(watermark_reset.watermark_position, WatermarkPosition.BOTTOM_RIGHT)
        self.assertEqual(watermark_reset.watermark_size, 5)
        self.assertEqual(watermark_reset.background_color, "#123456")
        self.assertEqual(watermark_reset.custom_background_file_id, "file-id")

    def test_panel_text_gets_quote_without_double_wrapping(self) -> None:
        decorated = message_utils.decorate_panel_text("🎨 <b>Цвет</b>\n\nВыберите действие")
        self.assertEqual(
            decorated,
            "🎨 <b>Цвет</b>\n\n<blockquote>Выберите действие</blockquote>",
        )
        self.assertEqual(message_utils.decorate_panel_text(decorated), decorated)

        existing = message_utils.decorate_panel_text(
            "🎞 <b>Рендер</b>\n\n<blockquote>Параметры</blockquote>"
        )
        self.assertEqual(
            existing,
            "🎞 <b>Рендер</b>\n\n<blockquote>Параметры</blockquote>",
        )

        multiline = message_utils.decorate_panel_text(
            "<blockquote>Первая строка\nВторая строка</blockquote>"
        )
        self.assertEqual(
            multiline,
            "<blockquote>Первая строка\nВторая строка</blockquote>",
        )

    def test_renderer_home_spacing_matches_requested_layout(self) -> None:
        text = _home_text(RenderSettings())
        self.assertTrue(text.startswith(f"{APPS.html} <b>Рендер</b>\n<blockquote>"))
        self.assertIn(f"</blockquote>\n\n{SETTINGS.html} <b>Конфигурация</b>", text)

    def test_pack_links_and_custom_media_classification(self) -> None:
        self.assertEqual(
            PACK_PATTERN.search("https://t.me/addstickers/DevHubPack").group(1),
            "DevHubPack",
        )
        self.assertEqual(
            PACK_PATTERN.search("t.me/addemoji/DevHubEmoji").group(1),
            "DevHubEmoji",
        )
        message = SimpleNamespace(
            sticker=None,
            photo=[SimpleNamespace(file_id="photo-id")],
            video=None,
            animation=None,
            document=None,
        )
        source = _source_from_message(message, SourceKind.USER_MEDIA, recolorable=False)
        self.assertEqual(source.kind, SourceKind.USER_MEDIA)
        self.assertFalse(source.recolorable)

    async def test_pack_handler_rejects_eleventh_selection(self) -> None:
        callback = SimpleNamespace(
            data="render:pack:toggle:10",
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "render_pack_items": [{} for _ in range(11)],
                    "render_pack_selected": list(range(10)),
                }
            ),
            update_data=AsyncMock(),
        )

        await pack_toggle(callback, state)

        callback.answer.assert_awaited_once_with(
            text="Можно выбрать не больше 10 элементов.",
            show_alert=True,
        )
        state.update_data.assert_not_awaited()

    async def test_same_banner_edits_caption_without_replacing_media(self) -> None:
        panel = SimpleNamespace(
            chat=SimpleNamespace(id=100),
            message_id=200,
            edit_caption=AsyncMock(),
            edit_media=AsyncMock(),
            edit_text=AsyncMock(),
        )
        panel.edit_caption.return_value = panel
        callback = SimpleNamespace(message=panel, answer=AsyncMock())
        message_utils._PANEL_MEDIA_KEYS[(100, 200)] = "main"

        result = await message_utils.edit_tool_photo(callback, "main", "Обновлено")

        self.assertIs(result, panel)
        callback.answer.assert_awaited_once()
        panel.edit_caption.assert_awaited_once()
        panel.edit_media.assert_not_awaited()

    async def test_new_banner_replaces_media_in_existing_message(self) -> None:
        panel = SimpleNamespace(
            chat=SimpleNamespace(id=101),
            message_id=201,
            edit_caption=AsyncMock(),
            edit_media=AsyncMock(),
            edit_text=AsyncMock(),
        )
        panel.edit_media.return_value = panel
        callback = SimpleNamespace(message=panel, answer=AsyncMock())
        message_utils._PANEL_MEDIA_KEYS[(101, 201)] = "main"

        result = await message_utils.edit_tool_photo(callback, "renderer", "Рендер")

        self.assertIs(result, panel)
        panel.edit_media.assert_awaited_once()
        panel.edit_caption.assert_not_awaited()

    async def test_accepted_renderer_input_is_deleted_and_panel_reused(self) -> None:
        message = SimpleNamespace(
            delete=AsyncMock(),
            from_user=SimpleNamespace(id=42),
        )
        state = SimpleNamespace(set_state=AsyncMock())
        with patch(
            "bot.handlers.emoji_renderer._show_home_message",
            new=AsyncMock(),
        ) as show_home:
            await _accept_and_home(message, state)

        message.delete.assert_awaited_once()
        state.set_state.assert_awaited_once_with(RenderStates.ready)
        show_home.assert_awaited_once_with(message, state, 42)

    async def test_preview_waits_for_next_sticker_and_renders_only_preview(self) -> None:
        callback = SimpleNamespace(
            message=SimpleNamespace(),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(set_state=AsyncMock())
        with patch(
            "bot.handlers.emoji_renderer.edit_message_text",
            new=AsyncMock(),
        ) as edit_panel:
            await render_preview(callback, state)
        state.set_state.assert_awaited_once_with(RenderStates.waiting_preview_source)
        self.assertIn("Отправьте эмодзи или стикер", edit_panel.await_args.args[1])

        sticker = SimpleNamespace(
            is_video=False,
            is_animated=False,
            file_id="sticker-id",
            emoji="🐝",
            file_size=1024,
        )
        message = SimpleNamespace(
            sticker=sticker,
            photo=None,
            video=None,
            animation=None,
            document=None,
            entities=None,
            caption_entities=None,
            from_user=SimpleNamespace(id=42),
            delete=AsyncMock(),
        )
        with patch(
            "bot.handlers.emoji_renderer._render_sources",
            new=AsyncMock(),
        ) as render_sources:
            await receive_preview_source(message, state)
        message.delete.assert_awaited_once()
        self.assertTrue(render_sources.await_args.kwargs["preview"])

    async def test_standalone_standard_animated_emoji_is_resolved_from_telegram_set(self) -> None:
        animated_sticker = SimpleNamespace(
            is_video=False,
            is_animated=True,
            file_id="animated-halo-id",
            emoji="😇",
        )
        bot = SimpleNamespace(
            get_sticker_set=AsyncMock(
                return_value=SimpleNamespace(stickers=[animated_sticker])
            )
        )
        message = SimpleNamespace(
            text="😇",
            entities=None,
            caption_entities=None,
            sticker=None,
            photo=None,
            video=None,
            animation=None,
            document=None,
            bot=bot,
            from_user=SimpleNamespace(id=42),
            delete=AsyncMock(),
        )
        state = SimpleNamespace()
        with (
            patch(
                "bot.handlers.emoji_renderer._ANIMATED_EMOJI_SOURCES",
                None,
            ),
            patch(
                "bot.handlers.emoji_renderer._render_sources",
                new=AsyncMock(),
            ) as render_sources,
        ):
            await receive_render_source(message, state)

        bot.get_sticker_set.assert_awaited_once_with("AnimatedEmojies")
        message.delete.assert_awaited_once()
        source = render_sources.await_args.args[2][0]
        self.assertEqual(source.file_id, "animated-halo-id")
        self.assertEqual(source.suffix, ".tgs")
        self.assertEqual(source.kind, SourceKind.CUSTOM_EMOJI)

    async def test_saved_custom_background_is_restored_into_session(self) -> None:
        settings = RenderSettings(
            custom_background_file_id="background-id",
            custom_background_suffix=".mp4",
            custom_background_label="Видео",
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={}),
            update_data=AsyncMock(),
        )
        source = await _ensure_background_in_state(state, settings)
        self.assertIsNotNone(source)
        self.assertEqual(source.file_id, "background-id")
        state.update_data.assert_awaited_once()

    async def test_renderer_private_panel_uses_native_blockquote(self) -> None:
        bot = SimpleNamespace(edit_message_caption=AsyncMock())
        message = SimpleNamespace(bot=bot)
        state = SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "renderer_panel_chat_id": 42,
                    "renderer_panel_message_id": 77,
                }
            )
        )
        await _edit_panel(
            message,
            state,
            "✨ <b>Рендер</b>\n\n<blockquote>Параметры</blockquote>",
            None,
        )
        caption = bot.edit_message_caption.await_args.kwargs["caption"]
        self.assertIn("<blockquote>Параметры</blockquote>", caption)
        self.assertNotIn("🔷", caption)

    async def test_renderer_defaults_clear_all_settings_and_custom_background(self) -> None:
        callback = SimpleNamespace(from_user=SimpleNamespace(id=42))
        state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
        with (
            patch(
                "bot.handlers.emoji_renderer.render_settings_store.save",
                new=AsyncMock(),
            ) as save,
            patch(
                "bot.handlers.emoji_renderer._show_home_callback",
                new=AsyncMock(),
            ) as show_home,
        ):
            await reset_render_defaults(callback, state)

        saved = save.await_args.args[1]
        self.assertEqual(saved, RenderSettings())
        state.update_data.assert_awaited_once_with(render_background_source=None)
        state.set_state.assert_awaited_once_with(RenderStates.ready)
        show_home.assert_awaited_once_with(callback, state)

    async def test_history_repeat_uses_the_saved_snapshot(self) -> None:
        entry = RenderHistoryEntry(
            entry_id="saved-render",
            created_at=datetime.now(UTC).isoformat(),
            settings=RenderSettings(
                width=1280,
                height=720,
                output_format=OutputFormat.VIDEO,
                background_color="#123456",
            ),
            sources=[RenderSource(SourceKind.STICKER, "sticker-id", ".tgs", "⭐", True)],
            background_source=RenderSource(
                SourceKind.USER_MEDIA,
                "background-id",
                ".png",
                "Фон",
            ),
            duration=2.5,
        )
        callback = SimpleNamespace(
            data="render:history:repeat:saved-render",
            message=SimpleNamespace(),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        state = SimpleNamespace()
        with (
            patch(
                "bot.handlers.emoji_renderer.render_history_store.load",
                new=AsyncMock(return_value=[entry]),
            ),
            patch(
                "bot.handlers.emoji_renderer._render_sources",
                new=AsyncMock(),
            ) as render_sources,
        ):
            await repeat_history_render(callback, state)

        callback.answer.assert_awaited_once()
        rendered_source = render_sources.await_args.args[2][0]
        self.assertEqual(rendered_source.file_id, "sticker-id")
        self.assertIsNot(rendered_source, entry.sources[0])
        self.assertIs(render_sources.await_args.kwargs["history_entry"], entry)


if __name__ == "__main__":
    unittest.main()
