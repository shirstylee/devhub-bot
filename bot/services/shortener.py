import aiohttp
from urllib.parse import quote_plus


async def shorten_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    api_url = f"https://clck.ru/--?url={quote_plus(cleaned)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=12)) as response:
            if response.status != 200:
                raise ValueError("Сервис сокращения ссылок временно недоступен.")
            result = (await response.text()).strip()
    if not result.startswith(("http://", "https://")):
        raise ValueError("Не удалось сократить ссылку.")
    return result
