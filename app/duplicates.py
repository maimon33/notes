from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
import re


@dataclass
class DuplicateGroup:
    keep_id: int
    duplicate_ids: list[int]
    pattern: str
    confidence: float
    source: str


def scan(notes: list[dict], analyze_with_ai=None) -> list[dict]:
    if len(notes) < 2:
        return []
    candidates = _candidate_groups(notes)
    if analyze_with_ai and candidates:
        try:
            ai_groups = analyze_with_ai(notes, candidates)
            if ai_groups:
                return _finalize_groups(notes, ai_groups, "ai")
        except Exception:
            pass
    return _finalize_groups(notes, candidates, "heuristic")


def _candidate_groups(notes: list[dict]) -> list[dict]:
    parent = {note["id"]: note["id"] for note in notes}
    note_map = {note["id"]: note for note in notes}
    reasons: dict[tuple[int, int], tuple[str, float]] = {}
    for left, right in combinations(notes, 2):
        reason = _pair_reason(left["body"], right["body"])
        if not reason:
            continue
        label, confidence = reason
        _union(parent, left["id"], right["id"])
        reasons[tuple(sorted((left["id"], right["id"])))] = (label, confidence)

    groups: dict[int, list[int]] = {}
    for note in notes:
        root = _find(parent, note["id"])
        groups.setdefault(root, []).append(note["id"])

    out = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        ids.sort(key=lambda note_id: (note_map[note_id]["created_at"], note_id))
        labels = []
        confidences = []
        for left, right in combinations(ids, 2):
            pair = reasons.get(tuple(sorted((left, right))))
            if pair:
                labels.append(pair[0])
                confidences.append(pair[1])
        pattern = labels[0] if labels else "very similar wording"
        confidence = max(confidences) if confidences else 0.8
        out.append({"keep_id": ids[0], "duplicate_ids": ids[1:], "pattern": pattern, "confidence": confidence})
    return out


def _pair_reason(left: str, right: str) -> tuple[str, float] | None:
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return None
    if a == b:
        return "same content after cleanup", 0.99
    ratio = SequenceMatcher(None, a, b).ratio()
    if ratio >= 0.94:
        return "almost identical wording", ratio
    toks_a = set(a.split())
    toks_b = set(b.split())
    overlap = len(toks_a & toks_b) / max(1, len(toks_a | toks_b))
    if overlap >= 0.8 and min(len(toks_a), len(toks_b)) >= 4:
        return "same idea with small wording changes", overlap
    return None


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[^\w\s:/.-]", "", text)
    return text


def _find(parent: dict[int, int], note_id: int) -> int:
    while parent[note_id] != note_id:
        parent[note_id] = parent[parent[note_id]]
        note_id = parent[note_id]
    return note_id


def _union(parent: dict[int, int], left: int, right: int) -> None:
    root_left = _find(parent, left)
    root_right = _find(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def _finalize_groups(notes: list[dict], groups: list[dict], source: str) -> list[dict]:
    note_map = {note["id"]: note for note in notes}
    final = []
    for group in groups:
        keep_id = int(group["keep_id"])
        duplicate_ids = [int(note_id) for note_id in group.get("duplicate_ids", []) if int(note_id) != keep_id]
        if not duplicate_ids:
            continue
        final.append(
            {
                "keep": note_map[keep_id],
                "duplicates": [note_map[note_id] for note_id in duplicate_ids if note_id in note_map],
                "pattern": (group.get("pattern") or "similar notes").strip(),
                "confidence": round(float(group.get("confidence") or 0.8), 2),
                "source": source,
            }
        )
    return final


AI_SYSTEM = (
    "You analyze notes and spot duplicate or near-duplicate entries. "
    "Group notes that clearly represent the same idea or same content, even if wording differs slightly. "
    "For each group choose one note to keep, list the duplicate note ids to remove, and describe the shared pattern briefly."
)


def ai_prompt(notes: list[dict], candidates: list[dict]) -> str:
    note_map = {note["id"]: note for note in notes}
    blocks = []
    for idx, group in enumerate(candidates, start=1):
        ids = [group["keep_id"], *group["duplicate_ids"]]
        lines = [f"Candidate group {idx}:"]
        for note_id in ids:
            note = note_map[note_id]
            lines.append(f"- id={note['id']} created_at={note['created_at']} body={note['body']!r}")
        blocks.append("\n".join(lines))
    return (
        "Review these candidate duplicate groups and keep only the ones that are truly duplicates.\n"
        "Return JSON with this shape: "
        '{"groups":[{"keep_id":123,"duplicate_ids":[456],"pattern":"same shopping list","confidence":0.96}]}.\n\n'
        + "\n\n".join(blocks)
    )
