# Notes — AI-routed inbox

Dump notes into one inbox; a background AI loop files them into spaces you define,
or flags them when unsure. FastAPI + SQLite, deployed on Railway with a Volume.

## Local dev

    pip install -r requirements.txt
    DB_PATH=./data/notes.db ANTHROPIC_API_KEY=sk-... uvicorn app.main:create_app --factory --reload

Visit http://localhost:8000

Without `ANTHROPIC_API_KEY` the app still runs — notes just stay in the inbox
(the background classifier is disabled).

## Tests

    python -m pytest -v

## Deploy (Railway)

1. `railway up` (or connect the GitHub repo for auto-deploy)
2. Set variables: `ANTHROPIC_API_KEY`, and optionally `S3_BUCKET`/`S3_REGION`/
   `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (+ `S3_ENDPOINT_URL` for non-AWS
   providers like R2/B2) for backups.
3. A Volume is mounted at `/data` (see `railway.toml`) — SQLite lives there and
   survives restarts/redeploys.

Backups are manual via the "Back up now" button.

## Config

See `.env.example` for all environment variables.
