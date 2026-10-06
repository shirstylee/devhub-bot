from dataclasses import dataclass
from os import getenv
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = BASE_DIR / "bot" / "temp"

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int] = frozenset()

    @property
    def token(self) -> str:
        return self.bot_token


def get_settings() -> Settings:
    token = getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Add it to .env before starting the bot.")
    admin_ids: set[int] = set()
    for raw_id in getenv("ADMIN_IDS", "").split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        if not raw_id.isascii() or not raw_id.isdigit() or not 0 < int(raw_id) < 2**52:
            raise RuntimeError("ADMIN_IDS must contain positive Telegram user IDs separated by commas.")
        admin_ids.add(int(raw_id))
    return Settings(bot_token=token, admin_ids=frozenset(admin_ids))


settings = get_settings()
