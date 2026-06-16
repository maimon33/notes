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
