"""Tests unitaires — src/config.py (valeurs par défaut, lecture des variables d'env)."""
import importlib


def test_default_values_when_env_unset(monkeypatch):
    for var in (
        "RAG_TEMPERATURE", "SCRAPER_TEMPERATURE", "NARRATION_TEMPERATURE",
        "JUDGE_TEMPERATURE", "LLM_MAX_TOKENS", "JUDGE_MAX_RETRIES",
        "JUDGE_CONFIDENCE_THRESHOLD", "LLM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)

    from src import config
    importlib.reload(config)

    assert config.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert config.RAG_TEMPERATURE == 0.2
    assert config.SCRAPER_TEMPERATURE == 0.3
    assert config.NARRATION_TEMPERATURE == 0.9
    assert config.JUDGE_TEMPERATURE == 0.1
    assert config.LLM_MAX_TOKENS == 2048
    assert config.JUDGE_MAX_RETRIES == 2
    assert config.JUDGE_CONFIDENCE_THRESHOLD == 0.65


def test_env_overrides_are_respected(monkeypatch):
    monkeypatch.setenv("JUDGE_MAX_RETRIES", "5")
    monkeypatch.setenv("NARRATION_TEMPERATURE", "0.42")

    from src import config
    importlib.reload(config)

    assert config.JUDGE_MAX_RETRIES == 5
    assert config.NARRATION_TEMPERATURE == 0.42

    # Repli propre pour ne pas polluer les autres tests du module
    monkeypatch.delenv("JUDGE_MAX_RETRIES", raising=False)
    monkeypatch.delenv("NARRATION_TEMPERATURE", raising=False)
    importlib.reload(config)


def test_faiss_index_dir_points_under_data():
    from src import config
    assert config.FAISS_INDEX_DIR == config.DATA_DIR / "faiss_index"
