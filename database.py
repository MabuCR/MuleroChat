"""
MuleroChat - Database layer (SQLite).
Keeps it simple: users + messages. That's it.
"""
import sqlite3
import hashlib
from pathlib import Path

DB_PATH = Path(__file__).parent / "mulerochat.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                pin_hash   TEXT    NOT NULL,
                is_admin   INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id  INTEGER NOT NULL,
                sender     TEXT    NOT NULL,   -- 'driver' | 'admin'
                content    TEXT,
                photo_url  TEXT,
                is_read    INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY(driver_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_msg_driver ON messages(driver_id);
        """)
    _seed_admin()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _hash(pin: str) -> str:
    return hashlib.sha256(pin.strip().encode()).hexdigest()


def _seed_admin():
    """Create default admin on first run. Change PIN after install!"""
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE is_admin=1").fetchone():
            conn.execute(
                "INSERT INTO users(name, pin_hash, is_admin) VALUES(?,?,1)",
                ("Manfred", _hash("1234")),
            )
            conn.commit()


# ── User CRUD ─────────────────────────────────────────────────────────────────

def get_user_by_name(name: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()


def get_user_by_id(uid: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def create_driver(name: str, pin: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users(name, pin_hash, is_admin) VALUES(?,?,0)",
            (name.strip(), _hash(pin)),
        )
        conn.commit()
    return get_user_by_name(name.strip())


def verify_pin(user, pin: str) -> bool:
    return user["pin_hash"] == _hash(pin)


def get_all_drivers():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE is_admin=0 ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()


# ── Message CRUD ──────────────────────────────────────────────────────────────

def save_message(driver_id: int, sender: str, content: str = None, photo_url: str = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages(driver_id, sender, content, photo_url) VALUES(?,?,?,?)",
            (driver_id, sender, content, photo_url),
        )
        conn.commit()
        return cur.lastrowid


def get_messages(driver_id: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM messages WHERE driver_id=? ORDER BY created_at ASC",
            (driver_id,),
        ).fetchall()


def mark_read(driver_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE messages SET is_read=1 WHERE driver_id=? AND sender='driver' AND is_read=0",
            (driver_id,),
        )
        conn.commit()


def get_unread_count(driver_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE driver_id=? AND sender='driver' AND is_read=0",
            (driver_id,),
        ).fetchone()
        return row["n"] if row else 0


def get_last_message(driver_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM messages WHERE driver_id=? ORDER BY created_at DESC LIMIT 1",
            (driver_id,),
        ).fetchone()
