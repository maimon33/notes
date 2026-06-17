import re

from app import db


def _matcher(query: str, regex: bool, case_sensitive: bool = False) -> re.Pattern:
    """Compile a search pattern. Literal queries are escaped; regex queries are
    used as-is (may raise re.error — callers should handle invalid patterns)."""
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = query if regex else re.escape(query)
    return re.compile(pattern, flags)


def _snippet(body: str, match: re.Match, pad: int = 32) -> str:
    start = max(0, match.start() - pad)
    end = min(len(body), match.end() + pad)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{body[start:end]}{suffix}"


def search(conn, query: str, regex: bool = False, case_sensitive: bool = False) -> list[dict]:
    """Return matching notes with match counts and snippets. Raises re.error on
    an invalid regex pattern."""
    if not query:
        return []
    pat = _matcher(query, regex, case_sensitive)
    out = []
    for row in conn.execute(
        "SELECT id, body, space_id, status FROM notes ORDER BY created_at DESC"
    ):
        matches = list(pat.finditer(row["body"]))
        if matches:
            out.append(
                {
                    "id": row["id"],
                    "body": row["body"],
                    "space_id": row["space_id"],
                    "status": row["status"],
                    "count": len(matches),
                    "snippets": [_snippet(row["body"], m) for m in matches[:3]],
                }
            )
    return out


def replace_in_text(
    body: str, query: str, replacement: str, regex: bool, case_sensitive: bool = False
) -> tuple[str, int]:
    """Replace occurrences in a single string. In literal mode the replacement is
    inserted verbatim (no backreference interpretation); in regex mode backrefs
    like \\1 are honored."""
    pat = _matcher(query, regex, case_sensitive)
    if regex:
        return pat.subn(replacement, body)
    return pat.subn(lambda _m: replacement, body)


def plan_replace(
    conn,
    note_ids: list[int],
    query: str,
    replacement: str,
    regex: bool,
    case_sensitive: bool = False,
) -> list[dict]:
    """Compute (but do not write) the changes for the given notes. Only notes
    that actually change are returned."""
    changes = []
    for nid in note_ids:
        note = db.get_note(conn, nid)
        if not note:
            continue
        new_body, n = replace_in_text(note["body"], query, replacement, regex, case_sensitive)
        if n > 0 and new_body != note["body"]:
            changes.append({"id": nid, "before": note["body"], "after": new_body, "n": n})
    return changes


def apply_replace(conn, changes: list[dict]) -> dict:
    for c in changes:
        conn.execute("UPDATE notes SET body=? WHERE id=?", (c["after"], c["id"]))
    conn.commit()
    return {
        "notes_changed": len(changes),
        "total": sum(c["n"] for c in changes),
    }
