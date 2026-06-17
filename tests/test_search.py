import re

import pytest

from app import db, search


def make_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_literal_search_case_insensitive():
    conn = make_conn()
    db.add_note(conn, "Buy MILK and bread")
    db.add_note(conn, "unrelated")
    results = search.search(conn, "milk")
    assert len(results) == 1
    assert results[0]["count"] == 1


def test_regex_search():
    conn = make_conn()
    db.add_note(conn, "call 555-1234 today")
    db.add_note(conn, "no numbers here")
    results = search.search(conn, r"\d{3}-\d{4}", regex=True)
    assert len(results) == 1
    assert results[0]["count"] == 1


def test_invalid_regex_raises():
    conn = make_conn()
    db.add_note(conn, "anything")
    with pytest.raises(re.error):
        search.search(conn, "(unclosed", regex=True)


def test_literal_replacement_is_verbatim():
    # backslashes in the replacement must not be treated as backrefs in literal mode
    new, n = search.replace_in_text("a todo b", "todo", r"\1 done", regex=False)
    assert n == 1
    assert new == r"a \1 done b"


def test_regex_replacement_honors_backrefs():
    new, n = search.replace_in_text("2026-06-17", r"(\d{4})-(\d{2})", r"\2/\1", regex=True)
    assert n == 1
    assert new == "06/2026-17"


def test_plan_and_apply_replace():
    conn = make_conn()
    n1 = db.add_note(conn, "todo: milk; todo: eggs")
    n2 = db.add_note(conn, "nothing to change")
    changes = search.plan_replace(conn, [n1, n2], "todo", "DONE", regex=False)
    # only the changed note is planned
    assert len(changes) == 1
    assert changes[0]["id"] == n1
    assert changes[0]["n"] == 2
    # nothing written yet
    assert db.get_note(conn, n1)["body"] == "todo: milk; todo: eggs"
    result = search.apply_replace(conn, changes)
    assert result == {"notes_changed": 1, "total": 2}
    assert db.get_note(conn, n1)["body"] == "DONE: milk; DONE: eggs"
    assert db.get_note(conn, n2)["body"] == "nothing to change"
