from app import classifier, db


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

    assert calls == []
    note = db.get_note(conn, nid)
    assert note["classified_at"] is None
