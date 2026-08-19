from aiogram.fsm.state import State, StatesGroup


class JsonStates(StatesGroup):
    waiting_json = State()


class ColorStates(StatesGroup):
    waiting_hex = State()
    waiting_rgb = State()


class FileStates(StatesGroup):
    waiting_file = State()


class QrStates(StatesGroup):
    waiting_text = State()
    waiting_wifi_ssid = State()
    waiting_wifi_password = State()
    waiting_phone = State()
    waiting_username = State()
    waiting_photo = State()


class FakeDataStates(StatesGroup):
    choosing_country = State()
    waiting_count = State()


class PasswordStates(StatesGroup):
    waiting_length = State()
    waiting_count = State()


class CodeScreenshotStates(StatesGroup):
    waiting_code = State()
    waiting_background_hex = State()


class RecolorStates(StatesGroup):
    waiting_file = State()
    waiting_custom_color = State()


class LinkShortenerStates(StatesGroup):
    waiting_url = State()


class PdfStates(StatesGroup):
    waiting_pdf = State()
    waiting_images = State()


class TextToolsStates(StatesGroup):
    waiting_input = State()


class RenderStates(StatesGroup):
    ready = State()
    waiting_background = State()
    waiting_resolution = State()
    waiting_media = State()
    waiting_emoji_color = State()
    waiting_emoji_size = State()
    waiting_preview_source = State()
    waiting_watermark_name = State()
    waiting_watermark_font = State()
    waiting_watermark_color = State()
    waiting_watermark_size = State()
    choosing_pack = State()
