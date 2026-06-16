import os
import sqlite3
from datetime import datetime, timezone


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS spaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            purpose TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'inbox',
            space_id INTEGER REFERENCES spaces(id),
            confidence REAL,
            classified_at TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_space(conn, name: str, purpose: str) -> int:
    cur = conn.execute(
        "INSERT INTO spaces (name, purpose, created_at) VALUES (?, ?, ?)",
        (name, purpose, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_spaces(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM spaces ORDER BY name")]


def delete_space(conn, space_id: int) -> None:
    conn.execute("UPDATE notes SET space_id=NULL, status='inbox' WHERE space_id=?", (space_id,))
    conn.execute("DELETE FROM spaces WHERE id=?", (space_id,))
    conn.commit()


def add_note(conn, body: str) -> int:
    cur = conn.execute(
        "INSERT INTO notes (body, status, created_at) VALUES (?, 'inbox', ?)",
        (body, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_note(conn, note_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    return dict(row) if row else None


def unclassified_notes(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM notes WHERE classified_at IS NULL ORDER BY created_at"
        )
    ]


def inbox_notes(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM notes WHERE status='inbox' ORDER BY created_at DESC"
        )
    ]


def notes_in_space(conn, space_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM notes WHERE space_id=? ORDER BY created_at DESC", (space_id,)
        )
    ]


def file_note(conn, note_id: int, space_id: int, confidence: float) -> None:
    conn.execute(
        "UPDATE notes SET status='filed', space_id=?, confidence=?, classified_at=? WHERE id=?",
        (space_id, confidence, _now(), note_id),
    )
    conn.commit()


def flag_note(conn, note_id: int, confidence: float) -> None:
    conn.execute(
        "UPDATE notes SET confidence=?, classified_at=? WHERE id=?",
        (confidence, _now(), note_id),
    )
    conn.commit()


def move_note(conn, note_id: int, space_id: int | None) -> None:
    status = "filed" if space_id is not None else "inbox"
    conn.execute(
        "UPDATE notes SET space_id=?, status=? WHERE id=?",
        (space_id, status, note_id),
    )
    conn.commit()
