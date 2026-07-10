"""Tests unitaires — src/tools/scraper_tool.py (recherche Wikipedia mockée, aucun réseau réel)."""
from src.tools import scraper_tool


class FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


def _search_response(titles):
    return FakeResponse({"query": {"search": [{"title": t} for t in titles]}})


def _extract_response(text):
    return FakeResponse({"query": {"pages": {"123": {"extract": text}}}})


class TestScrapeWebLore:
    def test_no_page_found(self, monkeypatch):
        monkeypatch.setattr(scraper_tool.requests, "get", lambda *a, **k: _search_response([]))

        result = scraper_tool.scrape_web_lore("Film totalement inconnu")

        assert result["found"] is False
        assert "Aucune page Wikipedia" in result["context"]

    def test_page_found_but_empty_extract(self, monkeypatch):
        calls = {"n": 0}

        def fake_get(url, params, headers, timeout):
            calls["n"] += 1
            if params["action"] == "query" and "srsearch" in params:
                return _search_response(["Some Page"])
            return _extract_response("")

        monkeypatch.setattr(scraper_tool.requests, "get", fake_get)

        result = scraper_tool.scrape_web_lore("Some Movie")

        assert result["found"] is False
        assert "contenu est vide" in result["context"]

    def test_page_found_with_content(self, monkeypatch):
        def fake_get(url, params, headers, timeout):
            if "srsearch" in params:
                return _search_response(["Hereditary (film)"])
            return _extract_response("Hereditary est un film d'horreur psychologique.")

        monkeypatch.setattr(scraper_tool.requests, "get", fake_get)

        result = scraper_tool.scrape_web_lore("Hereditary")

        assert result["found"] is True
        assert "Hereditary (film)" in result["context"]
        assert "film d'horreur psychologique" in result["context"]


class TestCleanAndTruncate:
    def test_strips_reference_sections(self):
        text = "Contenu principal.\n\n== Références ==\nDes trucs à jeter."
        cleaned = scraper_tool._clean_and_truncate(text)
        assert "Contenu principal." in cleaned
        assert "à jeter" not in cleaned

    def test_truncates_long_text_at_sentence_boundary(self):
        text = "Phrase un. " * 500  # bien plus long que _MAX_CHARS
        cleaned = scraper_tool._clean_and_truncate(text, max_chars=50)
        assert len(cleaned) <= 50 + len("\n\n[...] (résumé tronqué)")
        assert cleaned.endswith("[...] (résumé tronqué)")

    def test_short_text_is_untouched(self):
        text = "Un texte court."
        assert scraper_tool._clean_and_truncate(text) == text
