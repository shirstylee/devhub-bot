from bot.middlewares.language import LanguageMiddleware
from bot.middlewares.admin_access import AdminAccessMiddleware
from bot.middlewares.statistics import StatisticsMiddleware

__all__ = ["AdminAccessMiddleware", "LanguageMiddleware", "StatisticsMiddleware"]
