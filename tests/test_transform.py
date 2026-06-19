from app import transform


def test_tighten_text_collapses_blank_lines():
    body = "hello   \n\n\n\nworld  "
    assert transform.tighten_text(body) == "hello\n\nworld"


def test_titleize_adds_heading():
    body = "follow up with design team about nav labels."
    out = transform.titleize_text(body)
    assert out.startswith("# Follow Up With Design Team")


def test_sort_text_groups_content():
    body = "todo fix mobile footer\nhttps://example.com\nWhat should we rename this?\nraw thought"
    out = transform.sort_text(body)
    assert "## Tasks" in out
    assert "## Links" in out
    assert "## Questions" in out
    assert "## Notes" in out
