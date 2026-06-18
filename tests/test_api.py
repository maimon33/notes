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
    pending = db.private_and_pending(conn)
    assert pending[0]["body"] == "buy milk"
    assert pending[0]["private"] == 0


def test_add_private_note(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    r = client.post("/notes", data={"body": "secret", "private": "on"}, follow_redirects=False)
    assert r.status_code == 303
    note = db.private_and_pending(conn)[0]
    assert note["private"] == 1
    # private notes are never handed to the classifier
    assert db.unclassified_notes(conn) == []


def test_add_space(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    r = client.post("/spaces", data={"name": "Work", "purpose": "job"}, follow_redirects=False)
    assert r.status_code == 303
    assert db.list_spaces(conn)[0]["name"] == "Work"


def test_keep_endpoint(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    sid = db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "standup")
    db.file_note(conn, nid, sid, 0.9, confirmed=False)
    r = client.post(f"/notes/{nid}/keep", follow_redirects=False)
    assert r.status_code == 303
    assert db.get_note(conn, nid)["confirmed"] == 1


def test_file_endpoint(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    sid = db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "standup")
    r = client.post(f"/notes/{nid}/file", data={"space_id": str(sid)}, follow_redirects=False)
    assert r.status_code == 303
    note = db.get_note(conn, nid)
    assert note["space_id"] == sid
    assert note["status"] == "filed"
    assert note["confirmed"] == 1


def test_file_new_endpoint_creates_space(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    nid = db.add_note(conn, "flight to Tokyo")
    r = client.post(f"/notes/{nid}/file-new", data={"name": "Travel", "purpose": "trips"}, follow_redirects=False)
    assert r.status_code == 303
    spaces = db.list_spaces(conn)
    assert any(s["name"] == "Travel" for s in spaces)
    note = db.get_note(conn, nid)
    assert note["status"] == "filed"
    assert note["confirmed"] == 1


def test_index_renders(monkeypatch):
    client, conn = client_with_memory(monkeypatch)
    db.add_note(conn, "hello world note")
    html = client.get("/").text
    assert "hello world note" in html
