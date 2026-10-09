from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards.main_menu import back_keyboard
from bot.i18n import tr
from bot.keyboards.qr import qr_tools_keyboard
from bot.services.qr import build_phone_payload, build_telegram_payload, build_wifi_payload, create_qr_image, scan_qr_image
from bot.states import QrStates
from bot.utils.temp_files import cleanup_paths, make_temp_path
from bot.utils.messages import edit_message_text, edit_tool_photo
from bot.utils.premium_emoji import ERROR, LINK, SUCCESS

router = Router(name="qr_tools")


@router.callback_query(F.data == "menu:qr")
async def open_qr_tools(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await edit_tool_photo(callback, "qr", f"{LINK.html} <b>{tr(lang, 'QR-инструменты', 'QR tools')}</b>\n\n{tr(lang, 'Генерация и сканирование:', 'Create and scan codes:')}", reply_markup=qr_tools_keyboard(lang))


@router.callback_query(F.data == "qr:text")
async def ask_qr_text(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(QrStates.waiting_text)
    await edit_message_text(callback, tr(lang, "Отправьте текст или ссылку для QR-кода.", "Send text or a link for the QR code."), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "qr:wifi")
async def ask_wifi_ssid(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(QrStates.waiting_wifi_ssid)
    await edit_message_text(callback, tr(lang, "Введите имя WiFi сети (SSID).", "Enter the Wi-Fi network name (SSID)."), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "qr:phone")
async def ask_phone(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(QrStates.waiting_phone)
    await edit_message_text(callback, tr(lang, "Введите номер телефона.", "Enter a phone number."), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "qr:telegram")
async def ask_telegram(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(QrStates.waiting_username)
    await edit_message_text(callback, tr(lang, "Введите Telegram username, например: <code>@durov</code>", "Enter a Telegram username, for example: <code>@durov</code>"), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "qr:scan")
async def ask_qr_photo(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(QrStates.waiting_photo)
    await edit_message_text(callback, tr(lang, "Отправьте фото с QR-кодом.", "Send a photo containing a QR code."), reply_markup=back_keyboard(lang))


@router.message(QrStates.waiting_text, F.text, flags={"heavy": True})
async def handle_qr_text(message: Message, lang: str) -> None:
    await _send_qr(message, message.text or "", f"{SUCCESS.html} {tr(lang, 'QR-код готов.', 'QR code created.')}", lang)


@router.message(QrStates.waiting_wifi_ssid, F.text)
async def handle_wifi_ssid(message: Message, state: FSMContext, lang: str) -> None:
    await state.update_data(wifi_ssid=message.text or "")
    await state.set_state(QrStates.waiting_wifi_password)
    await message.answer(tr(lang, "Введите пароль WiFi.", "Enter the Wi-Fi password."), reply_markup=back_keyboard(lang))


@router.message(QrStates.waiting_wifi_password, F.text, flags={"heavy": True})
async def handle_wifi_password(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    payload = build_wifi_payload(data.get("wifi_ssid", ""), message.text or "")
    await _send_qr(message, payload, f"{SUCCESS.html} {tr(lang, 'QR-код WiFi готов.', 'Wi-Fi QR code created.')}", lang)


@router.message(QrStates.waiting_phone, F.text, flags={"heavy": True})
async def handle_phone(message: Message, lang: str) -> None:
    payload = build_phone_payload(message.text or "")
    await _send_qr(message, payload, f"{SUCCESS.html} {tr(lang, 'QR-код телефона готов.', 'Phone QR code created.')}", lang)


@router.message(QrStates.waiting_username, F.text, flags={"heavy": True})
async def handle_telegram(message: Message, lang: str) -> None:
    payload = build_telegram_payload(message.text or "")
    await _send_qr(message, payload, f"{SUCCESS.html} {tr(lang, 'QR-код Telegram готов.', 'Telegram QR code created.')}", lang)


@router.message(QrStates.waiting_photo, F.photo | F.document, flags={"heavy": True})
async def scan_qr(message: Message, lang: str) -> None:
    input_path: Path = make_temp_path(".png")
    try:
        if message.photo:
            await message.bot.download(message.photo[-1].file_id, destination=input_path)
        elif message.document:
            await message.bot.download(message.document.file_id, destination=input_path)
        else:
            await message.answer(f"{ERROR.html} {tr(lang, 'Отправьте фото с QR-кодом.', 'Send a photo containing a QR code.')}", reply_markup=back_keyboard(lang))
            return

        result = scan_qr_image(input_path)
        await message.answer(f"{SUCCESS.html} <b>{tr(lang, 'QR распознан', 'QR code recognized')}</b>\n\n<code>{result}</code>", reply_markup=qr_tools_keyboard(lang))
    except ValueError as exc:
        error = tr(lang, str(exc), "Could not read a QR code from this image.")
        await message.answer(f"{ERROR.html} {error}", reply_markup=back_keyboard(lang))
    finally:
        cleanup_paths(input_path)


async def _send_qr(message: Message, payload: str, caption: str, lang: str) -> None:
    if not payload.strip():
        await message.answer(f"{ERROR.html} {tr(lang, 'Текст не должен быть пустым.', 'Text cannot be empty.')}", reply_markup=back_keyboard(lang))
        return

    image_path: Path = make_temp_path(".png")
    create_qr_image(payload, image_path)
    try:
        await message.answer_photo(photo=FSInputFile(image_path), caption=caption, reply_markup=qr_tools_keyboard(lang))
    finally:
        cleanup_paths(image_path)
