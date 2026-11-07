import os
import sqlite3

DB_PATH = os.environ.get("KATER_DB_PATH", "kater.db")

# Та же логика хранения, что и в bot.py — с 2026-10-19 это буквально один и тот
# же файл (общая история Telegram и веба), см. AGENTS.md.
MAX_HISTORY = 20

_db = None


def get_db():
    global _db

    if _db is None:
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)

        # Файл пишут два независимых процесса (bot.py и этот backend) —
        # WAL снижает блокировки на чтении, busy_timeout ждёт лок вместо
        # мгновенного "database is locked".
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA busy_timeout=5000")

        _db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                image_data_url TEXT
            )
        """)

        columns = [row[1] for row in _db.execute("PRAGMA table_info(history)")]

        if "image_data_url" not in columns:
            _db.execute("ALTER TABLE history ADD COLUMN image_data_url TEXT")

        _db.commit()

    return _db


def load_history(chat_id):
    db = get_db()

    rows = db.execute(
        "SELECT role, content, image_data_url FROM history WHERE chat_id = ? ORDER BY id",
        (chat_id,)
    ).fetchall()

    return [
        {"role": role, "content": content, "image_data_url": image_data_url}
        for role, content, image_data_url in rows
    ]


def save_message(chat_id, role, content, image_data_url=None):
    db = get_db()

    db.execute(
        "INSERT INTO history (chat_id, role, content, image_data_url) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, image_data_url)
    )

    db.execute(
        """
        DELETE FROM history
        WHERE chat_id = ? AND id NOT IN (
            SELECT id FROM history
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (chat_id, chat_id, MAX_HISTORY)
    )

    db.commit()


def clear_history(chat_id):
    db = get_db()
    db.execute("DELETE FROM history WHERE chat_id = ?", (chat_id,))
    db.commit()
