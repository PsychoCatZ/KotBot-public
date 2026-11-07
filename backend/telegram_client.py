import os

import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_text(chat_id, text):
    # Лучшая попытка: это эхо PWA-сообщения в Telegram, не критичная часть
    # ответа пользователю веба — падать из-за сбоя Telegram не должны.
    try:
        requests.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15
        )
    except Exception:
        pass


def send_photo(chat_id, photo_bytes, caption=""):
    try:
        requests.post(
            f"{TG_API}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("image.jpg", photo_bytes)},
            timeout=30
        )
    except Exception:
        pass
