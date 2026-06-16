# Notes Inbox with AI Routing — Design Spec

**Date:** 2026-06-16
**Status:** Approved design, pre-implementation

## Purpose

A lightweight, free, self-hosted web app for centrally dumping notes. Everything
lands in a single **inbox**; a background process classifies each note with AI and
either auto-files it into a user-defined **space** (when confident) or leaves it
flagged in the inbox (when unsure). The opposite of heavy tools like Reflect/Notion/Obsidian —
the wedge is "dump and forget, AI files it."

## Constraints & Principles

- **Single-user now, multi-user-ready later.** No auth in v1, but avoid choices that block it.
- **Lightweight & free.** Smallest thing that works. No speculative features.
- **Text-only notes** in v1 (markdown allowed). No attachments.
- **User stays in control.** Spaces are defined by the user; classification is predictable.

## Stack

- **Backend:** Python + FastAPI
- **Storage:** SQLite, single file on a **Railway Volume** (`/data/notes.db`)
- **Frontend:** server-rendered HTML (no heavy JS framework)
- **AI:** Claude Haiku 4.5 (`claude-haiku-4-5`) via the Anthropic SDK
- **Hosting:** Railway (CLI or GitHub deploy)
- **Backup target:** S3-compatible object storage (AWS S3, R2, B2, GCS S3 endpoint)

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────┐
│  Web UI     │────▶│  API server  │────▶│  SQLite @ /data      │
│ textbox +   │     │  (FastAPI)   │     │  (Railway Volume)    │
│ space list +│◀────│              │     │  notes + spaces      │
│ "Back up"   │     │              │     │                      │
└─────────────┘     └──────┬───────┘     └─────────────────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
        ┌───────▼────────┐   ┌────────▼─────────┐
        │ classifier loop │   │ S3 backup (manual│
        │ polls inbox →   │   │ button) → VACUUM │
        │ Claude → file   │   │ INTO snapshot →  │
        │ or flag         │   │ upload to S3     │
        └─────────────────┘   └──────────────────┘
```

### Persistence model

- **Railway Volume** = primary storage. Survives container restarts, redeploys, crashes.
- **S3 backup** = off-site disaster recovery + portability. Not primary storage.

## Data Model (SQLite)

**`spaces`**
- `id` (pk)
- `name` (text)
- `purpose` (text) — the description the AI matches notes against
- `created_at`

**`notes`**
- `id` (pk)
- `body` (text)
- `status` (`inbox` | `filed`)
- `space_id` (nullable fk → spaces)
- `confidence` (nullable float) — last classification confidence
- `classified_at` (nullable) — null = not yet classified
- `created_at`

Single-user-now, multi-user-later: no `user_id` column in v1, but the schema is
small enough to add one later without restructuring.

## Components

### 1. Capture
A textbox in the web UI. Submit → new `notes` row, `status='inbox'`,
`classified_at=NULL`. That's the only capture channel in v1. Inbox is
channel-agnostic, so email/Slack are purely additive later.

### 2. Classifier loop
An in-process periodic task (no external queue/service). Every N seconds:
1. Select inbox notes where `classified_at IS NULL`.
2. For each, call Claude with: the note body + the list of spaces (name + purpose).
3. Use **structured output** to get back `{space_id, confidence}` reliably.
4. If `confidence >= THRESHOLD` (config, default 0.8): set `space_id`, `status='filed'`.
   Else: leave in inbox, store `confidence` and `classified_at` so it shows as
   "reviewed, unsure" (flagged) rather than reprocessing forever.

**AI call details:**
- Model: `claude-haiku-4-5` (classification is its sweet spot; cheap for a polling loop).
- Cache the spaces list as the stable prefix so repeated calls are cheap.
- The space list is small; note bodies are small. Single call per note.

### 3. Spaces management
CRUD for spaces (name + purpose). Editing a purpose does **not** retroactively
reclassify already-filed notes in v1.

### 4. Note review / correction
- View inbox (unclassified + flagged low-confidence).
- View notes per space.
- Manually move a note to a space (or back to inbox). Manual moves are the
  feedback signal for whether the threshold is tuned right.

### 5. S3 backup (manual)
- A **"Back up now"** button in the UI.
- On click: `VACUUM INTO` a consistent snapshot, upload to S3 with a timestamped
  key (`notes-<ISO8601>.db`), keep the last N snapshots (simple retention).
- S3 endpoint is **configurable** (env var) so AWS / R2 / B2 / GCS all work.
- Credentials via Railway env vars in v1 (see deferred item below).

## Configuration (env vars)

- `ANTHROPIC_API_KEY` — classifier
- `DB_PATH` — defaults to `/data/notes.db`
- `CLASSIFY_THRESHOLD` — default `0.8`
- `CLASSIFY_INTERVAL_SECONDS` — classifier poll interval
- `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL` (optional, for non-AWS)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `BACKUP_RETENTION` — number of snapshots to keep

## Out of Scope (deferred, additive later)

Parked from the original idea — each is purely additive and does not require
restructuring v1:

- Email / Slack / browser-extension ingest (all feed the same inbox)
- Merge-similar suggestions (needs embeddings; Anthropic has none — would use a
  third-party embedding provider like Voyage)
- Cleanup suggestions
- Attachments / blob storage
- Multi-user auth
- **Scheduled automatic backups** (v1 is manual-only)
- **Client-supplied S3 credentials** — move creds out of infra into browser
  `localStorage` so the deploy isn't tied to AWS keys. Has security implications
  (creds transit to the server per-request, or backup runs client-side) — design
  carefully when picked up.

## Success Criteria

- Paste text → it appears in the inbox immediately.
- Within one classifier interval, a clearly-matching note auto-files into the
  right space; an ambiguous note stays flagged in the inbox.
- Editing/creating spaces works; manual move works.
- "Back up now" produces a downloadable/restorable snapshot in S3.
- Surviving a Railway redeploy: data is intact (Volume).
