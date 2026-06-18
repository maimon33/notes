from app import classifier, db


def make_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_process_inbox_files_top_above_threshold():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job stuff")
    nid = db.add_note(conn, "prep standup")

    def fake(body, spaces):
        return classifier.Classification(ranked=[classifier.Suggestion(sid, 0.95)], new_space=None)

    classifier.process_inbox(conn, fake, threshold=0.8)
    note = db.get_note(conn, nid)
    assert note["status"] == "filed"
    assert note["space_id"] == sid
    assert note["confirmed"] == 0  # auto-filed, awaiting Keep
    assert note["suggestions"]["ranked"][0]["space_id"] == sid


def test_process_inbox_leaves_low_confidence_in_inbox_with_suggestions():
    conn = make_conn()
    s1 = db.create_space(conn, "Work", "job")
    s2 = db.create_space(conn, "Ideas", "ideas")
    nid = db.add_note(conn, "hmm could be either")

    def fake(body, spaces):
        return classifier.Classification(
            ranked=[classifier.Suggestion(s1, 0.45), classifier.Suggestion(s2, 0.4)], new_space=None
        )

    classifier.process_inbox(conn, fake, threshold=0.8)
    note = db.get_note(conn, nid)
    assert note["status"] == "inbox"
    assert note["space_id"] is None
    assert note["classified_at"] is not None
    assert len(note["suggestions"]["ranked"]) == 2


def test_process_inbox_skips_private():
    conn = make_conn()
    db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "secret", private=True)
    calls = []

    def fake(body, spaces):
        calls.append(body)
        return classifier.Classification(ranked=[], new_space=None)

    classifier.process_inbox(conn, fake, threshold=0.8)
    assert calls == []  # private notes never reach the classifier
    assert db.get_note(conn, nid)["classified_at"] is None


def test_new_space_proposal_is_stored():
    conn = make_conn()
    nid = db.add_note(conn, "flight to Tokyo in March")

    def fake(body, spaces):
        return classifier.Classification(ranked=[], new_space={"name": "Travel", "purpose": "trips"})

    classifier.process_inbox(conn, fake, threshold=0.8)
    note = db.get_note(conn, nid)
    assert note["status"] == "inbox"
    assert note["suggestions"]["new_space"]["name"] == "Travel"


def test_invalid_space_ids_are_filtered_out():
    conn = make_conn()
    sid = db.create_space(conn, "Work", "job")
    nid = db.add_note(conn, "x")

    def fake(body, spaces):
        return classifier.Classification(ranked=[classifier.Suggestion(999, 0.99)], new_space=None)

    classifier.process_inbox(conn, fake, threshold=0.8)
    note = db.get_note(conn, nid)
    assert note["status"] == "inbox"  # 999 not a real space -> nothing filed
    assert note["suggestions"]["ranked"] == []
