from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards.file import file_actions_keyboard
from bot.i18n import tr
from bot.keyboards.main_menu import back_keyboard
from bot.services.images import SUPPORTED_IMAGE_SUFFIXES, compress_image, convert_image, create_zip_archive, resize_image
from bot.states import FileStates
from bot.utils.temp_files import cleanup_paths, make_temp_path
from bot.utils.messages import answer_callback, edit_tool_photo
from bot.utils.premium_emoji import ERROR, FILE, SUCCESS

router = Router(name="file_converter")


@router.callback_query(F.data == "menu:file")
async def open_file_converter(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(FileStates.waiting_file)
    await edit_tool_photo(
        callback,
        "file",
        f"{FILE.html} <b>{tr(lang, 'Конвертер файлов', 'File converter')}</b>\n\n{tr(lang, 'Отправьте изображение или файл.', 'Send an image or file.')}",
        reply_markup=back_keyboard(lang),
    )


@router.message(FileStates.waiting_file, F.photo | F.document, flags={"heavy": "upload"})
async def receive_file(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    cleanup_paths(data.get("file_input_path"))

    if message.photo:
        file_id = message.photo[-1].file_id
        input_path = make_temp_path(".jpg")
    elif message.document:
        file_id = message.document.file_id
        suffix = Path(message.document.file_name or "").suffix or ".bin"
        input_path = make_temp_path(suffix)
    else:
        await message.answer(f"{ERROR.html} {tr(lang, 'Отправьте файл или изображение.', 'Send a file or image.')}", reply_markup=back_keyboard(lang))
        return

    await message.bot.download(file_id, destination=input_path)
    await state.update_data(file_input_path=str(input_path))
    await message.answer(f"{SUCCESS.html} {tr(lang, 'Файл получен. Выберите действие:', 'File received. Choose an action:')}", reply_markup=file_actions_keyboard(lang))


@router.callback_query(F.data.startswith("file:"), flags={"heavy": True})
async def handle_file_action(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    input_path = Path(data["file_input_path"]) if data.get("file_input_path") else None
    if input_path is None or not input_path.exists():
        await answer_callback(callback, tr(lang, "Сначала отправьте файл.", "Send a file first."), show_alert=True)
        return

    action = callback.data or ""
    output_path: Path | None = None
    processed = False

    try:
        if action.startswith("file:convert:"):
            target = action.rsplit(":", maxsplit=1)[-1]
            _ensure_image(input_path, lang)
            output_path = make_temp_path(f".{target}")
            convert_image(input_path, output_path, target)
            caption = f"{SUCCESS.html} {tr(lang, f'Конвертация в {target.upper()} выполнена.', f'Converted to {target.upper()}.')}"
        elif action.startswith("file:resize:"):
            max_size = int(action.rsplit(":", maxsplit=1)[-1])
            _ensure_image(input_path, lang)
            output_path = make_temp_path(input_path.suffix or ".png")
            resize_image(input_path, output_path, max_size)
            caption = f"{SUCCESS.html} {tr(lang, f'Изображение уменьшено до {max_size}px по большей стороне.', f'Image resized to {max_size}px on its longest side.')}"
        elif action.startswith("file:compress:"):
            quality = int(action.rsplit(":", maxsplit=1)[-1])
            _ensure_image(input_path, lang)
            output_path = make_temp_path(".jpg")
            compress_image(input_path, output_path, quality=quality)
            caption = f"{SUCCESS.html} {tr(lang, f'Изображение сжато до качества {quality}%.', f'Image compressed at {quality}% quality.')}"
        elif action == "file:zip":
            output_path = make_temp_path(".zip")
            create_zip_archive(input_path, output_path)
            caption = f"{SUCCESS.html} {tr(lang, 'ZIP архив создан.', 'ZIP archive created.')}"
        else:
            await answer_callback(callback)
            return

        await callback.message.answer_document(document=FSInputFile(output_path), caption=caption, reply_markup=back_keyboard(lang))
        processed = True
        await state.update_data(file_input_path=None)
        await answer_callback(callback)
    except ValueError as exc:
        await answer_callback(callback, str(exc), show_alert=True)
    finally:
        cleanup_paths(output_path)
        if processed:
            cleanup_paths(input_path)


def _ensure_image(path: Path, lang: str) -> None:
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(tr(lang, "Для этого действия нужен PNG, JPG или WEBP.", "This action requires a PNG, JPG, or WEBP image."))
