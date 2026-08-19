# 🧰 DevHub Bot

Многофункциональный Telegram-бот с инструментами для разработчиков, тестировщиков и дизайнеров. Интерфейс построен на inline-клавиатурах, Premium/Custom Emoji и отдельных графических панелях.

![DevHub Bot](Images/readme-cover.png)

## 🚀 Возможности

- форматирование и проверка JSON;
- генерация безопасных паролей;
- преобразование HEX/RGB и создание цветовых превью;
- конвертация PNG, JPG и WEBP, изменение размера и сжатие изображений;
- создание ZIP-архивов;
- генерация и распознавание QR-кодов;
- QR-коды для текста, ссылок, Wi-Fi, телефона и Telegram;
- генерация тестовых данных людей, компаний и платежных реквизитов;
- создание PNG-скриншотов кода в стиле Carbon;
- сокращение ссылок через `clck.ru`;
- преобразование PDF в изображения, сборка PDF и извлечение картинок;
- Base64 и URL encode/decode, SHA-256 и SHA-512.

## 🌐 Интерфейс

- русский и английский языки;
- обязательный выбор языка перед первым использованием;
- смена языка через меню или команду `/language`;
- Premium Emoji из единого каталога;
- сохранение настроек отдельно для каждого пользователя;
- редактирование существующей панели вместо цепочки сообщений.

## 🛠️ Стек

- Python 3.14;
- aiogram 3;
- asyncio и FSM;
- Pillow и OpenCV;
- PyMuPDF;
- Pygments;
- qrcode;
- aiohttp и aiofiles.

## ⚡ Быстрый запуск

### 1. 📥 Клонирование

```bash
git clone https://github.com/USERNAME/devhub-bot.git
cd devhub-bot
```

Замените `USERNAME` на имя своего аккаунта GitHub.

### 2. 🐍 Виртуальное окружение

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
```

### 3. 📦 Зависимости

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 🔑 Токен Telegram-бота

Создайте бота через [@BotFather](https://t.me/BotFather), затем скопируйте файл `.env.example` в `.env`.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Укажите токен в `.env`:

```dotenv
BOT_TOKEN=your_bot_token
```

Файл `.env` исключён из Git и не должен публиковаться.

### 5. ▶️ Запуск

```bash
python main.py
```

## 🤖 Команды бота

- `/start` — запуск и главное меню;
- `/menu` — открыть главное меню;
- `/language` — изменить язык интерфейса.

## 🗂️ Структура проекта

```text
DevHub Bot/
├── bot/
│   ├── handlers/       # обработчики сообщений и callback-запросов
│   ├── keyboards/      # inline-клавиатуры
│   ├── middlewares/    # обязательный выбор языка
│   ├── services/       # бизнес-логика инструментов
│   ├── utils/          # сообщения, Premium Emoji и временные файлы
│   ├── data/           # локальные настройки пользователей
│   ├── temp/           # временные результаты обработки
│   ├── config.py
│   └── main.py
├── Images/             # изображения разделов
├── tests/              # автоматические тесты
├── .env.example
├── .gitignore
├── main.py
├── requirements.txt
└── README.md
```

## ✅ Тесты

```bash
python -m unittest discover -s tests -v
```

## 💾 Хранение данных

Настройки языка и инструментов сохраняются локально в `bot/data`. Временные загруженные и созданные файлы находятся в `bot/temp`. Содержимое обеих папок исключено из Git, кроме файлов `.gitkeep`.

## 🔒 Безопасность

- не добавляйте `.env` в Git;
- не публикуйте токен BotFather в README, Issues или логах;
- если токен попал в историю Git, отзовите его через BotFather и выпустите новый;
- перед коммитом проверяйте список файлов командой `git status`.

## 📄 Лицензии ресурсов

Генератор скриншотов использует Hack Regular. Текст лицензии находится в `bot/assets/fonts/Hack-LICENSE.md`. Дополнительные лицензии шрифтов хранятся рядом с соответствующими файлами.
