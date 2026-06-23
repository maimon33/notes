import os
from dataclasses import dataclass


@dataclass
class Config:
    db_path: str
    classify_threshold: float
    classify_interval_seconds: int
    ai_provider: str | None
    anthropic_api_key: str | None
    openai_api_key: str | None
    gemini_api_key: str | None
    xai_api_key: str | None
    anthropic_model: str | None
    openai_model: str | None
    gemini_model: str | None
    xai_model: str | None
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
        ai_provider=os.getenv("AI_PROVIDER"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        xai_api_key=os.getenv("XAI_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL"),
        openai_model=os.getenv("OPENAI_MODEL"),
        gemini_model=os.getenv("GEMINI_MODEL"),
        xai_model=os.getenv("XAI_MODEL"),
        s3_bucket=os.getenv("S3_BUCKET"),
        s3_region=os.getenv("S3_REGION"),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        backup_retention=int(os.getenv("BACKUP_RETENTION", "7")),
        seed_demo=os.getenv("SEED_DEMO", "").lower() in ("1", "true", "yes"),
    )
