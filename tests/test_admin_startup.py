import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot import main as bot_main
from bot.config import Settings
from bot.middlewares import AdminAccessMiddleware, LanguageMiddleware, StatisticsMiddleware


class AdminStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_runs_before_polling_and_access_guard_is_first(self) -> None:
        dispatcher = MagicMock()
        dispatcher.start_polling = AsyncMock()
        events = []
        async def cleanup():
            events.append("cleanup")
            return 2
        def make_bot(**kwargs):
            events.append("bot")
            return MagicMock()
        with patch.object(bot_main, "prune_non_admin_data", side_effect=cleanup), \
             patch.object(bot_main, "Bot", side_effect=make_bot), \
             patch.object(bot_main, "Dispatcher", return_value=dispatcher), \
             patch.object(bot_main, "settings", Settings("test-token", frozenset({42}))), \
             patch.object(bot_main.logging, "info"):
            await bot_main.run_bot()
        self.assertEqual(events, ["cleanup", "bot"])
        for observer in (dispatcher.message, dispatcher.callback_query):
            middlewares = [type(call.args[0]) for call in observer.outer_middleware.call_args_list]
            self.assertEqual(middlewares, [AdminAccessMiddleware, StatisticsMiddleware, LanguageMiddleware])
        dispatcher.start_polling.assert_awaited_once()

    async def test_failed_cleanup_prevents_bot_startup(self) -> None:
        with patch.object(bot_main, "prune_non_admin_data", AsyncMock(side_effect=RuntimeError("corrupt file"))), \
             patch.object(bot_main, "Bot") as bot:
            with self.assertRaises(RuntimeError):
                await bot_main.run_bot()
        bot.assert_not_called()
