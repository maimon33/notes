import importlib

from app import config


def test_defaults(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("CLASSIFY_THRESHOLD", raising=False)
    monkeypatch.delenv("CLASSIFY_INTERVAL_SECONDS", raising=False)
    importlib.reload(config)
    cfg = config.load()
    assert cfg.db_path == "/data/notes.db"
    assert cfg.classify_threshold == 0.8
    assert cfg.classify_interval_seconds == 30


def test_env_override(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("CLASSIFY_THRESHOLD", "0.5")
    cfg = config.load()
    assert cfg.db_path == "/tmp/x.db"
    assert cfg.classify_threshold == 0.5
