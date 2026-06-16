import os
import sqlite3
import tempfile


def make_snapshot(src_path: str, dest_path: str) -> None:
    conn = sqlite3.connect(src_path)
    try:
        conn.execute("VACUUM INTO ?", (dest_path,))
    finally:
        conn.close()


def run_backup(db_path: str, s3_client, bucket: str, retention: int, now_iso: str) -> str:
    key = f"notes-{now_iso}.db"
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "snapshot.db")
        make_snapshot(db_path, snap)
        s3_client.upload_file(snap, bucket, key)

    _apply_retention(s3_client, bucket, retention)
    return key


def _apply_retention(s3_client, bucket: str, retention: int) -> None:
    resp = s3_client.list_objects_v2(Bucket=bucket, Prefix="notes-")
    keys = sorted(obj["Key"] for obj in resp.get("Contents", []))
    excess = len(keys) - retention
    for key in keys[: max(0, excess)]:
        s3_client.delete_object(Bucket=bucket, Key=key)
