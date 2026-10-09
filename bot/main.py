import asyncio
from contextlib import suppress
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import setup_routers
from bot.middlewares import (
    AdminAccessMiddleware,
    AntiSpamMiddleware,
    HeavyRequestMiddleware,
    LanguageMiddleware,
    StatisticsMiddleware,
)
from bot.services.anti_spam import AntiSpamLimiter
from bot.services.privacy import prune_non_admin_data


async def poll_bot(dp: Dispatcher, bot: Bot) -> None:
    # On Windows Ctrl+C cancels the asyncio runner's main task. Keep aiogram's
    # polling runner alive long enough to cancel its request before closing HTTP.
    polling = asyncio.create_task(dp.start_polling(bot), name="telegram-polling")
    try:
        await asyncio.shield(polling)
    except asyncio.CancelledError:
        logging.info("Bot shutdown requested")
        # Let a just-created polling task enter its startup before stopping it.
        await asyncio.sleep(0)
        if not polling.done():
            try:
                await dp.stop_polling()
            except RuntimeError as exc:
                if str(exc) != "Polling is not started":
                    raise
                polling.cancel()
        with suppress(asyncio.CancelledError):
            await polling
        raise


async def run_bot() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    removed = await prune_non_admin_data()
    if removed:
        logging.info("Removed %s non-admin records from local storage", removed)
    if not settings.admin_ids:
        logging.warning("ADMIN_IDS is empty: no primary administrator is configured")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    limiter = AntiSpamLimiter()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(AdminAccessMiddleware())
        observer.outer_middleware(AntiSpamMiddleware(limiter))
        observer.outer_middleware(StatisticsMiddleware())
        observer.middleware(HeavyRequestMiddleware(limiter))
    language_middleware = LanguageMiddleware()
    dp.message.outer_middleware(language_middleware)
    dp.callback_query.outer_middleware(language_middleware)
    dp.include_routers(*setup_routers())

    logging.info("Bot started")
    await poll_bot(dp, bot)


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user")
