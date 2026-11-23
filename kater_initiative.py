"""Occasional owner-only follow-ups from saved open threads."""
from datetime import datetime
from zoneinfo import ZoneInfo

HOUR = 3600
ZONE = ZoneInfo("Asia/Krasnoyarsk")


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS kater_initiative (
        chat_id INTEGER PRIMARY KEY, activity REAL NOT NULL,
        last_attempt REAL NOT NULL DEFAULT 0, last_note INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 1
    )""")


def record_activity(conn, chat_id, now, text):
    ensure_schema(conn)
    if text.casefold() == "статус инициативы":
        row = conn.execute("SELECT enabled FROM kater_initiative WHERE chat_id=?", (chat_id,)).fetchone()
        return "Инициатива включена." if row is None or row[0] else "Инициатива выключена."
    conn.execute("""INSERT INTO kater_initiative(chat_id, activity) VALUES (?,?)
        ON CONFLICT(chat_id) DO UPDATE SET activity=excluded.activity""", (chat_id, now))
    toggle = {"инициативу выключить": 0, "инициативу включить": 1}.get(text.casefold())
    if toggle is not None:
        conn.execute("UPDATE kater_initiative SET enabled=? WHERE chat_id=?", (toggle, chat_id))
        return "Буду ждать, пока позовёшь." if not toggle else "Ладно. Если будет повод, напишу."


def claim(conn, chat_id, now):
    if 8 <= datetime.fromtimestamp(now, ZONE).hour < 20:
        return None
    ensure_schema(conn)
    row = conn.execute(
        "SELECT activity,last_attempt,last_note,enabled FROM kater_initiative WHERE chat_id=?",
        (chat_id,),
    ).fetchone()
    if row is None:
        return None
    activity, last_attempt, last_note, enabled = row
    if not enabled or now - activity < 12 * HOUR or now - last_attempt < 48 * HOUR or activity <= last_attempt:
        return None
    note = conn.execute("""SELECT id,note FROM relationship_memory
        WHERE chat_id=? AND kind='open_thread' AND id>?
        AND created_at BETWEEN datetime(?, 'unixepoch', '-7 days')
                           AND datetime(?, 'unixepoch', '-1 day')
        ORDER BY id DESC LIMIT 1""", (chat_id, last_note, now, now)).fetchone()
    if note is None:
        return None
    # Claim before sending so timeouts and restarts cannot trigger duplicate notifications.
    conn.execute("UPDATE kater_initiative SET last_attempt=?,last_note=? WHERE chat_id=?",
                 (now, note[0], chat_id))
    return f"Создатель, чем в итоге закончилась эта история? Я тогда записал: «{note[1]}». Любопытство, разумеется, сугубо профессиональное."
