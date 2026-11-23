"""Shared persistent conversation service for both transports."""
import os
import sqlite3
import time
import apartment_memory
import kater_mood
import kater_initiative
from contextlib import contextmanager
from pathlib import Path
from kater_core import ask_kater, observe_relationship
import relationship_memory

MAX_HISTORY = 20

@contextmanager
def chat_lock(db_path, chat_id):
    # Linux production: cross-process lock, released automatically on crash.
    path = str(Path(db_path).resolve()) + ".chat-" + str(int(chat_id)) + ".lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o660)
        os.chmod(path, 0o660)  # preserve shared group write despite service umask
    except FileExistsError:
        fd = os.open(path, os.O_RDWR)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)

class ConversationService:
    def __init__(self, db_path, owner_id=None):
        self.db_path = db_path
        self.owner_id = owner_id

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, image_data_url TEXT)")
            cols = {r[1] for r in conn.execute("PRAGMA table_info(history)")}
            if "image_data_url" not in cols:
                conn.execute("ALTER TABLE history ADD COLUMN image_data_url TEXT")
            conn.commit()
            yield conn
        finally:
            conn.close()

    def load_history(self, chat_id):
        with self.connection() as conn:
            rows = conn.execute("SELECT role, content, image_data_url FROM history WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
        return [dict(role=r, content=c, image_data_url=i) for r,c,i in rows]

    def clear_history(self, chat_id):
        with chat_lock(self.db_path, chat_id), self.connection() as conn:
            with conn:
                conn.execute("DELETE FROM history WHERE chat_id=?", (chat_id,))
                kater_mood.ensure_schema(conn)
                conn.execute("DELETE FROM kater_mood WHERE chat_id=?", (chat_id,))

    def respond(self, chat_id, text, image_data_url=None):
        with chat_lock(self.db_path, chat_id):
            options = {}
            event = previous = None
            now = time.time()
            if chat_id == self.owner_id:
                options["allow_search"] = True
                raw = text.removeprefix("[Отправитель: Создатель]\n").strip()
                with self.connection() as conn, conn:
                    relationship_memory.ensure_schema(conn)
                    result = kater_initiative.record_activity(conn, chat_id, now, raw)
                    if result is not None:
                        return result
                    result = relationship_memory.command(conn, chat_id, raw)
                    if result is not None:
                        return result
                    memories = relationship_memory.relevant(conn, chat_id, raw)
                    apartment = apartment_memory.kater_context(conn, raw)
                    if apartment:
                        options["apartment"] = apartment
                    kater_mood.ensure_schema(conn)
                    previous = conn.execute(
                        "SELECT kind FROM kater_mood WHERE chat_id=? AND expires_at>? AND remaining>0",
                        (chat_id, now),
                    ).fetchone()
                event = kater_mood.detect(raw, memories)
                mood = event or (previous[0] if previous else None)
                if mood:
                    options["mood"] = kater_mood.STYLES[mood]
                if memories:
                    options["memories"] = memories
            history = self.load_history(chat_id)
            answer = ask_kater(history, text, image_data_url=image_data_url, **options)
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Модель не вернула текст")
            observation = observe_relationship(history, raw) if chat_id == self.owner_id else None
            with self.connection() as conn, conn:
                source = conn.execute(
                    "INSERT INTO history(chat_id,role,content,image_data_url) VALUES (?,?,?,?)",
                    (chat_id, "user", text, image_data_url),
                )
                conn.execute(
                    "INSERT INTO history(chat_id,role,content) VALUES (?,?,?)",
                    (chat_id, "assistant", answer),
                )
                if event:
                    conn.execute(
                        "INSERT OR REPLACE INTO kater_mood VALUES (?,?,?,?,?)",
                        (chat_id, event, source.lastrowid, now + 90 * 60, 2),
                    )
                elif previous:
                    conn.execute("UPDATE kater_mood SET remaining=remaining-1 WHERE chat_id=?", (chat_id,))
                relationship_memory.save_observation(conn, chat_id, source.lastrowid, observation)
                conn.execute("DELETE FROM history WHERE chat_id=? AND id NOT IN (SELECT id FROM history WHERE chat_id=? ORDER BY id DESC LIMIT ?)", (chat_id,chat_id,MAX_HISTORY))
            return answer

    def follow_up(self, send):
        if self.owner_id is None:
            return False
        with chat_lock(self.db_path, self.owner_id):
            with self.connection() as conn, conn:
                relationship_memory.ensure_schema(conn)
                message = kater_initiative.claim(conn, self.owner_id, time.time())
            if message is None:
                return False
            send(self.owner_id, message)
            with self.connection() as conn, conn:
                conn.execute("INSERT INTO history(chat_id,role,content) VALUES (?,?,?)",
                             (self.owner_id, "assistant", message))
            return True
