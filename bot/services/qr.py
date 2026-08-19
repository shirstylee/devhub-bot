from pathlib import Path

import cv2
import qrcode


def create_qr_image(payload: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    image.save(output_path, "PNG")
    return output_path


def build_wifi_payload(ssid: str, password: str, auth_type: str = "WPA") -> str:
    return f"WIFI:T:{auth_type};S:{_escape_wifi(ssid)};P:{_escape_wifi(password)};;"


def build_phone_payload(phone: str) -> str:
    normalized = phone.strip().replace(" ", "")
    return f"tel:{normalized}"


def build_telegram_payload(username: str) -> str:
    clean = username.strip().removeprefix("@")
    return f"https://t.me/{clean}"


def scan_qr_image(input_path: Path) -> str:
    image = cv2.imread(str(input_path))
    if image is None:
        raise ValueError("Не удалось открыть изображение.")
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)
    if not data:
        raise ValueError("QR-код не найден или изображение слишком размыто.")
    return data


def _escape_wifi(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace(":", "\\:")
