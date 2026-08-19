import unittest
from unittest.mock import patch

from bot import main as bot_main


class MainShutdownTests(unittest.TestCase):
    def test_keyboard_interrupt_is_handled_without_traceback(self) -> None:
        def interrupt(coroutine):
            coroutine.close()
            raise KeyboardInterrupt

        with patch.object(bot_main.asyncio, "run", side_effect=interrupt):
            bot_main.main()


if __name__ == "__main__":
    unittest.main()
