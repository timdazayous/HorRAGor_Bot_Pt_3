"""
Tests unitaires — src/graph/pipeline.py

Vérifie la topologie du graphe compilé, puis exécute un parcours complet
(RAG → Scraper → Narration → Juge) avec tous les LLM mockés.
"""
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from src.graph import nodes, pipeline


def _fake_llm(contents):
    responses = iter(contents)

    class _Fake:
        def invoke(self, messages):
            return SimpleNamespace(
                content=next(responses),
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            )
    return _Fake()


def test_graph_has_the_four_expected_nodes():
    node_names = set(pipeline.workflow.nodes.keys())
    assert {"rag", "scraper", "narration", "judge"}.issubset(node_names)


def test_full_traversal_skips_scraper_when_rag_complete(monkeypatch):
    # Une seule FakeLLM partagée par tous les nœuds : elle consomme les réponses
    # dans l'ordre d'appel, quel que soit le nœud qui invoque.
    shared_llm = _fake_llm([
        "TITRE\nThe Shining",                    # rag_node: extraction
        "Dossier factuel sur The Shining.",        # rag_node: synthèse
        "Il était une fois, dans un hôtel maudit...",  # narration_node
        '{"is_valid": true, "confidence": 0.95, "reasoning": "Cohérent."}',  # judge_node
    ])
    monkeypatch.setattr(nodes, "ChatGroq", lambda **kwargs: shared_llm)
    monkeypatch.setattr(nodes, "rag_search", lambda subject, is_title: {
        "context": "...", "is_complete": True, "matched_title": "The Shining",
    })

    query = "Parle-moi de The Shining"
    result = pipeline.app.invoke({
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "retry_count": 0,
        "tools_used": [],
    })

    assert result["tools_used"] == ["rag_agent", "narration_agent", "judge_agent"]
    assert result["final_answer"] == "Il était une fois, dans un hôtel maudit..."
    assert result["rag_complete"] is True


def test_full_traversal_goes_through_scraper_when_rag_incomplete(monkeypatch):
    shared_llm = _fake_llm([
        "TITRE\nSkinamarink",                       # rag_node: extraction
        "Aucune information locale.",                 # rag_node: synthèse
        "Synthèse des anecdotes trouvées en ligne.",   # scraper_node
        "Une atmosphère glaçante s'installe...",        # narration_node
        '{"is_valid": true, "confidence": 0.9, "reasoning": "Cohérent."}',  # judge_node
    ])
    monkeypatch.setattr(nodes, "ChatGroq", lambda **kwargs: shared_llm)
    monkeypatch.setattr(nodes, "rag_search", lambda subject, is_title: {
        "context": "...", "is_complete": False, "matched_title": None,
    })
    monkeypatch.setattr(nodes, "scrape_web_lore", lambda target: {"context": "extrait wiki", "found": True})

    query = "Parle-moi de Skinamarink"
    result = pipeline.app.invoke({
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "retry_count": 0,
        "tools_used": [],
    })

    assert result["tools_used"] == ["rag_agent", "scraper_agent", "narration_agent", "judge_agent"]
    assert result["rag_complete"] is False
