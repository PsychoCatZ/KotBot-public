import os
import sqlite3
import time
import re
import base64
import requests
from collections import defaultdict, deque

from dotenv import load_dotenv

load_dotenv()

from kater_core import ask_kater
from conversation import ConversationService

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OWNER_TELEGRAM_ID = int(os.environ["OWNER_TELEGRAM_ID"])


def safe_error(error):
    # Исключения requests включают полный URL запроса, а токен Telegram
    # сидит прямо в нём — без маскировки он попадает в журнал и в чат.
    text = str(error)

    for secret in (TELEGRAM_TOKEN, OPENAI_API_KEY):
        if secret:
            text = text.replace(secret, "<hidden>")

    return text


OPENAI_URL = "https://api.openai.com/v1/chat/completions"

DB_PATH = os.environ.get(
    "KATER_DB_PATH",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "kotbot.db"
    )
)

# Сколько сообщений помнить в каждом отдельном чате.
# 20 = примерно 10 реплик человека + 10 ответов кота.
MAX_HISTORY = 20


TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Последние сообщения каждой группы.
GROUP_CONTEXT_LIMIT = 30

group_messages = defaultdict(
    lambda: deque(maxlen=GROUP_CONTEXT_LIMIT)
)


# =========================
# ПЕРСИСТЕНТНОЕ ХРАНИЛИЩЕ (SQLite)
# =========================
# Личная история и групповой контекст переживают перезапуск бота,
# чтобы не терять "сформировавшуюся личность" при каждом рестарте.

db = sqlite3.connect(DB_PATH, check_same_thread=False)

# С 2026-10-19 этот файл пишет и backend/ (PWA) — WAL снижает блокировки
# на чтении, busy_timeout ждёт лок вместо мгновенного "database is locked".
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA busy_timeout=5000")

db.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        image_data_url TEXT
    )
""")

_history_columns = [row[1] for row in db.execute("PRAGMA table_info(history)")]

if "image_data_url" not in _history_columns:
    db.execute("ALTER TABLE history ADD COLUMN image_data_url TEXT")

db.execute("""
    CREATE TABLE IF NOT EXISTS group_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        line TEXT NOT NULL
    )
""")
db.commit()
conversations = ConversationService(DB_PATH, owner_id=OWNER_TELEGRAM_ID)


def load_state():
    for chat_id, line in db.execute(
        "SELECT chat_id, line FROM group_messages ORDER BY id"
    ):
        group_messages[chat_id].append(line)


def save_group_message(chat_id, line):
    db.execute(
        "INSERT INTO group_messages (chat_id, line) VALUES (?, ?)",
        (chat_id, line)
    )

    db.execute(
        """
        DELETE FROM group_messages
        WHERE chat_id = ? AND id NOT IN (
            SELECT id FROM group_messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (chat_id, chat_id, GROUP_CONTEXT_LIMIT)
    )

    db.commit()


def get_bot_info():
    response = requests.get(
        f"{TG_API}/getMe",
        timeout=30
    )
    response.raise_for_status()

    bot = response.json()["result"]

    return bot["id"], bot["username"]


def get_sender_tag(message, author):
    # Тег строится по Telegram ID из апдейта, а не по тексту сообщения —
    # гость не может подделать его, написав "я Создатель".
    user_id = message.get("from", {}).get("id")

    if user_id == OWNER_TELEGRAM_ID:
        return "[Отправитель: Создатель]"

    return f"[Отправитель: Гость | Имя: {author}]"


def download_image_as_data_url(file_id):
    response = requests.get(
        f"{TG_API}/getFile",
        params={"file_id": file_id},
        timeout=30
    )
    response.raise_for_status()

    file_path = response.json()["result"]["file_path"]

    # Файл Telegram-фото отдаёт только по ссылке с тем же токеном бота,
    # что и сам API, — маскируем через safe_error() так же, как остальные запросы.
    file_url = (
        f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    )

    image_response = requests.get(file_url, timeout=30)
    image_response.raise_for_status()

    extension = file_path.rsplit(".", 1)[-1].lower()
    mime_type = "image/jpeg" if extension in ("jpg", "jpeg") else f"image/{extension}"

    encoded = base64.b64encode(image_response.content).decode("ascii")

    return f"data:{mime_type};base64,{encoded}"


def get_author_name(message):
    user = message.get("from", {})

    username = user.get("username")

    if username:
        return f"@{username}"

    first_name = user.get("first_name", "")
    last_name = user.get("last_name", "")

    name = f"{first_name} {last_name}".strip()

    return name or "Участник"


def is_bot_called(message, bot_id, bot_username):
    text = message.get("text", "") or message.get("caption", "")

    # @username бота
    by_username = (
        f"@{bot_username}".casefold()
        in text.casefold()
    )

    # Отдельное слово "кот":
    # "Кот, ты где?" → да
    # "кот!" → да
    # "котлета" → нет
    by_cat = (
        re.search(
            r"(?<!\w)кот(?!\w)",
            text,
            flags=re.IGNORECASE
        )
        is not None
    )

    # "кис-кис", "кис кис", "КИС—КИС"
    by_kiskis = (
        re.search(
            r"(?<!\w)кис[\s\-–—]*кис(?!\w)",
            text,
            flags=re.IGNORECASE
        )
        is not None
    )

    # Reply непосредственно на сообщение Злого Кота
    replied_message = message.get("reply_to_message", {})
    replied_from = replied_message.get("from", {})

    by_reply = (
        replied_from.get("id") == bot_id
    )

    return by_username or by_cat or by_kiskis or by_reply


def ask_openai(
    chat_id,
    text,
    group_context=None,
    save_history=True,
    image_data_url=None
):
    if save_history:
        return conversations.respond(chat_id, text, image_data_url=image_data_url)
    return ask_kater([], text, image_data_url=image_data_url, group_context=group_context)


def clear_history(chat_id):
    # Личная история живёт только в БД (см. ConversationService) — её
    # достаточно удалить оттуда, в памяти процесса копии больше нет.

    # Групповая память, если это группа
    group_messages.pop(chat_id, None)

    conversations.clear_history(chat_id)
    db.execute("DELETE FROM group_messages WHERE chat_id = ?", (chat_id,))
    db.commit()


def send_message(
    chat_id,
    text,
    reply_to_message_id=None,
    reply_markup=None
):
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    if reply_to_message_id is not None:
        payload["reply_parameters"] = {
            "message_id": reply_to_message_id
        }

    response = requests.post(
        f"{TG_API}/sendMessage",
        json=payload,
        timeout=30
    )

    response.raise_for_status()


def main():
    print("Злой Кот запущен 🐈‍⬛")

    load_state()

    try:
        bot_id, bot_username = get_bot_info()
    except Exception as e:
        # Без этого traceback с URL (и токеном) уходит в журнал systemd.
        print("Не удалось получить данные бота:", safe_error(e))
        raise SystemExit(1)

    print(
        f"Telegram: @{bot_username} "
        f"(ID {bot_id})"
    )

    offset = None
    next_follow_up = time.monotonic() + 600

    while True:
        try:
            params = {
                "timeout": 30
            }

            if offset is not None:
                params["offset"] = offset

            response = requests.get(
                f"{TG_API}/getUpdates",
                params=params,
                timeout=40
            )

            response.raise_for_status()

            updates = response.json()["result"]
            if not updates and time.monotonic() >= next_follow_up:
                next_follow_up = time.monotonic() + 600
                conversations.follow_up(send_message)

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("message")

                if not message:
                    continue

                text = (
                    message.get("text")
                    or message.get("caption")
                )

                photo_sizes = message.get("photo")

                if not text and not photo_sizes:
                    continue

                image_data_url = None

                if photo_sizes:
                    try:
                        # Последний элемент — самое большое разрешение.
                        image_data_url = download_image_as_data_url(
                            photo_sizes[-1]["file_id"]
                        )
                    except Exception as e:
                        print(
                            "Не удалось загрузить фото:",
                            safe_error(e)
                        )

                    if not text:
                        text = "[фото без подписи]"

                chat_id = message["chat"]["id"]
                chat_type = message["chat"]["type"]
                if chat_type == "private" and chat_id == OWNER_TELEGRAM_ID:
                    prompts = {
                        "Запомни": ("Запомни:", "Ответь на это сообщение текстом заметки, которую сохранить."),
                        "Забудь": ("Забудь:", "Ответь на это сообщение номером заметки вида #12 или её точным текстом."),
                    }
                    if text.strip() in prompts:
                        prefix, prompt = prompts[text.strip()]
                        send_message(chat_id, f"{prefix} {prompt}", reply_markup={"force_reply": True})
                        continue
                    reply = message.get("reply_to_message") or {}
                    if (reply.get("from") or {}).get("id") == bot_id:
                        for prefix, prompt in prompts.values():
                            if reply.get("text") == f"{prefix} {prompt}":
                                text = f"{prefix} {text}"
                                break
                if chat_type == "private" and chat_id == OWNER_TELEGRAM_ID and text.strip() == "/start":
                    send_message(chat_id, "Управление инициативой", reply_markup={
                        "keyboard": [
                            [{"text": "Инициативу включить"}, {"text": "Инициативу выключить"}],
                            [{"text": "Статус инициативы"}, {"text": "Что ты помнишь?"}],
                            [{"text": "Запомни"}, {"text": "Забудь"}],
                        ],
                        "resize_keyboard": True,
                        "is_persistent": True,
                    })
                    continue
                message_id = message["message_id"]

                print(
                    f"[{chat_id}] Получено: {text}"
                )

                # =========================
                # /CLEAR
                # =========================

                if text.strip().lower() == "/clear":
                    clear_history(chat_id)

                    send_message(
                        chat_id,
                        "Память очищена. Кто ты вообще такой? 😼",
                        reply_to_message_id=(
                            message_id
                            if chat_type in ("group", "supergroup")
                            else None
                        )
                    )

                    print(
                        f"[{chat_id}] История очищена"
                    )

                    continue

                # =========================
                # ГРУППОВОЙ РЕЖИМ
                # =========================

                if chat_type in ("group", "supergroup"):
                    author = get_author_name(message)
                    sender_tag = get_sender_tag(message, author)

                    # Контекст до текущего сообщения.
                    previous_context = "\n".join(
                        group_messages[chat_id]
                    )

                    called = is_bot_called(
                        message,
                        bot_id,
                        bot_username
                    )

                    # Любое сообщение группы просто запоминаем.
                    group_line = f"{author}: {text}"
                    group_messages[chat_id].append(group_line)
                    save_group_message(chat_id, group_line)

                    # Никто Кота не звал.
                    # OpenAI вообще не запускается.
                    if not called:
                        print(
                            f"[GROUP {chat_id}] "
                            f"{author}: {text} "
                            f"(Кот молчит)"
                        )
                        continue

                    print(
                        f"[GROUP {chat_id}] "
                        f"Кота позвал {author}: {text}"
                    )

                    try:
                        answer = ask_openai(
                            chat_id,
                            f"{sender_tag}\n{author}: {text}",
                            group_context=previous_context,
                            save_history=False,
                            image_data_url=image_data_url
                        )

                    except Exception as e:
                        answer = (
                            f"У меня опять мозги отвалились: {safe_error(e)}"
                        )

                    # Запоминаем собственный ответ Кота.
                    answer_line = f"Kater: {answer}"
                    group_messages[chat_id].append(answer_line)
                    save_group_message(chat_id, answer_line)

                    send_message(
                        chat_id,
                        answer,
                        reply_to_message_id=message_id
                    )

                    print(
                        f"[GROUP {chat_id}] "
                        f"Ответ: {answer}"
                    )

                    continue

                # =========================
                # ЛИЧНЫЙ ЧАТ
                # =========================

                author = get_author_name(message)
                sender_tag = get_sender_tag(message, author)

                try:
                    answer = ask_openai(
                        chat_id,
                        f"{sender_tag}\n{text}",
                        image_data_url=image_data_url
                    )

                except Exception as e:
                    answer = (
                        f"OpenAI опять занимается хуйнёй: {safe_error(e)}"
                    )

                print(
                    f"[{chat_id}] Ответ: {answer}"
                )

                send_message(
                    chat_id,
                    answer
                )

        except KeyboardInterrupt:
            print("\nЗлой Кот уснул.")
            break

        except Exception as e:
            print("Ошибка:", safe_error(e))
            time.sleep(3)


if __name__ == "__main__":
    main()
