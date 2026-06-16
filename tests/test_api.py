from fastapi.testclient import TestClient

import app.main as main
from app import db


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
