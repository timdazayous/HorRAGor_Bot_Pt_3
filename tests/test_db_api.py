"""
Tests unitaires — src/db_api (Couche Données)

db-api est le seul endroit du projet qui parle encore SQL directement à
Supabase (avec migrations/apply_migrations.py, cas à part documenté). Ici
psycopg2 est mocké via le pattern FakeCursor/FakeConnection déplacé depuis
tests/test_auth.py et tests/test_rag_tool.py — c'est la bonne frontière de
test maintenant que src/auth.py et src/tools/rag_tool.py ne font plus que
de l'HTTP vers ce service.
"""
from fastapi.testclient import TestClient

from src.db_api.main import app

client = TestClient(app)


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result or []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch_conn(monkeypatch, fake_conn):
    monkeypatch.setattr("src.db_api.main.get_conn", lambda: fake_conn)


class TestHealth:
    def test_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestGetUserByUsername:
    def test_found(self, monkeypatch):
        row = {"id": 1, "username": "streamlit-ui", "password_hash": "hash", "role": "user"}
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=row)))

        resp = client.get("/users/streamlit-ui")

        assert resp.status_code == 200
        assert resp.json() == row

    def test_not_found(self, monkeypatch):
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=None)))

        resp = client.get("/users/ghost")

        assert resp.status_code == 404


class TestCreateRefreshToken:
    def test_inserts_and_commits(self, monkeypatch):
        fake_cursor = FakeCursor()
        fake_conn = FakeConnection(fake_cursor)
        _patch_conn(monkeypatch, fake_conn)

        resp = client.post(
            "/refresh-tokens",
            json={"user_id": 1, "token_hash": "abc123", "expires_at": "2030-01-01T00:00:00+00:00"},
        )

        assert resp.status_code == 201
        assert any("INSERT INTO refresh_tokens" in q for q, _ in fake_cursor.executed)
        assert fake_conn.committed is True


class TestGetRefreshTokenByHash:
    def test_found(self, monkeypatch):
        row = {
            "id": 42, "user_id": 1, "expires_at": "2030-01-01T00:00:00+00:00",
            "revoked": False, "username": "streamlit-ui", "role": "user",
        }
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=row)))

        resp = client.get("/refresh-tokens/by-hash/abc123")

        assert resp.status_code == 200
        assert resp.json() == row

    def test_not_found(self, monkeypatch):
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=None)))

        resp = client.get("/refresh-tokens/by-hash/unknown")

        assert resp.status_code == 404


class TestRevokeRefreshToken:
    def test_revoke_by_id(self, monkeypatch):
        fake_cursor = FakeCursor()
        fake_conn = FakeConnection(fake_cursor)
        _patch_conn(monkeypatch, fake_conn)

        resp = client.patch("/refresh-tokens/42/revoke")

        assert resp.status_code == 200
        assert any("UPDATE refresh_tokens" in q for q, _ in fake_cursor.executed)
        assert fake_conn.committed is True

    def test_revoke_by_hash_is_idempotent(self, monkeypatch):
        """Même sémantique que l'UPDATE ... WHERE d'origine : 0 ligne touchée n'est pas une erreur."""
        fake_cursor = FakeCursor()
        fake_conn = FakeConnection(fake_cursor)
        _patch_conn(monkeypatch, fake_conn)

        resp = client.patch("/refresh-tokens/by-hash/never-issued/revoke")

        assert resp.status_code == 200


class TestRevokeAllTokensForUser:
    def test_revokes_and_commits(self, monkeypatch):
        fake_cursor = FakeCursor()
        fake_conn = FakeConnection(fake_cursor)
        _patch_conn(monkeypatch, fake_conn)

        resp = client.patch("/users/1/revoke-all-tokens")

        assert resp.status_code == 200
        assert any("UPDATE refresh_tokens" in q for q, _ in fake_cursor.executed)
        assert fake_conn.committed is True


class TestSearchFilm:
    def test_found(self, monkeypatch):
        row = {
            "title": "The Shining", "original_title": "The Shining", "year": 1980,
            "overview": "Synopsis.", "genres": ["Horror"], "tmdb_score": 8.2, "imdb_score": 8.4,
        }
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=row)))

        resp = client.get("/films/search", params={"title": "Shining"})

        assert resp.status_code == 200
        assert resp.json() == row

    def test_not_found(self, monkeypatch):
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=None)))

        resp = client.get("/films/search", params={"title": "Film inexistant"})

        assert resp.status_code == 404


class TestSurvivalFilm:
    def test_found(self, monkeypatch):
        row = {
            "title": "The Shining", "original_title": "The Shining", "year": 1980,
            "overview": "Synopsis.", "genres": ["Horror"],
            "horror_keywords": ["blood", "axe"], "richness_score": 80,
        }
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=row)))

        resp = client.get("/films/survival", params={"title": "The Shining"})

        assert resp.status_code == 200
        assert resp.json() == row

    def test_not_found(self, monkeypatch):
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=None)))

        resp = client.get("/films/survival", params={"title": "Film inexistant"})

        assert resp.status_code == 404


class TestFilmAge:
    def test_found_serializes_date_as_iso_string(self, monkeypatch):
        from datetime import date
        row = {"title": "The Shining", "original_title": "The Shining", "release_date": date(1980, 5, 23)}
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=row)))

        resp = client.get("/films/age", params={"title": "The Shining"})

        assert resp.status_code == 200
        # FastAPI sérialise un `date` natif en chaîne ISO 8601 — c'est précisément
        # ce que src/tools/rag_tool.py reconstruit avec date.fromisoformat().
        assert resp.json()["release_date"] == "1980-05-23"

    def test_not_found(self, monkeypatch):
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=None)))

        resp = client.get("/films/age", params={"title": "Film inexistant"})

        assert resp.status_code == 404


class TestFilmsBulkByIds:
    def test_empty_ids_returns_empty_list_without_db_call(self, monkeypatch):
        def _fail_if_called():
            raise AssertionError("get_conn ne devrait pas être appelé pour une liste vide")
        monkeypatch.setattr("src.db_api.main.get_conn", _fail_if_called)

        resp = client.post("/films/bulk-by-ids", json={"ids": []})

        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_matching_rows(self, monkeypatch):
        rows = [{"id": 10, "title": "First", "overview": "...", "year": 1999, "genres": ["Horror"], "tmdb_score": 7.0}]
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchall_result=rows)))

        resp = client.post("/films/bulk-by-ids", json={"ids": [10, 999]})

        assert resp.status_code == 200
        assert resp.json() == rows


class TestFindSourceFilm:
    def test_found(self, monkeypatch):
        row = {"id": 1, "title": "The Shining", "overview": "Un hôtel isolé..."}
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=row)))

        resp = client.get("/films/find-source", params={"title": "The Shining"})

        assert resp.status_code == 200
        assert resp.json() == row

    def test_not_found(self, monkeypatch):
        _patch_conn(monkeypatch, FakeConnection(FakeCursor(fetchone_result=None)))

        resp = client.get("/films/find-source", params={"title": "Film inexistant"})

        assert resp.status_code == 404
