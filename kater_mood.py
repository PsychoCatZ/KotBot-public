"""Shared, short-lived tone for the owner's private conversation."""
import re

STYLES = {
    "correction": "Задета гордость. Проверь поправку, признай подтверждённый промах и исправь его. Допустима короткая самоирония.",
    "success": "Доволен собой. Отметь подтверждённый успех с сухим юмором.",
    "joke": "Ехидный и расположенный. Подхвати общую шутку, если она ещё к месту.",
    "support": "Подозрительно добрый. Говори прямо и тепло, без подколов по больному месту.",
}

def detect(text, memories):
    text = text.casefold()
    if re.search(r"\b(?:мне надо выговориться|можно выговориться|мне нужна поддержка|поддержи меня|мне сейчас тяжело)\b", text):
        return "support"
    if re.search(r"\bты (?:ошибся|перепутал|опять перепутал)\b|\bвот правильн(?:ый|ая|ое)\b", text):
        return "correction"
    if not re.search(r"\b(?:не|ничего|пока|если|вроде)\b|\?", text) and re.search(
        r"\b(?:заработало|всё работает|все работает|получилось|сработало)\b", text
    ):
        return "success"
    if any(note.get("kind") == "joke" for note in memories) and re.search(
        r"\b(?:помнишь|шутк\w*|смеялись|ржали|ахаха)\b", text
    ):
        return "joke"
    return None


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS kater_mood (
        chat_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, source_id INTEGER NOT NULL,
        expires_at REAL NOT NULL, remaining INTEGER NOT NULL
    )""")
