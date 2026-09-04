"""Tests unitaires — src/config.py (valeurs par défaut, lecture des variables d'env)."""
import importlib
import os

import pytest


def test_default_values_when_env_unset(monkeypatch):
    for var in (
        "RAG_TEMPERATURE", "SCRAPER_TEMPERATURE", "NARRATION_TEMPERATURE",
        "JUDGE_TEMPERATURE", "LLM_MAX_TOKENS", "JUDGE_MAX_RETRIES",
        "JUDGE_CONFIDENCE_THRESHOLD", "LLM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)

    from src import config
    importlib.reload(config)

    assert config.GROQ_MODEL == "openai/gpt-oss-120b"
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


def test_missing_jwt_secret_key_fails_closed(monkeypatch):
    """L'app refuse de démarrer sans JWT_SECRET_KEY — pas de valeur par défaut silencieuse."""
    from src import config
    original_secret = os.environ.get("JWT_SECRET_KEY")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    # Sans ça, le `from dotenv import load_dotenv` ré-exécuté par reload()
    # relirait .env (présent en local) et repeuplerait la variable qu'on
    # vient de supprimer — on veut simuler un déploiement où .env n'existe
    # pas du tout. On patche la source (dotenv.load_dotenv), pas l'attribut
    # du module config, qui serait de toute façon réimporté par le reload.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)

    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            importlib.reload(config)
    finally:
        # Repli : restaure une clé pour ne pas casser les tests suivants du module.
        monkeypatch.setenv("JWT_SECRET_KEY", original_secret or "test-secret-restored-after-fail-closed-test")
        importlib.reload(config)
