import re


def tighten_text(body: str) -> str:
    lines = [line.rstrip() for line in body.splitlines()]
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def titleize_text(body: str) -> str:
    text = tighten_text(body)
    if not text:
        return text
    first = text.splitlines()[0].strip()
    if first.startswith("#"):
        return text
    sentence = re.split(r"[.!?\n]", text, maxsplit=1)[0].strip()
    words = sentence.split()[:6] or ["Untitled", "note"]
    title = " ".join(words).strip(" -:").title()
    return f"# {title}\n\n{text}"


def organize_text(body: str) -> str:
    text = tighten_text(body)
    if not text:
        return text
    if text.startswith("#"):
        return text
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 1:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = [" ".join(sentences[i:i + 2]).strip() for i in range(0, len(sentences), 2)]
        paras = [chunk for chunk in chunks if chunk]
    sections = []
    for i, para in enumerate(paras, start=1):
        sections.append(f"## Section {i}\n{para}")
    return "\n\n".join(sections)


def sort_text(body: str) -> str:
    text = tighten_text(body)
    if not text:
        return text
    buckets = {"Tasks": [], "Questions": [], "Links": [], "Notes": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if "http://" in lower or "https://" in lower or "www." in lower:
            buckets["Links"].append(line)
        elif line.endswith("?"):
            buckets["Questions"].append(line)
        elif re.match(r"^(- |\* |\d+\.)", line) or any(lower.startswith(prefix) for prefix in (
            "todo", "fix", "call", "email", "send", "buy", "review", "follow up", "ship"
        )):
            buckets["Tasks"].append(line)
        else:
            buckets["Notes"].append(line)

    parts = []
    for name in ("Tasks", "Questions", "Links", "Notes"):
        if not buckets[name]:
            continue
        parts.append(f"## {name}\n" + "\n".join(buckets[name]))
    return "\n\n".join(parts) if parts else text


def dedupe_text(body: str) -> str:
    text = tighten_text(body)
    if not text:
        return text

    sections = [section.strip() for section in re.split(r"\n\s*\n", text) if section.strip()]
    if len(sections) > 1:
        kept_sections = []
        seen_sections = set()
        for section in sections:
            normalized = _normalize_duplicate_key(section)
            if normalized in seen_sections:
                continue
            seen_sections.add(normalized)
            kept_sections.append(section)
        return "\n\n".join(_dedupe_lines(section) for section in kept_sections)

    return _dedupe_lines(text)


def _dedupe_lines(text: str) -> str:
    lines = text.splitlines()
    kept = []
    seen = set()
    for line in lines:
        normalized = _normalize_duplicate_key(line)
        if normalized and normalized in seen:
            continue
        if normalized:
            seen.add(normalized)
        kept.append(line)
    return "\n".join(kept).strip()


def _normalize_duplicate_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def apply_transform(body: str, mode: str) -> str:
    transforms = {
        "dedupe": dedupe_text,
        "tighten": tighten_text,
        "organize": organize_text,
        "sort": sort_text,
        "titleize": titleize_text,
    }
    fn = transforms.get(mode)
    if fn is None:
        raise ValueError(f"Unknown transform mode: {mode}")
    return fn(body)
