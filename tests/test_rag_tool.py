"""
Tests unitaires — src/tools/rag_tool.py

Aucune connexion réelle à Supabase ni chargement du modèle FAISS : tout est
mocké (psycopg2, retriever) pour des tests rapides et déterministes.
"""
import numpy as np
import pytest

from src.tools import rag_tool


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result or []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self, *args, **kwargs):
        return self._cursor

    def close(self):
        pass


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Empêche tout test de cette suite de toucher au réseau/DB par erreur."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake:fake@localhost/fake")


class TestMatchExactMovie:
    def test_found_row_is_formatted(self, monkeypatch):
        row = {
            "title": "The Shining", "original_title": "The Shining", "year": 1980,
            "overview": "Jack Torrance devient gardien d'un hôtel isolé.",
            "genres": ["Horror", "Thriller"], "tmdb_score": 8.2, "imdb_score": 8.4,
        }
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool._match_exact_movie("Shining")

        assert result == row

    def test_no_row_returns_none(self, monkeypatch):
        fake_conn = FakeConnection(FakeCursor(fetchone_result=None))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        assert rag_tool._match_exact_movie("Film inexistant") is None

    def test_db_error_returns_none(self, monkeypatch):
        def _raise():
            raise ConnectionError("DB down")
        monkeypatch.setattr(rag_tool, "_get_conn", _raise)

        assert rag_tool._match_exact_movie("The Shining") is None


class TestFormatMovie:
    def test_includes_original_title_when_different(self):
        row = {
            "title": "Shining", "original_title": "The Shining", "year": 1980,
            "overview": "Synopsis.", "genres": ["Horror"], "tmdb_score": 8.2, "imdb_score": None,
        }
        text = rag_tool._format_movie(row)
        assert "Shining (The Shining)" in text
        assert "TMDB : 8.2/10" in text
        assert "IMDB" not in text.split("Notes")[1].split("\n")[0] or "Non disponible" not in text

    def test_missing_overview_says_so(self):
        row = {"title": "X", "original_title": None, "year": None, "overview": None, "genres": None}
        text = rag_tool._format_movie(row)
        assert "Aucun synopsis disponible." in text


class TestGetSurvivalContext:
    def test_found_film_with_keywords(self, monkeypatch):
        row = {
            "title": "The Shining", "original_title": "The Shining", "year": 1980,
            "overview": "Jack Torrance devient gardien d'un hôtel isolé.",
            "genres": ["Horror", "Thriller"],
            "horror_keywords": ["blood", "ghost", "axe"], "richness_score": 80,
        }
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.get_survival_context("The Shining")

        assert result["is_complete"] is True
        assert result["matched_title"] == "The Shining"
        assert "blood, ghost, axe" in result["context"]

    def test_found_film_without_keywords_omits_the_line(self, monkeypatch):
        row = {
            "title": "Obscure Movie", "original_title": None, "year": 2020,
            "overview": "Synopsis.", "genres": [], "horror_keywords": None, "richness_score": None,
        }
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.get_survival_context("Obscure Movie")

        assert "Éléments d'horreur clés" not in result["context"]

    def test_not_found_is_incomplete(self, monkeypatch):
        fake_conn = FakeConnection(FakeCursor(fetchone_result=None))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.get_survival_context("Film inexistant")

        assert result["is_complete"] is False
        assert result["matched_title"] is None

    def test_db_error_is_incomplete(self, monkeypatch):
        def _raise():
            raise ConnectionError("DB down")
        monkeypatch.setattr(rag_tool, "_get_conn", _raise)

        result = rag_tool.get_survival_context("The Shining")

        assert result["is_complete"] is False


class TestCalculateMovieAge:
    def test_computes_age_from_release_date(self, monkeypatch):
        from datetime import date
        row = {"title": "The Shining", "original_title": "The Shining", "release_date": date(1980, 5, 23)}
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.calculate_movie_age("The Shining")

        assert result["is_complete"] is True
        assert result["matched_title"] == "The Shining"
        assert "1980" in result["context"]

    def test_not_found_is_incomplete(self, monkeypatch):
        fake_conn = FakeConnection(FakeCursor(fetchone_result=None))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.calculate_movie_age("Film inexistant")

        assert result["is_complete"] is False
        assert result["matched_title"] is None

    def test_missing_release_date_is_incomplete(self, monkeypatch):
        row = {"title": "X", "original_title": None, "release_date": None}
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.calculate_movie_age("X")

        assert result["is_complete"] is False
        assert result["matched_title"] == "X"

    def test_db_error_is_incomplete(self, monkeypatch):
        def _raise():
            raise ConnectionError("DB down")
        monkeypatch.setattr(rag_tool, "_get_conn", _raise)

        result = rag_tool.calculate_movie_age("The Shining")

        assert result["is_complete"] is False


class TestFindSimilarMovies:
    def test_excludes_source_film_and_formats_results(self, monkeypatch):
        source_row = {"id": 1, "title": "The Shining", "overview": "Un hôtel isolé..."}
        similar_rows = [
            {"id": 2, "title": "Sleepy Hollow", "overview": "...", "year": 1999, "genres": ["Horror"], "tmdb_score": 7.2},
        ]
        fake_cursor = FakeCursor(fetchone_result=source_row, fetchall_result=similar_rows)
        fake_conn = FakeConnection(fake_cursor)
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        fake_model = type("M", (), {"encode": lambda self, texts, normalize_embeddings: np.array([[0.1, 0.2]])})()
        fake_index = type("I", (), {"search": lambda self, vec, k: (np.array([[0.9, 0.8]]), np.array([[0, 1]]))})()
        fake_id_map = np.array([1, 2])  # index 0 = film source (id=1), exclu du résultat
        monkeypatch.setattr(rag_tool, "_get_retriever", lambda: (fake_model, fake_index, fake_id_map))

        result = rag_tool.find_similar_movies("The Shining", k=5)

        assert result["is_complete"] is True
        assert result["matched_title"] == "The Shining"
        assert "1. Sleepy Hollow" in result["context"]
        # "The Shining" n'apparaît que dans l'en-tête ("Films similaires à « The
        # Shining »"), jamais comme entrée de la liste numérotée (film source exclu).
        assert result["context"].count("The Shining") == 1

    def test_source_not_found_is_incomplete(self, monkeypatch):
        fake_conn = FakeConnection(FakeCursor(fetchone_result=None))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool.find_similar_movies("Film inexistant")

        assert result["is_complete"] is False
        assert result["matched_title"] is None

    def test_db_error_is_incomplete(self, monkeypatch):
        def _raise():
            raise ConnectionError("DB down")
        monkeypatch.setattr(rag_tool, "_get_conn", _raise)

        result = rag_tool.find_similar_movies("The Shining")

        assert result["is_complete"] is False


class TestRagSearchTitle:
    def test_exact_match_with_overview_is_complete(self, monkeypatch):
        row = {
            "title": "The Shining", "original_title": "The Shining", "year": 1980,
            "overview": "Synopsis complet.", "genres": ["Horror"], "tmdb_score": 8.2, "imdb_score": 8.4,
        }
        monkeypatch.setattr(rag_tool, "_match_exact_movie", lambda q: row)

        result = rag_tool.rag_search("The Shining", is_title=True)

        assert result["is_complete"] is True
        assert result["matched_title"] == "The Shining"

    def test_exact_match_without_overview_is_incomplete(self, monkeypatch):
        row = {
            "title": "Obscure Movie", "original_title": None, "year": 2020,
            "overview": None, "genres": [], "tmdb_score": None, "imdb_score": None,
        }
        monkeypatch.setattr(rag_tool, "_match_exact_movie", lambda q: row)

        result = rag_tool.rag_search("Obscure Movie", is_title=True)

        assert result["is_complete"] is False
        assert result["matched_title"] == "Obscure Movie"

    def test_no_match_is_incomplete_and_never_falls_back_to_semantic(self, monkeypatch):
        monkeypatch.setattr(rag_tool, "_match_exact_movie", lambda q: None)
        called = {"semantic": False}

        def _fail_if_called(*args, **kwargs):
            called["semantic"] = True
            return []

        monkeypatch.setattr(rag_tool, "_semantic_search", _fail_if_called)

        result = rag_tool.rag_search("Skinamarink", is_title=True)

        assert result["is_complete"] is False
        assert result["matched_title"] is None
        assert called["semantic"] is False


class TestRagSearchTheme:
    def test_score_above_threshold_is_complete(self, monkeypatch):
        film = {"id": 1, "title": "Ghost Story", "year": 2020, "genres": ["Horror"],
                "tmdb_score": 7.0, "overview": "Une histoire de fantômes."}
        monkeypatch.setattr(rag_tool, "_semantic_search", lambda q, k=5: [(0.72, film)])

        result = rag_tool.rag_search("un film avec des fantômes", is_title=False)

        assert result["is_complete"] is True
        assert result["matched_title"] == "Ghost Story"
        assert "Ghost Story" in result["context"]

    def test_score_below_threshold_is_incomplete(self, monkeypatch):
        film = {"id": 1, "title": "Unrelated Movie", "year": 1999, "genres": [],
                "tmdb_score": None, "overview": "Sans rapport."}
        monkeypatch.setattr(rag_tool, "_semantic_search", lambda q, k=5: [(0.1, film)])

        result = rag_tool.rag_search("un sujet très pointu", is_title=False)

        assert result["is_complete"] is False
        assert result["matched_title"] is None

    def test_no_hits_is_incomplete(self, monkeypatch):
        monkeypatch.setattr(rag_tool, "_semantic_search", lambda q, k=5: [])

        result = rag_tool.rag_search("rien ne matche", is_title=False)

        assert result["is_complete"] is False


class TestFetchFilmsFromDb:
    def test_empty_ids_short_circuits_without_db_call(self, monkeypatch):
        def _fail_if_called():
            raise AssertionError("_get_conn ne devrait pas être appelé pour une liste vide")
        monkeypatch.setattr(rag_tool, "_get_conn", _fail_if_called)

        assert rag_tool._fetch_films_from_db([]) == []

    def test_preserves_requested_order(self, monkeypatch):
        rows = [{"id": 20, "title": "Second"}, {"id": 10, "title": "First"}]
        fake_conn = FakeConnection(FakeCursor(fetchall_result=rows))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool._fetch_films_from_db([10, 20])

        assert [f["title"] for f in result] == ["First", "Second"]

    def test_missing_id_is_silently_skipped(self, monkeypatch):
        rows = [{"id": 10, "title": "First"}]
        fake_conn = FakeConnection(FakeCursor(fetchall_result=rows))
        monkeypatch.setattr(rag_tool, "_get_conn", lambda: fake_conn)

        result = rag_tool._fetch_films_from_db([10, 999])

        assert len(result) == 1

    def test_db_error_returns_empty_list(self, monkeypatch):
        def _raise():
            raise ConnectionError("DB down")
        monkeypatch.setattr(rag_tool, "_get_conn", _raise)

        assert rag_tool._fetch_films_from_db([1, 2]) == []


class TestSemanticSearch:
    def test_pairs_scores_with_films_preserving_order(self, monkeypatch):
        fake_model = type("M", (), {"encode": lambda self, texts, normalize_embeddings: np.array([[0.1, 0.2]])})()
        fake_index = type("I", (), {"search": lambda self, vec, k: (np.array([[0.9, 0.5]]), np.array([[0, 1]]))})()
        fake_id_map = np.array([10, 20])

        monkeypatch.setattr(rag_tool, "_get_retriever", lambda: (fake_model, fake_index, fake_id_map))
        monkeypatch.setattr(
            rag_tool, "_fetch_films_from_db",
            lambda ids: [{"id": i, "title": f"Film {i}"} for i in ids],
        )

        hits = rag_tool._semantic_search("query", k=2)

        assert [score for score, _ in hits] == [0.9, 0.5]
        assert [f["id"] for _, f in hits] == [10, 20]
