"""Tests unitaires — src/models/state.py (schéma du State partagé)."""
from langchain_core.messages import HumanMessage

from src.models.state import AgentState


def test_agent_state_has_expected_fields():
    expected = {
        "messages", "user_query", "rag_context", "matched_title",
        "rag_complete", "force_scrape", "is_survival_mode", "scraper_context", "final_answer",
        "judge_verdict", "retry_count", "tools_used",
    }
    assert expected == set(AgentState.__annotations__.keys())


def test_agent_state_accepts_a_valid_instance():
    state: AgentState = {
        "messages": [HumanMessage(content="Parle-moi de The Shining")],
        "user_query": "Parle-moi de The Shining",
        "rag_context": None,
        "matched_title": None,
        "rag_complete": False,
        "force_scrape": False,
        "is_survival_mode": False,
        "scraper_context": None,
        "final_answer": None,
        "judge_verdict": None,
        "retry_count": 0,
        "tools_used": [],
    }
    assert state["user_query"] == "Parle-moi de The Shining"
