from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageOps


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def convert_image(input_path: Path, output_path: Path, target_format: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(input_path) as image:
        prepared = _prepare_for_format(image, target_format)
        prepared.save(output_path, _pil_format(target_format))
    return output_path


def resize_image(input_path: Path, output_path: Path, max_size: int) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(input_path) as image:
        prepared = image.copy()
        prepared.thumbnail((max_size, max_size))
        prepared.save(output_path, image.format or "PNG")
    return output_path


def compress_image(input_path: Path, output_path: Path, quality: int = 50) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(input_path) as image:
        prepared = ImageOps.exif_transpose(image)
        prepared = prepared.convert("RGB")
        prepared.save(output_path, "JPEG", optimize=True, quality=quality)
    return output_path


def create_zip_archive(input_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(input_path, arcname=input_path.name)
    return output_path


def _prepare_for_format(image: Image.Image, target_format: str) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if target_format.lower() in {"jpg", "jpeg"}:
        return image.convert("RGB")
    return image.copy()


def _pil_format(target_format: str) -> str:
    if target_format.lower() == "jpg":
        return "JPEG"
    return target_format.upper()
