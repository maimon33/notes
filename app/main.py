import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import boto3
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import backup, classifier, config, db, search

BASE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(BASE / "templates"))


class ReplaceRequest(BaseModel):
    query: str
    replacement: str
    regex: bool = False
    scope: str = "everywhere"  # "note" | "space" | "everywhere"
    space_id: int | None = None
    note_id: int | None = None
    note_ids: list[int] | None = None  # explicit subset (checked rows) on apply


def _scope_note_ids(conn, scope: str, space_id: int | None, note_id: int | None) -> list[int]:
    if scope == "note" and note_id is not None:
        return [note_id]
    if scope == "space" and space_id is not None:
        return [n["id"] for n in db.notes_in_space(conn, space_id)]
    return [r["id"] for r in conn.execute("SELECT id FROM notes")]


def _seed_demo(conn) -> None:
    if db.list_spaces(conn):
        return
    work = db.create_space(conn, "Work", "Job, clients, meetings, standups, deadlines")
    recipes = db.create_space(conn, "Recipes", "Food, cooking, ingredients, meals")
    ideas = db.create_space(conn, "Ideas", "Product ideas, side projects, things to build")

    # recently filed (awaiting keep/move) — with alternates so Move shows chips
    n1 = db.add_note(conn, "Standup at 9:30 — demo the new search panel")
    db.file_note(conn, n1, work, 0.93)
    db.set_suggestions(conn, n1, {"ranked": [{"space_id": work, "confidence": 0.93}, {"space_id": ideas, "confidence": 0.31}], "new_space": None})
    n2 = db.add_note(conn, "Pasta dough: 100g flour per egg, rest 30 min")
    db.file_note(conn, n2, recipes, 0.95)
    db.set_suggestions(conn, n2, {"ranked": [{"space_id": recipes, "confidence": 0.95}], "new_space": None})

    # already kept (lives only in its space)
    db.file_note(conn, db.add_note(conn, "Build a notes app that auto-files with AI"), ideas, 0.91, confirmed=True)

    # needs sorting — low confidence, multiple candidate chips
    n3 = db.add_note(conn, "random thought — could be work or a side project?")
    db.flag_note(conn, n3, 0.45)
    db.set_suggestions(conn, n3, {"ranked": [{"space_id": work, "confidence": 0.45}, {"space_id": ideas, "confidence": 0.4}], "new_space": None})

    # needs sorting — nothing fits, AI proposes a new space
    n4 = db.add_note(conn, "flights to Lisbon in October, find a hotel near Alfama")
    db.flag_note(conn, n4, 0.2)
    db.set_suggestions(conn, n4, {"ranked": [], "new_space": {"name": "Travel", "purpose": "Trips, flights, hotels, itineraries"}})

    # private (no AI) + pending
    db.add_note(conn, "ID number and gate code — keep this private", private=True)
    db.add_note(conn, "buy milk, eggs, bread")


def create_app(conn=None, cfg=None) -> FastAPI:
    cfg = cfg or config.load()
    if conn is None:
        conn = db.connect(cfg.db_path)
        db.init_schema(conn)
        if cfg.seed_demo:
            _seed_demo(conn)

    app = FastAPI()
    app.state.conn = conn
    app.state.cfg = cfg
    app.state.backup_msg = None
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

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
            {
                "recently_filed": db.recently_filed(conn),
                "needs_sorting": db.needs_sorting(conn),
                "private_pending": db.private_and_pending(conn),
                "spaces": spaces,
                "spaces_by_id": {s["id"]: s for s in spaces},
                "backup_msg": msg,
                "cfg": cfg,
                "classifier_on": bool(cfg.anthropic_api_key),
            },
        )

    @app.post("/notes")
    def add_note(body: str = Form(...), private: str = Form("")):
        db.add_note(conn, body, private=bool(private))
        return RedirectResponse("/", status_code=303)

    @app.post("/notes/{note_id}/keep")
    def keep_note(note_id: int):
        db.keep_note(conn, note_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/notes/{note_id}/file")
    def file_note(note_id: int, space_id: int = Form(...)):
        db.file_note(conn, note_id, space_id, None, confirmed=True)
        return RedirectResponse("/", status_code=303)

    @app.post("/notes/{note_id}/file-new")
    def file_note_new(note_id: int, name: str = Form(...), purpose: str = Form(...)):
        sid = db.create_space(conn, name, purpose)
        db.file_note(conn, note_id, sid, None, confirmed=True)
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

    @app.post("/notes/{note_id}/delete")
    def del_note(note_id: int):
        conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        conn.commit()
        return RedirectResponse("/", status_code=303)

    @app.post("/backup")
    def do_backup():
        if not cfg.s3_bucket:
            app.state.backup_msg = "Backup not configured (no S3_BUCKET)."
            return RedirectResponse("/", status_code=303)
        s3 = boto3.client("s3", region_name=cfg.s3_region, endpoint_url=cfg.s3_endpoint_url)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        try:
            key = backup.run_backup(cfg.db_path, s3, cfg.s3_bucket, cfg.backup_retention, now)
            app.state.backup_msg = f"Backed up to {key}"
        except Exception as e:  # surface failure to the user
            app.state.backup_msg = f"Backup failed: {e}"
        return RedirectResponse("/", status_code=303)

    # --- JSON API: search & replace -------------------------------------------------

    @app.get("/api/search")
    def api_search(q: str = "", regex: bool = False):
        try:
            matches = search.search(conn, q, regex=regex)
        except re.error as e:
            return JSONResponse({"error": f"Invalid regex: {e}"}, status_code=400)
        return {"matches": matches}

    @app.post("/api/replace/preview")
    def api_replace_preview(req: ReplaceRequest):
        ids = _scope_note_ids(conn, req.scope, req.space_id, req.note_id)
        try:
            changes = search.plan_replace(conn, ids, req.query, req.replacement, req.regex)
        except re.error as e:
            return JSONResponse({"error": f"Invalid regex: {e}"}, status_code=400)
        return {"changes": changes}

    @app.post("/api/replace/apply")
    def api_replace_apply(req: ReplaceRequest):
        # Recompute server-side from the request params (never trust client 'after').
        # If the client sent an explicit checked subset, restrict to it.
        ids = req.note_ids if req.note_ids is not None else _scope_note_ids(
            conn, req.scope, req.space_id, req.note_id
        )
        try:
            changes = search.plan_replace(conn, ids, req.query, req.replacement, req.regex)
        except re.error as e:
            return JSONResponse({"error": f"Invalid regex: {e}"}, status_code=400)
        return search.apply_replace(conn, changes)

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
