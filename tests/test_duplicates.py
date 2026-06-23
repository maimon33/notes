from app import db, duplicates


def make_note(conn, body: str) -> dict:
    note_id = db.add_note(conn, body)
    return db.get_note(conn, note_id)


def make_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_heuristic_duplicate_scan_groups_similar_notes():
    conn = make_conn()
    notes = [
        make_note(conn, "Buy milk and eggs"),
        make_note(conn, "Buy milk and eggs"),
        make_note(conn, "Standup at 10"),
    ]
    groups = duplicates.scan(notes)
    assert len(groups) == 1
    assert groups[0]["keep"]["body"] == "Buy milk and eggs"
    assert len(groups[0]["duplicates"]) == 1


def test_duplicate_scan_uses_ai_groups_when_available():
    conn = make_conn()
    notes = [
        make_note(conn, "Call Alice tomorrow morning"),
        make_note(conn, "Call Alice tomorrow morning please"),
    ]

    def fake_ai(all_notes, candidates):
        assert candidates
        return [{"keep_id": all_notes[0]["id"], "duplicate_ids": [all_notes[1]["id"]], "pattern": "same reminder", "confidence": 0.97}]

    groups = duplicates.scan(notes, analyze_with_ai=fake_ai)
    assert groups[0]["source"] == "ai"
    assert groups[0]["pattern"] == "same reminder"
