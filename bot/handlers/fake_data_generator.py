from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards.fake_data import COUNTRY_LABELS, fake_country_keyboard, fake_settings_keyboard
from bot.i18n import tr
from bot.services.fake_data import generate_fake_records, records_to_json, records_to_message
from bot.services.user_preferences import user_preferences_store
from bot.states import FakeDataStates
from bot.utils.messages import (
    answer_callback,
    delete_user_message,
    edit_message_text,
    edit_stored_panel,
    edit_tool_photo,
    remember_panel,
)
from bot.utils.premium_emoji import ERROR, PEOPLE, SUCCESS

router = Router(name="fake_data_generator")
DEFAULT_FAKE_PREFERENCES = {"country": "ru", "count": 1}


@router.callback_query(F.data == "menu:fake_data")
async def open_fake_data(callback: CallbackQuery, state: FSMContext, lang: str = "ru") -> None:
    settings = await _load_fake_preferences(callback.from_user.id)
    await state.update_data(fake_country=settings["country"], fake_count=settings["count"])
    await edit_tool_photo(
        callback,
        "fake",
        f"{PEOPLE.html} <b>{tr(lang, 'Генератор фейковых данных', 'Fake data generator')}</b>\n\n"
        + tr(lang, "Выберите страну. Данные подходят для тестов, моков и демо.", "Choose a country. The data is suitable for tests, mocks, and demos."),
        reply_markup=fake_country_keyboard(settings["country"], lang),
    )


@router.callback_query(F.data == "fake:country_menu")
async def show_country_menu(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    country, _ = await _fake_settings_from_state(state, callback.from_user.id)
    await edit_message_text(callback, tr(lang, "Выберите страну:", "Choose a country:"), reply_markup=fake_country_keyboard(country, lang))


@router.callback_query(F.data.startswith("fake:country:"))
async def choose_country(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    country = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    if country not in COUNTRY_LABELS:
        await answer_callback(callback)
        return
    _, count = await _fake_settings_from_state(state, callback.from_user.id)
    await _save_fake_preferences(callback.from_user.id, state, country, count)
    await edit_message_text(
        callback,
        tr(lang, "Настройте количество и тип данных:", "Choose the amount and data type:"),
        reply_markup=fake_settings_keyboard(country, count, lang),
    )


@router.callback_query(F.data == "fake:count:input")
async def ask_fake_count(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await remember_panel(callback, state, "fake")
    await state.set_state(FakeDataStates.waiting_count)
    await edit_message_text(callback, tr(lang, "Введите количество записей числом от 1 до 5.", "Enter the number of records from 1 to 5."))


@router.callback_query(F.data.in_({"fake:count:up", "fake:count:down"}))
async def change_count(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    country, count = await _fake_settings_from_state(state, callback.from_user.id)
    previous_count = count
    if callback.data == "fake:count:up":
        count = min(count + 1, 5)
    else:
        count = max(count - 1, 1)
    if count == previous_count:
        await answer_callback(callback)
        return
    await answer_callback(callback)
    await _save_fake_preferences(callback.from_user.id, state, country, count)
    try:
        await callback.message.edit_reply_markup(reply_markup=fake_settings_keyboard(country, count, lang))
    except TelegramBadRequest as exc:
        if "message is not modified" not in exc.message:
            raise


@router.message(FakeDataStates.waiting_count, F.text)
async def set_fake_count(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    country = data.get("fake_country", "ru")
    try:
        count = int(message.text or "")
    except ValueError:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {tr(lang, 'Введите число от 1 до 5.', 'Enter a number from 1 to 5.')}",
            reply_markup=fake_settings_keyboard(country, int(data.get("fake_count", 1)), lang),
        )
        return
    if count < 1 or count > 5:
        await edit_stored_panel(
            message,
            state,
            f"{ERROR.html} {tr(lang, 'Количество должно быть от 1 до 5.', 'Count must be between 1 and 5.')}",
            reply_markup=fake_settings_keyboard(country, int(data.get("fake_count", 1)), lang),
        )
        return
    await _save_fake_preferences(message.from_user.id, state, country, count)
    await state.set_state(None)
    await delete_user_message(message)
    await edit_stored_panel(
        message,
        state,
        f"{SUCCESS.html} {tr(lang, 'Количество обновлено.', 'Count updated.')}",
        reply_markup=fake_settings_keyboard(country, count, lang),
    )


@router.callback_query(F.data == "fake:noop")
async def noop(callback: CallbackQuery) -> None:
    await answer_callback(callback)


@router.callback_query(F.data.startswith("fake:generate:"))
async def generate_fake_data(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    country, count = await _fake_settings_from_state(state, callback.from_user.id)
    kind = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    records = generate_fake_records(country, kind, count, lang)
    message_text = records_to_message(records, lang)
    keyboard = fake_settings_keyboard(country, count, lang)

    if len(message_text) <= 3500:
        await edit_message_text(callback, message_text, reply_markup=keyboard)
    else:
        await callback.message.answer_document(
            document=BufferedInputFile(records_to_json(records).encode("utf-8"), filename="fake-data.json"),
            caption=f"{SUCCESS.html} {tr(lang, 'Фейковые данные готовы.', 'Fake data is ready.')}",
            reply_markup=keyboard,
        )
        await answer_callback(callback)


async def _load_fake_preferences(user_id: int) -> dict[str, str | int]:
    raw = await user_preferences_store.load_section(
        user_id,
        "fake_data",
        DEFAULT_FAKE_PREFERENCES,
    )
    country = str(raw.get("country", "ru"))
    if country not in COUNTRY_LABELS:
        country = "ru"
    try:
        count = max(1, min(5, int(raw.get("count", 1))))
    except (TypeError, ValueError):
        count = 1
    return {"country": country, "count": count}


async def _save_fake_preferences(
    user_id: int,
    state: FSMContext,
    country: str,
    count: int,
) -> None:
    await state.update_data(fake_country=country, fake_count=count)
    await user_preferences_store.save_section(
        user_id,
        "fake_data",
        {"country": country, "count": count},
    )


async def _fake_settings_from_state(state: FSMContext, user_id: int) -> tuple[str, int]:
    data = await state.get_data()
    if data.get("fake_country") in COUNTRY_LABELS:
        try:
            count = max(1, min(5, int(data.get("fake_count", 1))))
        except (TypeError, ValueError):
            count = 1
        return str(data["fake_country"]), count
    settings = await _load_fake_preferences(user_id)
    await state.update_data(
        fake_country=settings["country"],
        fake_count=settings["count"],
    )
    return str(settings["country"]), int(settings["count"])
