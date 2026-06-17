import os
from dataclasses import dataclass


@dataclass
class Config:
    db_path: str
    classify_threshold: float
    classify_interval_seconds: int
    anthropic_api_key: str | None
    s3_bucket: str | None
    s3_region: str | None
    s3_endpoint_url: str | None
    backup_retention: int
    seed_demo: bool


def load() -> Config:
    return Config(
        db_path=os.getenv("DB_PATH", "/data/notes.db"),
        classify_threshold=float(os.getenv("CLASSIFY_THRESHOLD", "0.8")),
        classify_interval_seconds=int(os.getenv("CLASSIFY_INTERVAL_SECONDS", "30")),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        s3_bucket=os.getenv("S3_BUCKET"),
        s3_region=os.getenv("S3_REGION"),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        backup_retention=int(os.getenv("BACKUP_RETENTION", "7")),
        seed_demo=os.getenv("SEED_DEMO", "").lower() in ("1", "true", "yes"),
    )
