from bot.middlewares.language import LanguageMiddleware
from bot.middlewares.admin_access import AdminAccessMiddleware
from bot.middlewares.statistics import StatisticsMiddleware
from bot.middlewares.anti_spam import AntiSpamMiddleware, HeavyRequestMiddleware

__all__ = [
    "AdminAccessMiddleware",
    "AntiSpamMiddleware",
    "HeavyRequestMiddleware",
    "LanguageMiddleware",
    "StatisticsMiddleware",
]
