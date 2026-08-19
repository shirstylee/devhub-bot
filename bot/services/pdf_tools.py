from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
from PIL import Image, ImageOps


def pdf_pages_to_images(input_path: Path, output_dir: Path, image_format: str = "png") -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with fitz.open(input_path) as document:
        for page_index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            suffix = "jpg" if image_format == "jpg" else "png"
            output_path = output_dir / f"page-{page_index:03d}.{suffix}"
            pixmap.save(output_path)
            paths.append(output_path)
    return paths


def images_to_pdf(input_paths: list[Path], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    images: list[Image.Image] = []
    for input_path in input_paths:
        with Image.open(input_path) as source:
            images.append(ImageOps.exif_transpose(source).convert("RGB"))
    if not images:
        raise ValueError("Нет изображений для PDF.")
    first, rest = images[0], images[1:]
    first.save(output_path, "PDF", save_all=True, append_images=rest)
    for image in images:
        image.close()
    return output_path


def extract_images_from_pdf(input_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with fitz.open(input_path) as document:
        counter = 1
        for page_index in range(len(document)):
            for image_info in document.get_page_images(page_index):
                xref = image_info[0]
                extracted = document.extract_image(xref)
                ext = extracted.get("ext", "png")
                output_path = output_dir / f"image-{counter:03d}.{ext}"
                output_path.write_bytes(extracted["image"])
                paths.append(output_path)
                counter += 1
    return paths


def zip_paths(paths: list[Path], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)
    return output_path
