from collections import Counter
from time import monotonic

from aiogram.types import CallbackQuery, Message


TOOL_LABELS = {
    "json": "JSON", "password": "Пароли / Passwords", "color": "Цвета / Colors",
    "file": "Файлы / Files", "qr": "QR", "fake_data": "Тестовые данные / Fake data",
    "code_screenshot": "Скриншоты кода / Code screenshots", "shortener": "Ссылки / Links",
    "pdf": "PDF", "text_tools": "Текст / Text",
}


class Statistics:
    """Aggregate counters only: no user IDs, texts or persistent storage."""

    def __init__(self) -> None:
        self.started_at = monotonic()
        self.messages = 0
        self.callbacks = 0
        self.errors = 0
        self.rejected_requests = 0
        self.tool_opens: Counter[str] = Counter()

    def record(self, event: Message | CallbackQuery) -> None:
        if isinstance(event, Message):
            self.messages += 1
        else:
            self.callbacks += 1
            action = (event.data or "").removeprefix("menu:")
            if (event.data or "").startswith("menu:") and action in TOOL_LABELS:
                self.tool_opens[action] += 1

    def snapshot(self) -> dict:
        return {
            "uptime_seconds": int(monotonic() - self.started_at),
            "messages": self.messages, "callbacks": self.callbacks, "errors": self.errors,
            "rejected_requests": self.rejected_requests,
            "tool_opens": dict(self.tool_opens),
        }


statistics = Statistics()
