import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe, GetUpdates
from aiogram.types import User

from bot import main as bot_main


class MainShutdownTests(unittest.TestCase):
    def test_keyboard_interrupt_is_handled_without_traceback(self) -> None:
        def interrupt(coroutine):
            coroutine.close()
            raise KeyboardInterrupt

        with patch.object(bot_main.asyncio, "run", side_effect=interrupt):
            bot_main.main()


class PollingShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_completion_does_not_request_stop(self) -> None:
        dp = MagicMock(start_polling=AsyncMock(), stop_polling=AsyncMock())
        await bot_main.poll_bot(dp, MagicMock())
        dp.start_polling.assert_awaited_once()
        dp.stop_polling.assert_not_awaited()

    async def test_polling_errors_are_not_swallowed(self) -> None:
        dp = MagicMock(start_polling=AsyncMock(side_effect=RuntimeError("startup error")), stop_polling=AsyncMock())
        with self.assertRaisesRegex(RuntimeError, "startup error"):
            await bot_main.poll_bot(dp, MagicMock())
        dp.stop_polling.assert_not_awaited()

    async def exercise_real_dispatcher_shutdown(self, fail_first_request: bool = False) -> list[logging.LogRecord]:
        started = asyncio.Event()
        events = []
        active_request = False
        pending_response = None
        request_count = 0

        async def request(bot, method, **kwargs):
            nonlocal active_request, pending_response, request_count
            if isinstance(method, GetMe):
                return User(id=123456, is_bot=True, first_name="Test bot", username="test_bot")
            if isinstance(method, GetUpdates):
                request_count += 1
                if fail_first_request and request_count == 1:
                    raise TelegramNetworkError(method=method, message="real network failure")
                active_request = True
                pending_response = asyncio.get_running_loop().create_future()
                started.set()
                try:
                    return await pending_response
                finally:
                    active_request = False
                    events.append("request stopped")
            raise AssertionError(f"Unexpected method: {type(method).__name__}")

        async def close_session():
            events.append("HTTP closed")
            # Reproduce the reported disconnect if the HTTP session is closed too soon.
            if active_request and pending_response is not None and not pending_response.done():
                pending_response.set_exception(TelegramNetworkError(method=GetUpdates(), message="Server disconnected"))
                await asyncio.sleep(0)

        bot = Bot(token="123456:testing-token")
        bot.session = AsyncMock(side_effect=request)
        bot.session.timeout = 60
        bot.session.close.side_effect = close_session
        dp = Dispatcher()
        with self.assertLogs("aiogram.dispatcher", level="INFO") as captured, \
             patch("aiogram.utils.backoff.Backoff.asleep", AsyncMock()):
            polling = asyncio.create_task(bot_main.poll_bot(dp, bot))
            try:
                await asyncio.wait_for(started.wait(), 2)
                polling.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(polling, 2)
            finally:
                if not polling.done():
                    polling.cancel()
                    await asyncio.gather(polling, return_exceptions=True)
        self.assertEqual(events, ["request stopped", "HTTP closed"])
        bot.session.close.assert_awaited_once()
        self.assertTrue(dp._stopped_signal.is_set())
        return captured.records

    async def test_ctrl_c_cancellation_stops_request_before_closing_http(self) -> None:
        records = await self.exercise_real_dispatcher_shutdown()
        self.assertFalse(any(record.levelno >= logging.WARNING for record in records))
        self.assertTrue(any("Polling stopped" in record.getMessage() for record in records))

    async def test_real_network_errors_remain_visible_before_shutdown(self) -> None:
        records = await self.exercise_real_dispatcher_shutdown(fail_first_request=True)
        errors = [record for record in records if record.levelno >= logging.ERROR]
        self.assertEqual(len(errors), 1)
        self.assertIn("real network failure", errors[0].getMessage())


if __name__ == "__main__":
    unittest.main()
