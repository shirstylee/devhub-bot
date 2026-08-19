import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.handlers import setup_routers
from bot.middlewares import LanguageMiddleware


async def run_bot() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    language_middleware = LanguageMiddleware()
    dp.message.outer_middleware(language_middleware)
    dp.callback_query.outer_middleware(language_middleware)
    dp.include_routers(*setup_routers())

    logging.info("Bot started")
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logging.info("Bot shutdown requested")
        raise


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user")
