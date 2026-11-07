import os
import requests

from persona import MODEL, SYSTEM_PROMPT

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def ask_kater(history, text, image_data_url=None):
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    # history хранит image_data_url для отображения в UI, но старые картинки
    # в модель повторно не шлём — иначе каждый запрос тянул бы за собой
    # все вложения разговора и раздувал бы токены.
    for item in history:
        messages.append({
            "role": item["role"],
            "content": item["content"]
        })

    if image_data_url:
        user_content = [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_data_url}}
        ]
    else:
        user_content = text

    messages.append({
        "role": "user",
        "content": user_content
    })

    payload = {
        "model": MODEL,
        "messages": messages,
        "reasoning_effort": "low",
        "max_completion_tokens": 350
    }

    response = requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        },
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    return (
        data["choices"][0]["message"]["content"]
        .strip()
    )
