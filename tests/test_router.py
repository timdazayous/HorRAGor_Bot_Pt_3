"""Tests unitaires — src/graph/router.py (aiguillage, aucune dépendance externe)."""
from src.graph.router import should_retry_or_end, should_scrape_or_narrate


class TestShouldScrapeOrNarrate:
    def test_rag_complete_goes_to_narration(self):
        assert should_scrape_or_narrate({"rag_complete": True}) == "narration"

    def test_rag_incomplete_goes_to_scraper(self):
        assert should_scrape_or_narrate({"rag_complete": False}) == "scraper"

    def test_missing_key_defaults_to_scraper(self):
        assert should_scrape_or_narrate({}) == "scraper"

    def test_force_scrape_overrides_complete_rag(self):
        """Intention ANECDOTES : la base est complète mais l'enrichissement est explicite."""
        assert should_scrape_or_narrate({"rag_complete": True, "force_scrape": True}) == "scraper"

    def test_no_force_scrape_with_complete_rag_goes_to_narration(self):
        assert should_scrape_or_narrate({"rag_complete": True, "force_scrape": False}) == "narration"


class TestShouldRetryOrEnd:
    def test_valid_verdict_ends(self):
        state = {"judge_verdict": {"is_valid": True, "confidence": 0.9}, "retry_count": 0}
        assert should_retry_or_end(state) == "end"

    def test_invalid_but_high_confidence_ends(self):
        state = {"judge_verdict": {"is_valid": False, "confidence": 0.9}, "retry_count": 0}
        assert should_retry_or_end(state) == "end"

    def test_invalid_low_confidence_retries(self):
        state = {"judge_verdict": {"is_valid": False, "confidence": 0.1}, "retry_count": 0}
        assert should_retry_or_end(state) == "retry"

    def test_retry_budget_exhausted_ends(self):
        state = {"judge_verdict": {"is_valid": False, "confidence": 0.1}, "retry_count": 2}
        assert should_retry_or_end(state) == "end"

    def test_missing_verdict_ends(self):
        assert should_retry_or_end({"retry_count": 0}) == "end"
