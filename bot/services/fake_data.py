import json
import random
from datetime import date, timedelta

from bot.utils.premium_emoji import PROFILE


COUNTRIES: dict[str, dict[str, list[str] | str]] = {
    "ru": {
        "locale": "ru_RU",
        "first_names": ["Алексей", "Егор", "Максим", "Анна", "Мария", "София"],
        "last_names": ["Иванов", "Петров", "Смирнова", "Кузнецова", "Волков", "Морозова"],
        "cities": ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск"],
        "streets": ["Тверская", "Ленина", "Садовая", "Пушкина", "Мира"],
        "phone_prefix": "+7",
        "domain": "example.ru",
        "currency": "RUB",
    },
    "us": {
        "locale": "en_US",
        "first_names": ["James", "John", "Robert", "Emily", "Olivia", "Emma"],
        "last_names": ["Smith", "Johnson", "Brown", "Davis", "Miller", "Wilson"],
        "cities": ["New York", "Austin", "Seattle", "Denver", "Boston"],
        "streets": ["Main St", "Market St", "Oak Ave", "Sunset Blvd", "Broadway"],
        "phone_prefix": "+1",
        "domain": "example.com",
        "currency": "USD",
    },
    "de": {
        "locale": "de_DE",
        "first_names": ["Lukas", "Felix", "Jonas", "Mia", "Emma", "Hannah"],
        "last_names": ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Wagner"],
        "cities": ["Berlin", "Munich", "Hamburg", "Cologne", "Dresden"],
        "streets": ["Hauptstrasse", "Bahnhofstrasse", "Gartenweg", "Schulstrasse", "Ringstrasse"],
        "phone_prefix": "+49",
        "domain": "example.de",
        "currency": "EUR",
    },
    "fr": {
        "locale": "fr_FR",
        "first_names": ["Lucas", "Louis", "Hugo", "Emma", "Jade", "Louise"],
        "last_names": ["Martin", "Bernard", "Thomas", "Petit", "Robert", "Moreau"],
        "cities": ["Paris", "Lyon", "Marseille", "Nice", "Toulouse"],
        "streets": ["Rue Victor Hugo", "Rue Nationale", "Avenue Jean Jaures", "Rue de la Paix"],
        "phone_prefix": "+33",
        "domain": "example.fr",
        "currency": "EUR",
    },
    "gb": {
        "locale": "en_GB",
        "first_names": ["Oliver", "George", "Harry", "Amelia", "Isla", "Ava"],
        "last_names": ["Smith", "Jones", "Taylor", "Brown", "Williams", "Evans"],
        "cities": ["London", "Manchester", "Bristol", "Leeds", "Liverpool"],
        "streets": ["High Street", "Station Road", "Church Lane", "Victoria Road", "King Street"],
        "phone_prefix": "+44",
        "domain": "example.co.uk",
        "currency": "GBP",
    },
}


def generate_fake_records(country: str, kind: str, count: int, lang: str = "ru") -> list[dict[str, str]]:
    if country not in COUNTRIES:
        raise ValueError("Неизвестная страна.")
    count = max(1, min(count, 5))
    return [_generate_record(country, kind, lang) for _ in range(count)]


def records_to_json(records: list[dict[str, str]]) -> str:
    return json.dumps(records, ensure_ascii=False, indent=4)


def records_to_message(records: list[dict[str, str]], lang: str = "ru") -> str:
    chunks: list[str] = []
    for index, record in enumerate(records, start=1):
        fields = "\n".join(f"<b>{key}</b>: <code>{value}</code>" for key, value in record.items())
        heading = "Record" if lang == "en" else "Запись"
        chunks.append(f"{PROFILE.html} <b>{heading} {index}</b>\n{fields}")
    return "\n\n".join(chunks)


def _generate_record(country: str, kind: str, lang: str) -> dict[str, str]:
    base = COUNTRIES[country]
    first_name = _pick(base, "first_names")
    last_name = _pick(base, "last_names")
    full_name = f"{first_name} {last_name}"
    email = f"{first_name}.{last_name}{random.randint(10, 999)}@{base['domain']}".lower()

    labels = _field_labels(lang)
    person = {
        labels["name"]: full_name,
        labels["birth_date"]: _birth_date(),
        labels["phone"]: _phone(str(base["phone_prefix"])),
        "Email": email,
        labels["address"]: f"{_pick(base, 'streets')}, {random.randint(1, 180)}, {_pick(base, 'cities')}",
    }
    company = {
        labels["company"]: f"{_pick(base, 'last_names')} {_company_suffix(country)}",
        labels["job"]: random.choice(["Backend Developer", "QA Engineer", "Product Manager", "Designer", "Analyst"]),
        labels["tax_id"]: "".join(str(random.randint(0, 9)) for _ in range(10)),
        labels["website"]: f"https://{last_name.lower()}-{random.randint(100, 999)}.{base['domain']}",
        labels["currency"]: str(base["currency"]),
    }
    payment = {
        labels["card"]: f"**** **** **** {random.randint(1000, 9999)}",
        labels["expires"]: f"{random.randint(1, 12):02d}/{random.randint(27, 34)}",
        "IBAN": f"{country.upper()}{random.randint(10, 99)} {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
        labels["balance"]: f"{random.randint(50, 9000)} {base['currency']}",
    }

    if kind == "person":
        return person
    if kind == "company":
        return company
    if kind == "payment":
        return payment
    return person | company | payment


def _field_labels(lang: str) -> dict[str, str]:
    if lang == "en":
        return {
            "name": "Name", "birth_date": "Date of birth", "phone": "Phone", "address": "Address",
            "company": "Company", "job": "Job title", "tax_id": "Tax ID", "website": "Website",
            "currency": "Currency", "card": "Card", "expires": "Expires", "balance": "Balance",
        }
    return {
        "name": "Имя", "birth_date": "Дата рождения", "phone": "Телефон", "address": "Адрес",
        "company": "Компания", "job": "Должность", "tax_id": "ИНН/Tax ID", "website": "Сайт",
        "currency": "Валюта", "card": "Карта", "expires": "Срок", "balance": "Баланс",
    }


def _pick(data: dict[str, list[str] | str], key: str) -> str:
    value = data[key]
    if isinstance(value, list):
        return random.choice(value)
    return value


def _birth_date() -> str:
    start = date.today() - timedelta(days=65 * 365)
    end = date.today() - timedelta(days=18 * 365)
    return (start + timedelta(days=random.randint(0, (end - start).days))).isoformat()


def _phone(prefix: str) -> str:
    return f"{prefix} {random.randint(100, 999)} {random.randint(100, 999)} {random.randint(10, 99)} {random.randint(10, 99)}"


def _company_suffix(country: str) -> str:
    return {"ru": "ООО", "us": "LLC", "de": "GmbH", "fr": "SARL", "gb": "Ltd"}[country]
