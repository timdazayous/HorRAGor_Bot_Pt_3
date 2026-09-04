"""Tests unitaires — src/logging_config.py (interception logging stdlib → Loguru)."""
import json
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


def test_stdlib_log_record_reaches_loguru_json_sink(tmp_path, monkeypatch):
    """Le sink JSON (consommé par Promtail/Loki) doit rester parsable ligne par ligne."""
    fake_log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.logging_config.LOG_DIR", fake_log_dir)

    setup_logging()
    logging.getLogger("some.module").error("panne simulée pour Loki")
    logger.complete()

    json_log_file = fake_log_dir / "horragor.jsonl"
    assert json_log_file.exists()

    lines = [line for line in json_log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    matching = [json.loads(line) for line in lines if "panne simulée pour Loki" in line]
    assert matching, "aucune ligne JSON ne contient le message attendu"

    # Format plat (pas serialize=True) : level/message directement au premier
    # niveau, pour rester filtrable simplement en LogQL (`| json`).
    record = matching[0]
    assert record["level"] == "ERROR"
    assert record["message"] == "panne simulée pour Loki"
