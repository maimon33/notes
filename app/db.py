import json
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


def _columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


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
            created_at TEXT NOT NULL,
            private INTEGER NOT NULL DEFAULT 0,
            confirmed INTEGER NOT NULL DEFAULT 0,
            suggestions TEXT
        );
        """
    )
    # In-place migration for DBs created before these columns existed.
    cols = _columns(conn, "notes")
    if "private" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN private INTEGER NOT NULL DEFAULT 0")
    if "confirmed" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0")
        # back-fill: notes already filed should not reappear in the triage inbox
        conn.execute("UPDATE notes SET confirmed=1 WHERE status='filed'")
    if "suggestions" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN suggestions TEXT")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----- spaces ---------------------------------------------------------------

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
    conn.execute(
        "UPDATE notes SET space_id=NULL, status='inbox', confirmed=0 WHERE space_id=?",
        (space_id,),
    )
    conn.execute("DELETE FROM spaces WHERE id=?", (space_id,))
    conn.commit()


# ----- notes ----------------------------------------------------------------

def _row(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["suggestions"] = json.loads(d["suggestions"]) if d.get("suggestions") else None
    return d


def add_note(conn, body: str, private: bool = False) -> int:
    cur = conn.execute(
        "INSERT INTO notes (body, status, created_at, private) VALUES (?, 'inbox', ?, ?)",
        (body, _now(), 1 if private else 0),
    )
    conn.commit()
    return cur.lastrowid


def get_note(conn, note_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone())


def _rows(cur) -> list[dict]:
    return [_row(r) for r in cur]


def unclassified_notes(conn) -> list[dict]:
    # only notes the AI should look at: not yet classified and not private
    return _rows(conn.execute(
        "SELECT * FROM notes WHERE classified_at IS NULL AND private=0 ORDER BY created_at"
    ))


def notes_in_space(conn, space_id: int) -> list[dict]:
    return _rows(conn.execute(
        "SELECT * FROM notes WHERE space_id=? ORDER BY created_at DESC", (space_id,)
    ))


# inbox triage groups
def recently_filed(conn) -> list[dict]:
    return _rows(conn.execute(
        "SELECT * FROM notes WHERE status='filed' AND confirmed=0 ORDER BY classified_at DESC"
    ))


def needs_sorting(conn) -> list[dict]:
    return _rows(conn.execute(
        "SELECT * FROM notes WHERE status='inbox' AND private=0 AND classified_at IS NOT NULL "
        "ORDER BY created_at DESC"
    ))


def private_and_pending(conn) -> list[dict]:
    return _rows(conn.execute(
        "SELECT * FROM notes WHERE private=1 OR (status='inbox' AND private=0 AND classified_at IS NULL) "
        "ORDER BY created_at DESC"
    ))


# state transitions
def file_note(conn, note_id: int, space_id: int, confidence: float | None, confirmed: bool = False) -> None:
    conn.execute(
        "UPDATE notes SET status='filed', space_id=?, confidence=?, confirmed=?, classified_at=? WHERE id=?",
        (space_id, confidence, 1 if confirmed else 0, _now(), note_id),
    )
    conn.commit()


def flag_note(conn, note_id: int, confidence: float) -> None:
    # low-confidence: stays in the inbox "needs sorting", marked classified so it
    # isn't reprocessed
    conn.execute(
        "UPDATE notes SET confidence=?, classified_at=? WHERE id=?",
        (confidence, _now(), note_id),
    )
    conn.commit()


def set_suggestions(conn, note_id: int, suggestions: dict) -> None:
    conn.execute(
        "UPDATE notes SET suggestions=? WHERE id=?", (json.dumps(suggestions), note_id)
    )
    conn.commit()


def keep_note(conn, note_id: int) -> None:
    conn.execute("UPDATE notes SET confirmed=1 WHERE id=?", (note_id,))
    conn.commit()


def move_note(conn, note_id: int, space_id: int | None) -> None:
    if space_id is not None:
        conn.execute(
            "UPDATE notes SET space_id=?, status='filed', confirmed=1 WHERE id=?",
            (space_id, note_id),
        )
    else:
        conn.execute(
            "UPDATE notes SET space_id=NULL, status='inbox', confirmed=0 WHERE id=?",
            (note_id,),
        )
    conn.commit()


def delete_note(conn, note_id: int) -> None:
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
