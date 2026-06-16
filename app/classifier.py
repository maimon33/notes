import json
from dataclasses import dataclass

from app import db


@dataclass
class Classification:
    space_id: int
    confidence: float


SYSTEM = (
    "You sort short notes into spaces. Each space has a name and a purpose. "
    "Pick the single best-matching space for the note and a confidence between "
    "0 and 1. If nothing fits well, return your best guess with low confidence."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "space_id": {"type": "integer"},
        "confidence": {"type": "number"},
    },
    "required": ["space_id", "confidence"],
    "additionalProperties": False,
}


def classify_one(body: str, spaces: list[dict], client) -> Classification:
    space_lines = "\n".join(f"- id={s['id']} {s['name']}: {s['purpose']}" for s in spaces)
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": f"Spaces:\n{space_lines}\n\nNote:\n{body}",
            }
        ],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    return Classification(space_id=int(data["space_id"]), confidence=float(data["confidence"]))


def process_inbox(conn, classify_fn, threshold: float) -> int:
    spaces = db.list_spaces(conn)
    if not spaces:
        return 0
    valid_ids = {s["id"] for s in spaces}
    processed = 0
    for note in db.unclassified_notes(conn):
        result = classify_fn(note["body"], spaces)
        if result.confidence >= threshold and result.space_id in valid_ids:
            db.file_note(conn, note["id"], result.space_id, result.confidence)
        else:
            db.flag_note(conn, note["id"], result.confidence)
        processed += 1
    return processed
