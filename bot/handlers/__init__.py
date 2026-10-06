from aiogram import Router

from bot.handlers import (
    admin,
    code_screenshot,
    color_picker,
    common,
    fake_data_generator,
    file_converter,
    json_formatter,
    language,
    link_shortener,
    password_generator,
    pdf_tools,
    qr_tools,
    text_tools,
)


def setup_routers() -> tuple[Router, ...]:
    return (
        admin.router,
        language.router,
        common.router,
        json_formatter.router,
        password_generator.router,
        color_picker.router,
        file_converter.router,
        qr_tools.router,
        fake_data_generator.router,
        code_screenshot.router,
        link_shortener.router,
        pdf_tools.router,
        text_tools.router,
    )
