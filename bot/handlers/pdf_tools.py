from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards.main_menu import back_keyboard
from bot.i18n import tr
from bot.keyboards.pdf import image_pdf_collect_keyboard, pdf_tools_keyboard
from bot.services.pdf_tools import extract_images_from_pdf, images_to_pdf, pdf_pages_to_images, zip_paths
from bot.states import PdfStates
from bot.utils.temp_files import cleanup_paths, make_temp_dir, make_temp_path
from bot.utils.messages import answer_callback, edit_message_text, edit_tool_photo
from bot.utils.premium_emoji import ERROR, FILE, SUCCESS

router = Router(name="pdf_tools")


@router.callback_query(F.data == "menu:pdf")
async def open_pdf_tools(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await edit_tool_photo(callback, "pdf", f"{FILE.html} <b>{tr(lang, 'PDF-инструменты', 'PDF tools')}</b>\n\n{tr(lang, 'Выберите действие:', 'Choose an action:')}", reply_markup=pdf_tools_keyboard(lang))


@router.callback_query(F.data.startswith("pdf:mode:"))
async def set_pdf_mode(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    mode = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    await state.update_data(pdf_mode=mode, pdf_images=[])
    if mode == "images_to_pdf":
        await state.set_state(PdfStates.waiting_images)
        await edit_message_text(callback, tr(lang, "Отправляйте изображения по одному. После загрузки нажмите «Создать PDF».", "Send images one at a time. When finished, tap “Create PDF”."), reply_markup=back_keyboard(lang))
    else:
        await state.set_state(PdfStates.waiting_pdf)
        await edit_message_text(callback, tr(lang, "Отправьте PDF файлом.", "Send a PDF file."), reply_markup=back_keyboard(lang))


@router.message(PdfStates.waiting_pdf, F.document, flags={"heavy": True})
async def receive_pdf(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    mode = data.get("pdf_mode")
    input_path = make_temp_path(".pdf")
    output_dir = make_temp_dir()
    archive_path = make_temp_path(".zip")
    try:
        await message.bot.download(message.document.file_id, destination=input_path)
        if mode in {"pages_png", "pages_jpg"}:
            image_format = "jpg" if mode == "pages_jpg" else "png"
            paths = pdf_pages_to_images(input_path, output_dir, image_format)
            caption = f"{SUCCESS.html} {tr(lang, f'Страницы PDF экспортированы в {image_format.upper()}.', f'PDF pages exported as {image_format.upper()}.')}"
        else:
            paths = extract_images_from_pdf(input_path, output_dir)
            caption = f"{SUCCESS.html} {tr(lang, 'Картинки из PDF извлечены.', 'Images extracted from the PDF.')}"
        if not paths:
            await message.answer(f"{ERROR.html} {tr(lang, 'В PDF не найдено подходящих данных.', 'No suitable data was found in the PDF.')}", reply_markup=back_keyboard(lang))
            return
        zip_paths(paths, archive_path)
        await message.answer_document(FSInputFile(archive_path), caption=caption, reply_markup=pdf_tools_keyboard(lang))
    finally:
        cleanup_paths(input_path, output_dir, archive_path)


@router.message(PdfStates.waiting_images, F.photo | F.document, flags={"heavy": "upload"})
async def receive_pdf_image(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    image_paths = list(data.get("pdf_images", []))
    if message.photo:
        file_id = message.photo[-1].file_id
        input_path = make_temp_path(".jpg")
    elif message.document:
        file_id = message.document.file_id
        input_path = make_temp_path(Path(message.document.file_name or "image.jpg").suffix or ".jpg")
    else:
        return
    await message.bot.download(file_id, destination=input_path)
    image_paths.append(str(input_path))
    await state.update_data(pdf_images=image_paths)
    await message.answer(f"{SUCCESS.html} {tr(lang, f'Изображений загружено: {len(image_paths)}', f'Images uploaded: {len(image_paths)}')}", reply_markup=image_pdf_collect_keyboard(len(image_paths), lang))


@router.callback_query(F.data == "pdf:create_from_images", flags={"heavy": True})
async def create_pdf_from_images(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    paths = [Path(path) for path in data.get("pdf_images", [])]
    if not paths:
        await answer_callback(callback, tr(lang, "Сначала отправьте изображения.", "Send images first."), show_alert=True)
        return
    await answer_callback(callback)
    output_path = make_temp_path(".pdf")
    try:
        images_to_pdf(paths, output_path)
        await callback.message.answer_document(FSInputFile(output_path), caption=f"{SUCCESS.html} {tr(lang, 'PDF создан.', 'PDF created.')}", reply_markup=pdf_tools_keyboard(lang))
        await state.update_data(pdf_images=[])
    finally:
        cleanup_paths(*paths, output_path)
