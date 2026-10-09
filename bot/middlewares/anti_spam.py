from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.i18n import tr
from bot.services.administrators import administrator_store
from bot.services.anti_spam import AntiSpamLimiter, Rejection
from bot.services.language import get_telegram_language
from bot.services.statistics import statistics


async def notify_rejection(event: Message | CallbackQuery, rejection: Rejection, max_upload_bytes: int) -> None:
    statistics.rejected_requests += 1
    if not rejection.notify:
        return
    lang = get_telegram_language(event.from_user.language_code if event.from_user else None)
    if rejection.reason == "upload":
        size = max_upload_bytes // (1024 * 1024)
        text = tr(lang, f"Файл слишком большой. Максимум: {size} МиБ.", f"File is too large. Maximum: {size} MiB.")
    elif rejection.reason == "busy":
        text = tr(lang, "⏳ Предыдущий запрос ещё обрабатывается. Дождитесь результата.",
                  "⏳ Your previous request is still running. Please wait for the result.")
    elif rejection.reason == "capacity":
        text = tr(lang, "⏳ Бот сейчас занят. Попробуйте немного позже.", "⏳ The bot is busy. Please try again shortly.")
    else:
        seconds = rejection.retry_after
        text = tr(lang, f"⏳ Слишком частые запросы. Попробуйте через {seconds} сек.",
                  f"⏳ Too many requests. Try again in {seconds} sec.")
    try:
        if isinstance(event, CallbackQuery):
            await event.answer(text=text)
        else:
            await event.answer(text)
    except TelegramAPIError:
        # Best-effort warning: stale callbacks, blocked chats and Telegram flood
        # control must not create retries or an error-log storm of their own.
        pass


def upload_size(event: Message) -> int:
    sizes = [photo.file_size or 0 for photo in event.photo or []]
    for field in ("document", "video", "animation", "audio", "voice", "video_note", "sticker"):
        media = getattr(event, field, None)
        if media is not None:
            sizes.append(media.file_size or 0)
    return max(sizes, default=0)


class AntiSpamMiddleware(BaseMiddleware):
    """Outer guard shared by messages and callbacks, before language or tool work."""

    def __init__(self, limiter: AntiSpamLimiter) -> None:
        self.limiter = limiter

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)) or event.from_user is None:
            return await handler(event, data)
        user_id = event.from_user.id
        if administrator_store.is_admin(user_id):
            data["anti_spam_guest"] = False
            return await handler(event, data)
        rejection = self.limiter.begin(user_id)
        if rejection is not None:
            await notify_rejection(event, rejection, self.limiter.policy.max_upload_bytes)
            return None
        try:
            data["anti_spam_guest"] = True
            if isinstance(event, Message) and upload_size(event) > self.limiter.policy.max_upload_bytes:
                rejection = self.limiter.reject(user_id, "upload")
                await notify_rejection(event, rejection, self.limiter.policy.max_upload_bytes)
                return None
            return await handler(event, data)
        finally:
            self.limiter.finish(user_id)


class HeavyRequestMiddleware(BaseMiddleware):
    """Inner guard: reserve a slot only after a heavy handler actually matches."""

    def __init__(self, limiter: AntiSpamLimiter) -> None:
        self.limiter = limiter

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, data: dict[str, Any],
    ) -> Any:
        heavy = get_flag(data, "heavy")
        if (not heavy or not data.get("anti_spam_guest") or not isinstance(event, (Message, CallbackQuery))
                or event.from_user is None or administrator_store.is_admin(event.from_user.id)):
            return await handler(event, data)
        rejection = self.limiter.begin_heavy(event.from_user.id, cooldown=heavy != "upload")
        if rejection is not None:
            await notify_rejection(event, rejection, self.limiter.policy.max_upload_bytes)
            return None
        try:
            return await handler(event, data)
        finally:
            self.limiter.finish_heavy()
