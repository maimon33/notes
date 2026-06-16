import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import boto3
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import backup, classifier, config, db

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(conn=None, cfg=None) -> FastAPI:
    cfg = cfg or config.load()
    if conn is None:
        conn = db.connect(cfg.db_path)
        db.init_schema(conn)

    app = FastAPI()
    app.state.conn = conn
    app.state.cfg = cfg
    app.state.backup_msg = None

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def index(request: Request):
        spaces = db.list_spaces(conn)
        for s in spaces:
            s["notes"] = db.notes_in_space(conn, s["id"])
        msg = app.state.backup_msg
        app.state.backup_msg = None
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"inbox": db.inbox_notes(conn), "spaces": spaces, "backup_msg": msg},
        )

    @app.post("/notes")
    def add_note(body: str = Form(...)):
        db.add_note(conn, body)
        return RedirectResponse("/", status_code=303)

    @app.post("/spaces")
    def add_space(name: str = Form(...), purpose: str = Form(...)):
        db.create_space(conn, name, purpose)
        return RedirectResponse("/", status_code=303)

    @app.post("/spaces/{space_id}/delete")
    def del_space(space_id: int):
        db.delete_space(conn, space_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/notes/{note_id}/move")
    def move(note_id: int, space_id: str = Form("")):
        db.move_note(conn, note_id, int(space_id) if space_id else None)
        return RedirectResponse("/", status_code=303)

    @app.post("/backup")
    def do_backup():
        if not cfg.s3_bucket:
            app.state.backup_msg = "Backup not configured (no S3_BUCKET)."
            return RedirectResponse("/", status_code=303)
        s3 = boto3.client(
            "s3", region_name=cfg.s3_region, endpoint_url=cfg.s3_endpoint_url
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        try:
            key = backup.run_backup(cfg.db_path, s3, cfg.s3_bucket, cfg.backup_retention, now)
            app.state.backup_msg = f"Backed up to {key}"
        except Exception as e:  # surface failure to the user
            app.state.backup_msg = f"Backup failed: {e}"
        return RedirectResponse("/", status_code=303)

    _start_background(app)
    return app


def _start_background(app: FastAPI) -> None:
    cfg = app.state.cfg
    conn = app.state.conn
    if not cfg.anthropic_api_key:
        return
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    def classify_fn(body, spaces):
        return classifier.classify_one(body, spaces, client)

    def loop():
        import time

        while True:
            try:
                classifier.process_inbox(conn, classify_fn, cfg.classify_threshold)
            except Exception:
                pass
            time.sleep(cfg.classify_interval_seconds)

    threading.Thread(target=loop, daemon=True).start()
