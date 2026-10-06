from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main_menu import main_menu_keyboard
from bot.services.administrators import administrator_store
from bot.utils.temp_files import cleanup_paths
from bot.utils.messages import answer_callback, answer_tool_photo, edit_tool_photo
from bot.utils.premium_emoji import BOT, BRUSH, CODE, FILE, LINK, LOCKED, PEOPLE, TEXT

router = Router(name="common")


def build_welcome_text(lang: str) -> str:
    if lang == "en":
        return (
            f"{BOT.html} <b>DevHub Bot</b>\n"
            "<i>Tools for development, files, and test data</i>\n\n"
            f"{CODE.html} <b>Format JSON</b> — validate and pretty-print JSON.\n"
            f"{LOCKED.html} <b>Passwords</b> — configurable secure password generation.\n"
            f"{BRUSH.html} <b>Colors</b> — HEX/RGB conversion, random colors, and previews.\n"
            f"{FILE.html} <b>Files</b> — convert, resize, compress, and archive.\n"
            f"{LINK.html} <b>QR tools</b> — create and scan QR codes.\n"
            f"{PEOPLE.html} <b>Fake Data</b> — people, companies, and payment test data.\n"
            f"{CODE.html} <b>Code Screenshot</b> — Carbon-style PNG images.\n"
            f"{LINK.html} <b>Links</b> — shorten links with clck.ru.\n"
            f"{FILE.html} <b>PDF tools</b> — export pages, build PDFs, and extract images.\n"
            f"{TEXT.html} <b>Text tools</b> — Base64, URL encoding, and secure hashes."
        )
    return (
        f"{BOT.html} <b>DevHub Bot</b>\n"
        "<i>Инструменты для разработки, файлов и тестовых данных</i>\n\n"
        f"{CODE.html} <b>Форматировать JSON</b> — проверка и красивое форматирование.\n"
        f"{LOCKED.html} <b>Пароли</b> — генерация с длиной, количеством и наборами символов.\n"
        f"{BRUSH.html} <b>Цвета</b> — HEX/RGB, случайный цвет и превью.\n"
        f"{FILE.html} <b>Файлы</b> — конвертация, resize, compress и ZIP.\n"
        f"{LINK.html} <b>QR-инструменты</b> — генерация и сканирование QR-кодов.\n"
        f"{PEOPLE.html} <b>Fake Data</b> — тестовые люди, компании и платежные данные.\n"
        f"{CODE.html} <b>Code Screenshot</b> — PNG-скриншот кода в стиле Carbon.\n"
        f"{LINK.html} <b>Links</b> — сокращение ссылок через clck.ru.\n"
        f"{FILE.html} <b>PDF-инструменты</b> — экспорт страниц, сборка PDF и извлечение изображений.\n"
        f"{TEXT.html} <b>Текстовые инструменты</b> — Base64, URL-кодирование и безопасные хеши."
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("file_input_path"), data.get("pdf_input_path"), data.get("pdf_images"))
    await state.clear()
    await answer_tool_photo(message, "main", build_welcome_text(lang), reply_markup=main_menu_keyboard(
        lang, allow_language_choice=bool(message.from_user and administrator_store.is_admin(message.from_user.id))))


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("file_input_path"), data.get("pdf_input_path"), data.get("pdf_images"))
    await state.clear()
    await answer_tool_photo(message, "main", build_welcome_text(lang), reply_markup=main_menu_keyboard(
        lang, allow_language_choice=bool(message.from_user and administrator_store.is_admin(message.from_user.id))))


@router.callback_query(F.data == "menu:back")
async def callback_back_to_menu(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("file_input_path"), data.get("pdf_input_path"), data.get("pdf_images"))
    await state.clear()
    if callback.message:
        if callback.message.sticker:
            await answer_callback(callback)
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await answer_tool_photo(
                callback.message,
                "main",
                build_welcome_text(lang),
                reply_markup=main_menu_keyboard(lang, allow_language_choice=administrator_store.is_admin(callback.from_user.id)),
            )
            return
        await edit_tool_photo(callback, "main", build_welcome_text(lang), reply_markup=main_menu_keyboard(
            lang, allow_language_choice=administrator_store.is_admin(callback.from_user.id)))
