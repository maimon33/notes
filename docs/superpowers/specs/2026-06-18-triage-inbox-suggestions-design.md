# Triage Inbox, Ranked Suggestions & Private Notes — Design Spec

**Date:** 2026-06-18
**Status:** Approved design, pre-implementation
**Builds on:** 2026-06-16-notes-inbox-ai-routing-design.md

## Purpose

Turn the inbox into a true triage queue. The AI proposes ranked target spaces
(and can propose a brand-new space); the user confirms (**Keep**) or re-routes
(**Move**) with one click. Notes can be marked **Private (no AI)**. Inbox notes
default to collapsed. The whole UI gets a real mobile pass.

## Core behavior (hybrid — extends current loop)

The classifier returns, per note, **ranked suggestions** (1–5 `{space_id, confidence}`)
plus an optional **proposed new space** `{name, purpose}` when nothing fits well.

Note review states (inbox only):
- **Recently filed** — top confidence ≥ `CLASSIFY_THRESHOLD` (0.8): auto-filed into
  that space (`status='filed'`) but `confirmed=0`, so it still appears in the inbox
  awaiting a verdict.
- **Needs sorting** — top confidence < threshold: stays `status='inbox'`, shows the
  candidate chips.
- **Private / pending** — `private=1` notes (never classified) and notes not yet
  processed (`classified_at IS NULL`).

A note leaves the inbox only when `confirmed=1`.

## Actions (one-click, no dropdown)

- **Keep** — `confirmed=1`; note leaves the inbox, stays in its space.
- **Move** — reveals one-click chips: the AI's 1–5 candidate spaces + a `＋ New: <name>`
  chip (when the AI proposed one — creates the space and files in one tap) + an
  "Inbox" fallback. Choosing a chip sets `space_id`, `status='filed'`, `confirmed=1`.
- The same chip row serves "Needs sorting" notes.

## Private notes

Composer gets a **Private (no AI)** toggle. Private notes: `private=1`,
`classified_at` stays NULL but the classifier skips them (filtered by `private=0`),
no suggestions, shown in the Private section with a lock marker. They can be moved
manually like any note.

## Inbox UI

- Notes render **collapsed by default** (one-line preview) in the inbox; tap to expand
  (full body + actions). Space views keep full cards (collapse is inbox-only).
- Three labelled sections in order: Recently filed → Needs sorting → Private & pending.

## Mobile

- Off-canvas sidebar with a tap-to-close backdrop.
- Full-width composer and cards; chips/Keep/Move sized as comfortable tap targets.
- Search panel full-width; modal fits small viewports; safe-area insets.

## Data model

`notes` gains:
- `private INTEGER NOT NULL DEFAULT 0`
- `confirmed INTEGER NOT NULL DEFAULT 0`
- `suggestions TEXT` — JSON: `{"ranked": [{"space_id", "confidence"}], "new_space": {"name","purpose"}|null}`

**Migration:** `init_schema` adds any missing column via `ALTER TABLE` (idempotent),
so the live SQLite DB on the Railway volume upgrades in place with no data loss.
Existing filed notes are treated as `confirmed=1` (back-fill) so they don't reappear
in the inbox.

## Classifier

- `classify_one` returns the ranked structure via structured output (Haiku 4.5):
  `{"ranked": [{space_id, confidence} ...≤5], "new_space": {name, purpose} | null}`.
- `process_inbox` skips `private=1`, stores `suggestions`, and sets state:
  top ≥ threshold → file + `confirmed=0`; else leave in inbox; always set `classified_at`.

## Endpoints

- `POST /notes` — add `private` form field.
- `POST /notes/{id}/keep` — set `confirmed=1`.
- `POST /notes/{id}/file` — `{space_id}` (existing space) → file + confirm.
- `POST /notes/{id}/file-new` — `{name, purpose}` → create space, file + confirm.
- `POST /notes/{id}/move` — existing (back to inbox / other) retained.

## Testing

- Migration adds columns and back-fills `confirmed` for existing filed notes.
- Ranked-suggestion parse from a mocked Claude response.
- `process_inbox` skips private; files top≥threshold with `confirmed=0`; leaves low.
- keep / file / file-new endpoints set state correctly.
- Inbox grouping query returns the right notes per section.

## Out of scope (unchanged)

Auto-confirm aging (Recently filed stays until Keep), email/Slack ingest, merge/cleanup,
attachments, multi-user, scheduled backups.
