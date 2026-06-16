import sqlite3
import os

from app import backup, db


def test_snapshot_creates_consistent_copy(tmp_path):
    src = str(tmp_path / "src.db")
    conn = db.connect(src)
    db.init_schema(conn)
    db.add_note(conn, "hello")

    dest = str(tmp_path / "snap.db")
    backup.make_snapshot(src, dest)

    assert os.path.exists(dest)
    snap = sqlite3.connect(dest)
    snap.row_factory = sqlite3.Row
    rows = snap.execute("SELECT body FROM notes").fetchall()
    assert rows[0]["body"] == "hello"


def test_run_backup_uploads_and_applies_retention(tmp_path):
    src = str(tmp_path / "src.db")
    conn = db.connect(src)
    db.init_schema(conn)

    uploaded = []
    deleted = []
    # 10 pre-existing snapshots with realistic timestamped keys (earlier dates).
    existing = [f"notes-2026-06-{i:02d}T00-00-00.db" for i in range(1, 11)]

    class FakeS3:
        def __init__(self):
            self.keys = list(existing)

        def upload_file(self, filename, bucket, key):
            uploaded.append((bucket, key))
            self.keys.append(key)

        def list_objects_v2(self, Bucket, Prefix):
            return {"Contents": [{"Key": k} for k in self.keys if k.startswith(Prefix)]}

        def delete_object(self, Bucket, Key):
            deleted.append(Key)

    key = backup.run_backup(
        src, FakeS3(), bucket="mybucket", retention=7, now_iso="2026-06-16T12-00-00"
    )

    assert uploaded == [("mybucket", key)]
    assert key == "notes-2026-06-16T12-00-00.db"
    # 10 existing + 1 new = 11; keep 7 newest, delete 4 oldest by timestamp.
    assert len(deleted) == 4
    assert deleted == [f"notes-2026-06-{i:02d}T00-00-00.db" for i in range(1, 5)]
    # the newest snapshot (just uploaded) is never deleted
    assert key not in deleted
