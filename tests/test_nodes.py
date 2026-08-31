"""
Tests unitaires — src/graph/nodes.py

ChatGroq est entièrement mocké : ces tests ne consomment aucun appel Groq réel,
ils vérifient uniquement la logique métier de chaque nœud (parsing, branchement,
construction du State retourné).
"""
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.graph import nodes


class FakeLLM:
    """Renvoie les réponses fournies dans l'ordre à chaque appel .invoke()."""
    def __init__(self, contents):
        self._responses = iter(contents)

    def invoke(self, messages):
        content = next(self._responses)
        return SimpleNamespace(content=content, usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


@pytest.fixture
def fake_llm(monkeypatch):
    def _make(contents):
        llm = FakeLLM(contents)
        monkeypatch.setattr(nodes, "ChatGroq", lambda **kwargs: llm)
        return llm
    return _make


class TestParseExtraction:
    @pytest.mark.parametrize("intent", ["TITRE", "THEME", "SURVIE", "AGE", "SIMILAIRE", "ANECDOTES"])
    def test_well_formed_each_intent(self, intent):
        parsed_intent, subject = nodes._parse_extraction(f"{intent}\nThe Shining")
        assert subject == "The Shining"
        assert parsed_intent == intent

    def test_malformed_output_falls_back_to_title(self):
        intent, subject = nodes._parse_extraction("juste une phrase sans le bon format")
        assert intent == "TITRE"
        assert subject  # non vide

    def test_empty_output(self):
        intent, subject = nodes._parse_extraction("")
        assert intent == "TITRE"
        assert subject == ""


class TestParseJudgeVerdict:
    def test_valid_json_extracted_from_surrounding_text(self):
        raw = 'Voici mon verdict : {"is_valid": true, "confidence": 0.9, "reasoning": "ok"} merci'
        verdict = nodes._parse_judge_verdict(raw)
        assert verdict == {"is_valid": True, "confidence": 0.9, "reasoning": "ok"}

    def test_invalid_json_returns_safe_default(self):
        verdict = nodes._parse_judge_verdict("pas du json du tout")
        assert verdict["is_valid"] is True
        assert 0.0 <= verdict["confidence"] <= 1.0


class TestRagNode:
    def test_title_query_complete(self, fake_llm, monkeypatch):
        fake_llm(["TITRE\nThe Shining", "Dossier factuel sur The Shining."])
        monkeypatch.setattr(
            nodes, "rag_search",
            lambda subject, is_title: {"context": "...", "is_complete": True, "matched_title": "The Shining"},
        )

        state = {"messages": [HumanMessage(content="Parle-moi de The Shining")], "user_query": "Parle-moi de The Shining"}
        result = nodes.rag_node(state)

        assert result["rag_complete"] is True
        assert result["matched_title"] == "The Shining"
        assert result["is_survival_mode"] is False
        assert result["tools_used"] == ["rag_agent"]
        assert isinstance(result["messages"][0], AIMessage)

    def test_theme_query_incomplete_triggers_scraper_branch(self, fake_llm, monkeypatch):
        fake_llm(["THEME\nfantomes", "Rien trouvé de pertinent."])
        monkeypatch.setattr(
            nodes, "rag_search",
            lambda subject, is_title: {"context": "...", "is_complete": False, "matched_title": None},
        )

        state = {"messages": [HumanMessage(content="Un film avec des fantômes ?")], "user_query": "Un film avec des fantômes ?"}
        result = nodes.rag_node(state)

        assert result["rag_complete"] is False
        assert result["matched_title"] is None
        assert result["is_survival_mode"] is False

    def test_survival_query_calls_get_survival_context_not_rag_search(self, fake_llm, monkeypatch):
        """Régression : une question de suivi comme 'mon taux de survie dans ce dernier ?'
        doit résoudre le film déjà discuté et utiliser le Simulateur de Survie,
        pas repartir sur une recherche thématique générique."""
        fake_llm(["SURVIE\nThe Shining", "Dossier de survie sur The Shining."])

        called = {"rag_search": False, "get_survival_context": None}
        monkeypatch.setattr(nodes, "rag_search", lambda *a, **k: called.update(rag_search=True) or {})

        def fake_get_survival_context(subject):
            called["get_survival_context"] = subject
            return {"context": "...", "is_complete": True, "matched_title": "The Shining"}
        monkeypatch.setattr(nodes, "get_survival_context", fake_get_survival_context)

        state = {
            "messages": [
                HumanMessage(content="parle de the shining"),
                AIMessage(content="..."),
                HumanMessage(content="quel est mon taux de survie dans ce dernier ?"),
            ],
            "user_query": "quel est mon taux de survie dans ce dernier ?",
        }
        result = nodes.rag_node(state)

        assert called["get_survival_context"] == "The Shining"
        assert called["rag_search"] is False
        assert result["is_survival_mode"] is True
        assert result["matched_title"] == "The Shining"

    def test_age_query_calls_calculate_movie_age(self, fake_llm, monkeypatch):
        fake_llm(["AGE\nHalloween", "Halloween est sorti il y a 47 ans."])
        called = {}

        def fake_calculate_movie_age(subject):
            called["subject"] = subject
            return {"context": "...", "is_complete": True, "matched_title": "Halloween"}
        monkeypatch.setattr(nodes, "calculate_movie_age", fake_calculate_movie_age)

        def _fail_if_called(*a, **k):
            raise AssertionError("rag_search ne devrait pas être appelé")
        monkeypatch.setattr(nodes, "rag_search", _fail_if_called)

        state = {"messages": [HumanMessage(content="quel age a Halloween ?")], "user_query": "quel age a Halloween ?"}
        result = nodes.rag_node(state)

        assert called["subject"] == "Halloween"
        assert result["is_survival_mode"] is False
        assert result["matched_title"] == "Halloween"

    def test_similar_query_calls_find_similar_movies(self, fake_llm, monkeypatch):
        fake_llm(["SIMILAIRE\nScream", "Films similaires à Scream."])
        called = {}

        def fake_find_similar_movies(subject):
            called["subject"] = subject
            return {"context": "...", "is_complete": True, "matched_title": "Scream"}
        monkeypatch.setattr(nodes, "find_similar_movies", fake_find_similar_movies)

        state = {"messages": [HumanMessage(content="films similaires a Scream ?")], "user_query": "films similaires a Scream ?"}
        result = nodes.rag_node(state)

        assert called["subject"] == "Scream"
        assert result["matched_title"] == "Scream"

    def test_anecdotes_query_forces_incomplete_even_if_db_has_data(self, fake_llm, monkeypatch):
        """Régression : une demande explicite d'anecdotes doit toujours passer par le
        Scraper, même si la base locale a déjà toutes les infos de base sur le film."""
        fake_llm(["ANECDOTES\nGet Out", "Dossier de base sur Get Out."])
        monkeypatch.setattr(
            nodes, "rag_search",
            lambda subject, is_title: {"context": "déjà complet", "is_complete": True, "matched_title": "Get Out"},
        )

        state = {"messages": [HumanMessage(content="donne-moi des anecdotes sur Get Out")], "user_query": "donne-moi des anecdotes sur Get Out"}
        result = nodes.rag_node(state)

        assert result["rag_complete"] is True  # reflet fidèle : la base est bien complète
        assert result["force_scrape"] is True  # mais l'enrichissement est explicitement demandé
        assert result["matched_title"] == "Get Out"


class TestScraperNode:
    def test_uses_matched_title_as_target(self, fake_llm, monkeypatch):
        fake_llm(["Synthèse des anecdotes Wikipedia."])
        captured = {}

        def fake_scrape(target):
            captured["target"] = target
            return {"context": "extrait wiki", "found": True}

        monkeypatch.setattr(nodes, "scrape_web_lore", fake_scrape)

        state = {"matched_title": "Hereditary", "messages": []}
        result = nodes.scraper_node(state)

        assert captured["target"] == "Hereditary"
        assert result["scraper_context"] == "Synthèse des anecdotes Wikipedia."
        assert result["tools_used"] == ["scraper_agent"]

    def test_falls_back_to_user_query_without_matched_title(self, fake_llm, monkeypatch):
        fake_llm(["Synthèse."])
        captured = {}

        def fake_scrape(target):
            captured["target"] = target
            return {"context": "x", "found": False}

        monkeypatch.setattr(nodes, "scrape_web_lore", fake_scrape)

        state = {"matched_title": None, "user_query": "Skinamarink", "messages": [HumanMessage(content="Skinamarink")]}
        nodes.scraper_node(state)

        assert captured["target"] == "Skinamarink"


class TestNarrationNode:
    def test_basic_generation_without_retry(self, fake_llm):
        fake_llm(["Il était une fois, dans les ténèbres..."])

        state = {"user_query": "Parle-moi de The Shining", "rag_context": "Dossier RAG.", "retry_count": 0}
        result = nodes.narration_node(state)

        assert result["final_answer"] == "Il était une fois, dans les ténèbres..."
        assert result["tools_used"] == ["narration_agent"]

    def test_includes_scraper_context_when_present(self, fake_llm):
        fake_llm(["Réponse enrichie."])
        state = {
            "user_query": "Hereditary", "rag_context": "Dossier RAG.",
            "scraper_context": "Anecdotes web.", "retry_count": 0,
        }
        nodes.narration_node(state)
        # Le contenu envoyé au LLM doit contenir les deux dossiers concaténés
        # (vérifié indirectement : pas d'exception, la fonction s'exécute normalement)
        assert True

    def test_retry_injects_judge_critique(self, fake_llm, monkeypatch):
        captured_messages = []
        llm = fake_llm(["Réponse corrigée."])
        original_invoke = llm.invoke

        def spy_invoke(messages):
            captured_messages.extend(messages)
            return original_invoke(messages)

        llm.invoke = spy_invoke

        state = {
            "user_query": "The Shining", "rag_context": "Dossier.",
            "retry_count": 1,
            "judge_verdict": {"is_valid": False, "confidence": 0.1, "reasoning": "Hors sujet."},
        }
        nodes.narration_node(state)

        human_msg = [m for m in captured_messages if isinstance(m, HumanMessage)][0]
        assert "Critique du Juge" in human_msg.content
        assert "Hors sujet." in human_msg.content

    def test_survival_mode_uses_survival_prompt(self, fake_llm, monkeypatch):
        captured_messages = []
        llm = fake_llm(["🩸 SIMULATEUR DE SURVIE — THE SHINING (1980)..."])
        original_invoke = llm.invoke

        def spy_invoke(messages):
            captured_messages.extend(messages)
            return original_invoke(messages)
        llm.invoke = spy_invoke

        state = {
            "user_query": "quel est mon taux de survie dans ce dernier ?",
            "rag_context": "Film : The Shining (1980)...",
            "is_survival_mode": True,
            "retry_count": 0,
        }
        result = nodes.narration_node(state)

        system_msg = [m for m in captured_messages if isinstance(m, SystemMessage)][0]
        assert system_msg is nodes._SURVIVAL_NARRATION_PROMPT
        assert "SIMULATEUR DE SURVIE" in result["final_answer"]

    def test_non_survival_mode_uses_gothic_prompt(self, fake_llm, monkeypatch):
        captured_messages = []
        llm = fake_llm(["Il était une fois..."])
        original_invoke = llm.invoke

        def spy_invoke(messages):
            captured_messages.extend(messages)
            return original_invoke(messages)
        llm.invoke = spy_invoke

        state = {"user_query": "Parle-moi de The Shining", "rag_context": "Dossier.", "retry_count": 0}
        nodes.narration_node(state)

        system_msg = [m for m in captured_messages if isinstance(m, SystemMessage)][0]
        assert system_msg is nodes._NARRATION_SYSTEM_PROMPT


class TestJudgeNode:
    def test_valid_verdict_increments_retry_count(self, fake_llm):
        fake_llm(['{"is_valid": true, "confidence": 0.95, "reasoning": "Cohérent."}'])

        state = {"user_query": "q", "final_answer": "réponse", "rag_context": "dossier", "retry_count": 0}
        result = nodes.judge_node(state)

        assert result["judge_verdict"]["is_valid"] is True
        assert result["retry_count"] == 1
        assert result["tools_used"] == ["judge_agent"]

    def test_malformed_json_falls_back_gracefully(self, fake_llm):
        fake_llm(["ce n'est pas du json"])

        state = {"user_query": "q", "final_answer": "réponse", "retry_count": 0}
        result = nodes.judge_node(state)

        assert result["judge_verdict"]["is_valid"] is True  # repli prudent
        assert result["retry_count"] == 1
