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
    assert note["confirmed"] == 1  # a manual move is an explicit confirmation


def test_private_note_skipped_by_classifier_query():
    conn = make_conn()
    db.add_note(conn, "public")
    db.add_note(conn, "secret", private=True)
    rows = db.unclassified_notes(conn)
    assert len(rows) == 1
    assert rows[0]["body"] == "public"


def test_inbox_groups():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job")
    n_unconf = db.add_note(conn, "auto filed")
    db.file_note(conn, n_unconf, sid, 0.9, confirmed=False)
    n_conf = db.add_note(conn, "already kept")
    db.file_note(conn, n_conf, sid, 0.9, confirmed=True)
    n_sort = db.add_note(conn, "unsure")
    db.flag_note(conn, n_sort, 0.4)
    n_priv = db.add_note(conn, "secret", private=True)
    n_pend = db.add_note(conn, "not processed yet")

    assert [n["id"] for n in db.recently_filed(conn)] == [n_unconf]
    assert [n["id"] for n in db.needs_sorting(conn)] == [n_sort]
    pp = {n["id"] for n in db.private_and_pending(conn)}
    assert pp == {n_priv, n_pend}


def test_keep_note_clears_from_recently_filed():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "x")
    db.file_note(conn, nid, sid, 0.9, confirmed=False)
    assert [n["id"] for n in db.recently_filed(conn)] == [nid]
    db.keep_note(conn, nid)
    assert db.recently_filed(conn) == []
    assert db.get_note(conn, nid)["confirmed"] == 1


def test_migration_adds_columns_and_backfills_confirmed():
    # simulate an old DB created before private/confirmed/suggestions existed
    conn = db.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE spaces (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, purpose TEXT, created_at TEXT);
        CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT, status TEXT,
            space_id INTEGER, confidence REAL, classified_at TEXT, created_at TEXT);
        """
    )
    conn.execute("INSERT INTO notes (body, status, created_at) VALUES ('old filed', 'filed', 't')")
    conn.commit()

    db.init_schema(conn)  # runs the in-place migration

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(notes)")}
    assert {"private", "confirmed", "suggestions"} <= cols
    # existing filed note is back-filled as confirmed so it won't flood the inbox
    assert db.get_note(conn, 1)["confirmed"] == 1
    assert db.recently_filed(conn) == []
