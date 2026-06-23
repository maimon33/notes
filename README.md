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

## GitHub Actions

Two workflows are included:

1. `Checks`
   - runs on every push and pull request
   - installs Python 3.12
   - installs `requirements.txt`
   - runs `python -m pytest -q`

2. `Deploy`
   - runs on pushes to `main` and on manual dispatch
   - runs the same test suite first
   - deploys to Railway only if tests pass

This gives you branch-level feedback before merge, while keeping Railway deploys
gated on passing checks.

## Deploy (Railway)

1. Push to `main` to trigger the GitHub Actions deploy workflow, or run `railway up`
   locally if you want a manual CLI deploy.
2. In GitHub, set:
   - secret: `RAILWAY_TOKEN`
   - variables: `RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_SERVICE_NAME`
3. In Railway, set app environment variables for your runtime config. For AI and
   backups that usually means:
   - `AI_PROVIDER`
   - one or more of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`
   - optionally `ANTHROPIC_MODEL`, `OPENAI_MODEL`, `GEMINI_MODEL`, `XAI_MODEL`
   - optionally `S3_BUCKET`, `S3_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
   - optionally `S3_ENDPOINT_URL` for non-AWS providers such as R2/B2
4. A Volume is mounted at `/data` (see `railway.toml`) — SQLite lives there and
   survives restarts/redeploys.

Backups are manual via the "Back up now" button.

## Config

See `.env.example` for all environment variables.
