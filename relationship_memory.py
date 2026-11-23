"""Owner-curated memories shared by Telegram and PWA."""
import re

KINDS = {"joke", "project", "open_thread"}

def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS relationship_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, note)
    )""")

    columns = {row[1] for row in conn.execute("PRAGMA table_info(relationship_memory)")}
    if "kind" not in columns:
        conn.execute("ALTER TABLE relationship_memory ADD COLUMN kind TEXT")
    if "source_id" not in columns:
        conn.execute("ALTER TABLE relationship_memory ADD COLUMN source_id INTEGER")


def save_observation(conn, chat_id, source_id, observation):
    if observation:
        kind, quote = observation
        conn.execute(
            "INSERT OR IGNORE INTO relationship_memory(chat_id,note,kind,source_id) VALUES (?,?,?,?)",
            (chat_id, quote, kind, source_id),
        )


def command(conn, chat_id, text):
    # The caller supplies the authenticated owner scope and strips its own tag.
    if text.casefold() == "что ты помнишь?":
        rows = conn.execute(
            "SELECT id, note FROM relationship_memory WHERE chat_id=? ORDER BY id DESC LIMIT 10",
            (chat_id,),
        )
        return "\n".join(f"#{i} {note}" for i, note in rows) or "Пока ничего не записал."
    match = re.fullmatch(r"(запомни|забудь)\s*:\s*(.+)", text, re.I | re.S)
    if not match:
        return None
    action, note = match.groups()
    note = note.strip()
    if not note or len(note) > 300:
        return "Нужна запись длиной от 1 до 300 символов."
    if action.casefold() == "запомни":
        conn.execute(
            "INSERT OR IGNORE INTO relationship_memory(chat_id,note) VALUES (?,?)",
            (chat_id, note),
        )
        return "Записал."
    if note.startswith("#") and note[1:].isascii() and note[1:].isdigit() and len(note) <= 18:
        cursor = conn.execute("DELETE FROM relationship_memory WHERE chat_id=? AND id=?", (chat_id, int(note[1:])))
    else:
        cursor = conn.execute("DELETE FROM relationship_memory WHERE chat_id=? AND note=?", (chat_id, note))
    return "Забыл." if cursor.rowcount else "Такой записи нет."

def relevant(conn, chat_id, text):
    def words(value):
        return set(re.findall(r"[^\W\d_]{5,}", value.casefold()))
    query = words(text)
    ranked = []
    for ident, note, date, kind in conn.execute(
        "SELECT id,note,created_at,kind FROM relationship_memory WHERE chat_id=?", (chat_id,)
    ):
        score = len(query & words(note))
        if score:
            ranked.append((score, ident, note, date, kind))
    return [{"note": note, "recorded_at_utc": date, "kind": kind} for _, _, note, date, kind in sorted(ranked, reverse=True)[:3]]
