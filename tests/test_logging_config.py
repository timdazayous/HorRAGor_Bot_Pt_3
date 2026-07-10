"""Tests unitaires — src/logging_config.py (interception logging stdlib → Loguru)."""
import logging

from loguru import logger

from src.logging_config import setup_logging


def test_setup_logging_creates_log_dir_and_configures_root(tmp_path, monkeypatch):
    fake_log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.logging_config.LOG_DIR", fake_log_dir)

    setup_logging()

    assert fake_log_dir.exists()
    root_handlers = logging.getLogger().handlers
    assert len(root_handlers) == 1


def test_noisy_loggers_do_not_propagate_to_root(tmp_path, monkeypatch):
    fake_log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.logging_config.LOG_DIR", fake_log_dir)

    setup_logging()

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx"):
        assert logging.getLogger(name).propagate is False


def test_stdlib_log_record_reaches_loguru_file_sink(tmp_path, monkeypatch):
    fake_log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.logging_config.LOG_DIR", fake_log_dir)

    setup_logging()
    logging.getLogger("some.module").warning("message de test intercepté")
    logger.complete()  # attend le flush du sink asynchrone (enqueue=True)

    log_file = fake_log_dir / "horragor.log"
    assert log_file.exists()
    assert "message de test intercepté" in log_file.read_text(encoding="utf-8")
