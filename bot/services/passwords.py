import secrets
import string


DEFAULT_PASSWORD_SETTINGS: dict[str, bool | int] = {
    "length": 16,
    "count": 1,
    "digits": True,
    "symbols": True,
    "uppercase": True,
    "lowercase": True,
}


def generate_password(settings: dict[str, bool | int]) -> str:
    length = int(settings["length"])
    pools: list[str] = []

    if settings["digits"]:
        pools.append(string.digits)
    if settings["symbols"]:
        pools.append("!@#$%^&*()-_=+[]{};:,.?/|")
    if settings["uppercase"]:
        pools.append(string.ascii_uppercase)
    if settings["lowercase"]:
        pools.append(string.ascii_lowercase)

    if not pools:
        raise ValueError("Выберите хотя бы один набор символов.")
    if length < len(pools):
        raise ValueError("Длина слишком маленькая для выбранных настроек.")

    # Гарантируем, что каждый выбранный набор символов попадет в пароль.
    chars = [secrets.choice(pool) for pool in pools]
    alphabet = "".join(pools)
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def generate_passwords(settings: dict[str, bool | int]) -> list[str]:
    count = max(1, min(int(settings.get("count", 1)), 10))
    return [generate_password(settings) for _ in range(count)]


def copy_settings(settings: dict[str, bool | int] | None = None) -> dict[str, bool | int]:
    return dict(settings or DEFAULT_PASSWORD_SETTINGS)
