import json
import logging
from dataclasses import dataclass, field

from app import db

log = logging.getLogger("notes")


@dataclass
class Suggestion:
    space_id: int
    confidence: float


@dataclass
class Classification:
    ranked: list[Suggestion] = field(default_factory=list)
    new_space: dict | None = None  # {"name": str, "purpose": str} or None


SYSTEM = (
    "You sort short personal notes into spaces. Each space has an id, a name, and a "
    "purpose. Return up to 5 candidate spaces ranked best-first, each with a confidence "
    "from 0 to 1. If no existing space is a good fit, propose ONE new space that matches "
    "the note's tone (a short name and a one-line purpose) in `new_space`. If an existing "
    "space fits well, set new_space.name and new_space.purpose to empty strings."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "ranked": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "space_id": {"type": "integer"},
                    "confidence": {"type": "number"},
                },
                "required": ["space_id", "confidence"],
                "additionalProperties": False,
            },
        },
        "new_space": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "purpose": {"type": "string"},
            },
            "required": ["name", "purpose"],
            "additionalProperties": False,
        },
    },
    "required": ["ranked", "new_space"],
    "additionalProperties": False,
}


def classify_one(body: str, spaces: list[dict], ask_json) -> Classification:
    space_lines = "\n".join(f"- id={s['id']} {s['name']}: {s['purpose']}" for s in spaces) or "(no spaces yet)"
    data = ask_json(
        SYSTEM,
        "Return JSON matching this schema: "
        + json.dumps(SCHEMA, separators=(",", ":"))
        + f"\n\nSpaces:\n{space_lines}\n\nNote:\n{body}",
    )
    ranked = [Suggestion(int(r["space_id"]), float(r["confidence"])) for r in data.get("ranked", [])][:5]
    ns = data.get("new_space") or {}
    new_space = None
    if ns.get("name", "").strip():
        new_space = {"name": ns["name"].strip(), "purpose": ns.get("purpose", "").strip()}
    return Classification(ranked=ranked, new_space=new_space)


def process_inbox(conn, classify_fn, threshold: float) -> int:
    spaces = db.list_spaces(conn)
    valid = {s["id"] for s in spaces}
    processed = 0
    for note in db.unclassified_notes(conn):
        try:
            result = classify_fn(note["body"], spaces)
        except Exception:
            # one bad note (API/schema/key error) must not stall the batch — log and skip
            log.exception("classify failed for note %s", note["id"])
            continue
        ranked = [s for s in result.ranked if s.space_id in valid][:5]
        suggestions = {
            "ranked": [{"space_id": s.space_id, "confidence": s.confidence} for s in ranked],
            "new_space": result.new_space,
        }
        top = ranked[0] if ranked else None
        if top and top.confidence >= threshold:
            db.file_note(conn, note["id"], top.space_id, top.confidence, confirmed=False)
        else:
            db.flag_note(conn, note["id"], top.confidence if top else 0.0)
        db.set_suggestions(conn, note["id"], suggestions)
        processed += 1
    return processed
