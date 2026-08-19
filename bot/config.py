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

    @property
    def token(self) -> str:
        return self.bot_token


def get_settings() -> Settings:
    token = getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Add it to .env before starting the bot.")
    return Settings(bot_token=token)


settings = get_settings()
