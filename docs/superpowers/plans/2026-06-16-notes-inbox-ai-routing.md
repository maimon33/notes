# Notes Inbox with AI Routing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A lightweight self-hosted web app where pasted notes land in an inbox and a background AI loop files them into user-defined spaces (or flags them when unsure), deployed on Railway with a Volume-backed SQLite DB and manual S3 backup.

**Architecture:** FastAPI app serving server-rendered HTML. SQLite single-file DB on a Railway Volume at `/data/notes.db`. An in-process background task polls the inbox and classifies notes with Claude Haiku 4.5 via structured output. A manual "Back up now" endpoint snapshots the DB with `VACUUM INTO` and uploads to S3-compatible storage.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Jinja2, stdlib `sqlite3`, `anthropic` SDK, `boto3`, `pytest`. Docker for Railway.

---

## File Structure

- `app/__init__.py` — package marker
- `app/db.py` — connection + schema + query helpers
- `app/classifier.py` — Claude classification call + inbox processing logic
- `app/backup.py` — VACUUM INTO snapshot + S3 upload + retention
- `app/config.py` — env-var config
- `app/main.py` — FastAPI app, routes, startup background task
- `app/templates/index.html` — single-page UI (inbox + spaces + backup button)
- `tests/test_db.py`, `tests/test_classifier.py`, `tests/test_backup.py`, `tests/test_api.py`
- `requirements.txt`, `Dockerfile`, `railway.toml`, `.env.example`, `.gitignore`, `README.md`

---

## Task 1: Project scaffold + config

**Files:**
- Create: `requirements.txt`, `.gitignore`, `app/__init__.py`, `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
anthropic==0.40.0
boto3==1.35.0
pytest==8.3.0
httpx==0.27.0
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.db
*.db-journal
data/
.venv/
```

- [ ] **Step 3: Create `app/__init__.py`** (empty file)

- [ ] **Step 4: Write the failing test** in `tests/test_config.py`

```python
import importlib
from app import config


def test_defaults(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("CLASSIFY_THRESHOLD", raising=False)
    importlib.reload(config)
    cfg = config.load()
    assert cfg.db_path == "/data/notes.db"
    assert cfg.classify_threshold == 0.8
    assert cfg.classify_interval_seconds == 30


def test_env_override(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("CLASSIFY_THRESHOLD", "0.5")
    cfg = config.load()
    assert cfg.db_path == "/tmp/x.db"
    assert cfg.classify_threshold == 0.5
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (`config.load` not defined)

- [ ] **Step 6: Implement `app/config.py`**

```python
import os
from dataclasses import dataclass


@dataclass
class Config:
    db_path: str
    classify_threshold: float
    classify_interval_seconds: int
    anthropic_api_key: str | None
    s3_bucket: str | None
    s3_region: str | None
    s3_endpoint_url: str | None
    backup_retention: int


def load() -> Config:
    return Config(
        db_path=os.getenv("DB_PATH", "/data/notes.db"),
        classify_threshold=float(os.getenv("CLASSIFY_THRESHOLD", "0.8")),
        classify_interval_seconds=int(os.getenv("CLASSIFY_INTERVAL_SECONDS", "30")),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        s3_bucket=os.getenv("S3_BUCKET"),
        s3_region=os.getenv("S3_REGION"),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        backup_retention=int(os.getenv("BACKUP_RETENTION", "7")),
    )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore app/__init__.py app/config.py tests/test_config.py
git commit -m "feat: project scaffold and config"
```

---

## Task 2: Database layer

**Files:**
- Create: `app/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test** in `tests/test_db.py`

```python
from app import db


def make_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_create_and_get_space():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "Anything about my job")
    spaces = db.list_spaces(conn)
    assert len(spaces) == 1
    assert spaces[0]["id"] == sid
    assert spaces[0]["name"] == "Work"
    assert spaces[0]["purpose"] == "Anything about my job"


def test_add_note_lands_in_inbox_unclassified():
    conn = make_conn()
    nid = db.add_note(conn, "buy milk")
    note = db.get_note(conn, nid)
    assert note["status"] == "inbox"
    assert note["space_id"] is None
    assert note["classified_at"] is None


def test_unclassified_notes_query():
    conn = make_conn()
    db.add_note(conn, "a")
    db.add_note(conn, "b")
    rows = db.unclassified_notes(conn)
    assert len(rows) == 2


def test_file_note_sets_space_and_status():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "standup at 9")
    db.file_note(conn, nid, space_id=sid, confidence=0.95)
    note = db.get_note(conn, nid)
    assert note["status"] == "filed"
    assert note["space_id"] == sid
    assert note["confidence"] == 0.95
    assert note["classified_at"] is not None
    # filed notes no longer appear as unclassified
    assert db.unclassified_notes(conn) == []


def test_flag_note_stays_in_inbox_but_marked_classified():
    conn = make_conn()
    nid = db.add_note(conn, "ambiguous")
    db.flag_note(conn, nid, confidence=0.4)
    note = db.get_note(conn, nid)
    assert note["status"] == "inbox"
    assert note["space_id"] is None
    assert note["confidence"] == 0.4
    assert note["classified_at"] is not None
    assert db.unclassified_notes(conn) == []


def test_move_note_manual():
    conn = make_conn()
    sid = db.create_space(conn, "Recipes", "food")
    nid = db.add_note(conn, "pasta")
    db.move_note(conn, nid, space_id=sid)
    note = db.get_note(conn, nid)
    assert note["status"] == "filed"
    assert note["space_id"] == sid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL (`db.connect` not defined)

- [ ] **Step 3: Implement `app/db.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: sqlite db layer for notes and spaces"
```

---

## Task 3: Classifier logic

**Files:**
- Create: `app/classifier.py`
- Test: `tests/test_classifier.py`

The Claude call is isolated in `classify_one`; the loop logic `process_inbox` takes an
injectable `classify_fn` so it can be tested without hitting the API.

- [ ] **Step 1: Write the failing test** in `tests/test_classifier.py`

```python
from app import db, classifier


def make_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_process_inbox_files_high_confidence():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job stuff")
    nid = db.add_note(conn, "prep standup")

    def fake_classify(body, spaces):
        return classifier.Classification(space_id=sid, confidence=0.95)

    classifier.process_inbox(conn, fake_classify, threshold=0.8)

    note = db.get_note(conn, nid)
    assert note["status"] == "filed"
    assert note["space_id"] == sid


def test_process_inbox_flags_low_confidence():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job stuff")
    nid = db.add_note(conn, "hmm")

    def fake_classify(body, spaces):
        return classifier.Classification(space_id=sid, confidence=0.3)

    classifier.process_inbox(conn, fake_classify, threshold=0.8)

    note = db.get_note(conn, nid)
    assert note["status"] == "inbox"
    assert note["space_id"] is None
    assert note["classified_at"] is not None


def test_process_inbox_skips_when_no_spaces():
    conn = make_conn()
    nid = db.add_note(conn, "orphan")
    calls = []

    def fake_classify(body, spaces):
        calls.append(body)
        return classifier.Classification(space_id=1, confidence=1.0)

    classifier.process_inbox(conn, fake_classify, threshold=0.8)

    assert calls == []  # never called classifier with no spaces
    note = db.get_note(conn, nid)
    assert note["classified_at"] is None  # still pending
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classifier.py -v`
Expected: FAIL (`classifier` has no `Classification`)

- [ ] **Step 3: Implement `app/classifier.py`**

```python
import json
from dataclasses import dataclass

from app import db


@dataclass
class Classification:
    space_id: int
    confidence: float


SYSTEM = (
    "You sort short notes into spaces. Each space has a name and a purpose. "
    "Pick the single best-matching space for the note and a confidence between "
    "0 and 1. If nothing fits well, return your best guess with low confidence."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "space_id": {"type": "integer"},
        "confidence": {"type": "number"},
    },
    "required": ["space_id", "confidence"],
    "additionalProperties": False,
}


def classify_one(body: str, spaces: list[dict], client) -> Classification:
    space_lines = "\n".join(f"- id={s['id']} {s['name']}: {s['purpose']}" for s in spaces)
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": f"Spaces:\n{space_lines}\n\nNote:\n{body}",
            }
        ],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    return Classification(space_id=int(data["space_id"]), confidence=float(data["confidence"]))


def process_inbox(conn, classify_fn, threshold: float) -> int:
    spaces = db.list_spaces(conn)
    if not spaces:
        return 0
    valid_ids = {s["id"] for s in spaces}
    processed = 0
    for note in db.unclassified_notes(conn):
        result = classify_fn(note["body"], spaces)
        if result.confidence >= threshold and result.space_id in valid_ids:
            db.file_note(conn, note["id"], result.space_id, result.confidence)
        else:
            db.flag_note(conn, note["id"], result.confidence)
        processed += 1
    return processed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classifier.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/classifier.py tests/test_classifier.py
git commit -m "feat: note classifier logic with injectable classify fn"
```

---

## Task 4: S3 backup

**Files:**
- Create: `app/backup.py`
- Test: `tests/test_backup.py`

- [ ] **Step 1: Write the failing test** in `tests/test_backup.py`

```python
import os
import sqlite3

from app import db, backup


def test_snapshot_creates_consistent_copy(tmp_path):
    src = str(tmp_path / "src.db")
    conn = db.connect(src)
    db.init_schema(conn)
    db.add_note(conn, "hello")

    dest = str(tmp_path / "snap.db")
    backup.make_snapshot(src, dest)

    assert os.path.exists(dest)
    snap = sqlite3.connect(dest)
    snap.row_factory = sqlite3.Row
    rows = snap.execute("SELECT body FROM notes").fetchall()
    assert rows[0]["body"] == "hello"


def test_run_backup_uploads_and_applies_retention(tmp_path):
    src = str(tmp_path / "src.db")
    conn = db.connect(src)
    db.init_schema(conn)

    uploaded = []
    deleted = []

    class FakeS3:
        def upload_file(self, filename, bucket, key):
            uploaded.append((bucket, key))

        def list_objects_v2(self, Bucket, Prefix):
            return {"Contents": [{"Key": f"{Prefix}old-{i}.db"} for i in range(10)]}

        def delete_object(self, Bucket, Key):
            deleted.append(Key)

    key = backup.run_backup(
        src, FakeS3(), bucket="mybucket", retention=7, now_iso="2026-06-16T12:00:00"
    )

    assert uploaded == [("mybucket", key)]
    assert key.startswith("notes-")
    assert key.endswith(".db")
    # 10 existing + this one = 11; keep 7 newest, delete 4 oldest
    assert len(deleted) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backup.py -v`
Expected: FAIL (`backup.make_snapshot` not defined)

- [ ] **Step 3: Implement `app/backup.py`**

```python
import os
import sqlite3
import tempfile


def make_snapshot(src_path: str, dest_path: str) -> None:
    conn = sqlite3.connect(src_path)
    try:
        conn.execute("VACUUM INTO ?", (dest_path,))
    finally:
        conn.close()


def run_backup(db_path: str, s3_client, bucket: str, retention: int, now_iso: str) -> str:
    key = f"notes-{now_iso}.db"
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "snapshot.db")
        make_snapshot(db_path, snap)
        s3_client.upload_file(snap, bucket, key)

    _apply_retention(s3_client, bucket, retention)
    return key


def _apply_retention(s3_client, bucket: str, retention: int) -> None:
    resp = s3_client.list_objects_v2(Bucket=bucket, Prefix="notes-")
    keys = sorted(obj["Key"] for obj in resp.get("Contents", []))
    excess = len(keys) - retention
    for key in keys[:max(0, excess)]:
        s3_client.delete_object(Bucket=bucket, Key=key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backup.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/backup.py tests/test_backup.py
git commit -m "feat: sqlite VACUUM INTO snapshot and s3 backup with retention"
```

---

## Task 5: FastAPI app + routes

**Files:**
- Create: `app/main.py`, `app/templates/index.html`
- Test: `tests/test_api.py`

Routes:
- `GET /` — render inbox + spaces
- `POST /notes` — add note (form field `body`)
- `POST /spaces` — add space (`name`, `purpose`)
- `POST /spaces/{id}/delete` — delete space
- `POST /notes/{id}/move` — manual move (`space_id`, empty = back to inbox)
- `POST /backup` — run manual backup
- `GET /healthz` — health check

The app exposes `app.state.conn`. Tests override config to use an in-memory DB and
disable the background loop.

- [ ] **Step 1: Write the failing test** in `tests/test_api.py`

```python
from fastapi.testclient import TestClient

from app import db
import app.main as main


def client_with_memory(monkeypatch):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    monkeypatch.setattr(main, "_start_background", lambda app: None)
    app = main.create_app(conn=conn)
    return TestClient(app), conn


def test_healthz(monkeypatch):
    client, _ = client_with_memory(monkeypatch)
    assert client.get("/healthz").json() == {"ok": True}


def test_add_note_then_shows_in_inbox(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    r = client.post("/notes", data={"body": "buy milk"}, follow_redirects=False)
    assert r.status_code == 303
    assert db.inbox_notes(conn)[0]["body"] == "buy milk"


def test_add_space(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    r = client.post("/spaces", data={"name": "Work", "purpose": "job"}, follow_redirects=False)
    assert r.status_code == 303
    assert db.list_spaces(conn)[0]["name"] == "Work"


def test_move_note_to_space(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    sid = db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "standup")
    r = client.post(f"/notes/{nid}/move", data={"space_id": str(sid)}, follow_redirects=False)
    assert r.status_code == 303
    assert db.get_note(conn, nid)["space_id"] == sid


def test_index_renders(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    db.add_note(conn, "hello world note")
    html = client.get("/").text
    assert "hello world note" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL (`app.main` import error / `create_app` missing)

- [ ] **Step 3: Implement `app/templates/index.html`**

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Notes</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
    textarea { width: 100%; height: 5rem; }
    .space { border: 1px solid #ddd; border-radius: 6px; padding: .75rem; margin: .5rem 0; }
    .note { padding: .4rem 0; border-bottom: 1px solid #eee; }
    .flagged { color: #b15; }
    button { cursor: pointer; }
    form.inline { display: inline; }
  </style>
</head>
<body>
  <h1>Notes</h1>

  <form method="post" action="/notes">
    <textarea name="body" placeholder="Dump a note..." required></textarea>
    <button type="submit">Add to inbox</button>
  </form>

  <form method="post" action="/backup">
    <button type="submit">Back up now</button>
  </form>
  {% if backup_msg %}<p>{{ backup_msg }}</p>{% endif %}

  <h2>Inbox ({{ inbox|length }})</h2>
  {% for n in inbox %}
    <div class="note {% if n.classified_at %}flagged{% endif %}">
      {{ n.body }}
      {% if n.classified_at %}<small>(unsure, conf {{ '%.2f'|format(n.confidence or 0) }})</small>{% endif %}
      {% if spaces %}
      <form class="inline" method="post" action="/notes/{{ n.id }}/move">
        <select name="space_id">
          <option value="">— move to —</option>
          {% for s in spaces %}<option value="{{ s.id }}">{{ s.name }}</option>{% endfor %}
        </select>
        <button type="submit">Move</button>
      </form>
      {% endif %}
    </div>
  {% endfor %}

  <h2>Spaces</h2>
  <form method="post" action="/spaces">
    <input name="name" placeholder="Name" required>
    <input name="purpose" placeholder="Purpose (what belongs here)" required>
    <button type="submit">Add space</button>
  </form>
  {% for s in spaces %}
    <div class="space">
      <strong>{{ s.name }}</strong> — {{ s.purpose }}
      <form class="inline" method="post" action="/spaces/{{ s.id }}/delete">
        <button type="submit">Delete</button>
      </form>
      {% for n in s.notes %}<div class="note">{{ n.body }}</div>{% endfor %}
    </div>
  {% endfor %}
</body>
</html>
```

- [ ] **Step 4: Implement `app/main.py`**

```python
import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import boto3
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import backup, classifier, config, db

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(conn=None, cfg=None) -> FastAPI:
    cfg = cfg or config.load()
    if conn is None:
        conn = db.connect(cfg.db_path)
        db.init_schema(conn)

    app = FastAPI()
    app.state.conn = conn
    app.state.cfg = cfg
    app.state.backup_msg = None

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def index(request: Request):
        spaces = db.list_spaces(conn)
        for s in spaces:
            s["notes"] = db.notes_in_space(conn, s["id"])
        msg = app.state.backup_msg
        app.state.backup_msg = None
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"inbox": db.inbox_notes(conn), "spaces": spaces, "backup_msg": msg},
        )

    @app.post("/notes")
    def add_note(body: str = Form(...)):
        db.add_note(conn, body)
        return RedirectResponse("/", status_code=303)

    @app.post("/spaces")
    def add_space(name: str = Form(...), purpose: str = Form(...)):
        db.create_space(conn, name, purpose)
        return RedirectResponse("/", status_code=303)

    @app.post("/spaces/{space_id}/delete")
    def del_space(space_id: int):
        db.delete_space(conn, space_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/notes/{note_id}/move")
    def move(note_id: int, space_id: str = Form("")):
        db.move_note(conn, note_id, int(space_id) if space_id else None)
        return RedirectResponse("/", status_code=303)

    @app.post("/backup")
    def do_backup():
        if not cfg.s3_bucket:
            app.state.backup_msg = "Backup not configured (no S3_BUCKET)."
            return RedirectResponse("/", status_code=303)
        s3 = boto3.client(
            "s3", region_name=cfg.s3_region, endpoint_url=cfg.s3_endpoint_url
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        try:
            key = backup.run_backup(cfg.db_path, s3, cfg.s3_bucket, cfg.backup_retention, now)
            app.state.backup_msg = f"Backed up to {key}"
        except Exception as e:  # surface failure to the user
            app.state.backup_msg = f"Backup failed: {e}"
        return RedirectResponse("/", status_code=303)

    _start_background(app)
    return app


def _start_background(app: FastAPI) -> None:
    cfg = app.state.cfg
    conn = app.state.conn
    if not cfg.anthropic_api_key:
        return
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    def classify_fn(body, spaces):
        return classifier.classify_one(body, spaces, client)

    def loop():
        import time
        while True:
            try:
                classifier.process_inbox(conn, classify_fn, cfg.classify_threshold)
            except Exception:
                pass
            time.sleep(cfg.classify_interval_seconds)

    threading.Thread(target=loop, daemon=True).start()


app = create_app() if __name__ != "__main__" else None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tasks' tests)

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/templates/index.html tests/test_api.py
git commit -m "feat: fastapi app, routes, ui, background classifier loop"
```

---

## Task 6: Deployment files

**Files:**
- Create: `Dockerfile`, `railway.toml`, `.env.example`, `README.md`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

- [ ] **Step 2: Create `railway.toml`**

```toml
[build]
builder = "dockerfile"

[deploy]
healthcheckPath = "/healthz"
restartPolicyType = "on_failure"

[[deploy.volumes]]
mountPath = "/data"
name = "notes-data"
```

- [ ] **Step 3: Create `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-...
DB_PATH=/data/notes.db
CLASSIFY_THRESHOLD=0.8
CLASSIFY_INTERVAL_SECONDS=30
S3_BUCKET=
S3_REGION=
S3_ENDPOINT_URL=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
BACKUP_RETENTION=7
```

- [ ] **Step 4: Create `README.md`**

```markdown
# Notes — AI-routed inbox

Dump notes into one inbox; a background AI loop files them into spaces you define,
or flags them when unsure. FastAPI + SQLite, deployed on Railway with a Volume.

## Local dev

    pip install -r requirements.txt
    DB_PATH=./data/notes.db ANTHROPIC_API_KEY=sk-... uvicorn app.main:app --reload

Visit http://localhost:8000

## Tests

    python -m pytest -v

## Deploy (Railway)

1. `railway up` (or connect the GitHub repo for auto-deploy)
2. Set variables: `ANTHROPIC_API_KEY`, and optionally `S3_BUCKET`/`S3_REGION`/
   `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` for backups.
3. A Volume is mounted at `/data` (see `railway.toml`) — SQLite lives there and
   survives restarts/redeploys.

Backups are manual via the "Back up now" button.
```

- [ ] **Step 5: Verify Docker build locally** (if Docker available)

Run: `docker build -t notes . && docker run --rm -e PORT=8000 -p 8000:8000 notes`
Expected: container starts, `curl localhost:8000/healthz` → `{"ok":true}`
(If Docker unavailable, skip — Railway will build it.)

- [ ] **Step 6: Commit**

```bash
git add Dockerfile railway.toml .env.example README.md
git commit -m "chore: railway deployment files"
```

---

## Self-Review Notes

- **Spec coverage:** capture (Task 5 `/notes`), inbox+classify loop (Tasks 3+5), auto-file/flag threshold (Task 3), spaces CRUD (Tasks 2+5), manual move (Tasks 2+5), Volume SQLite (Task 6 `railway.toml` + `DB_PATH` default), manual S3 backup with retention + configurable endpoint (Tasks 4+5), Haiku 4.5 + structured output (Task 3), health check for Railway (Task 5). All spec sections map to a task.
- **Deferred items** (email/Slack, merge, cleanup, attachments, auth, scheduled backup, client-side creds) are intentionally absent.
- **Type consistency:** `Classification(space_id, confidence)`, `process_inbox(conn, classify_fn, threshold)`, `classify_one(body, spaces, client)`, `run_backup(db_path, s3_client, bucket, retention, now_iso)`, `make_snapshot(src, dest)` used consistently across tasks and tests.
