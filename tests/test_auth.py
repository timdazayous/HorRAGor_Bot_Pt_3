"""
Tests unitaires — src/auth.py (authentification par Refresh Tokens)

Aucune connexion réelle à Supabase : psycopg2 est mocké (mêmes fakes que
tests/test_rag_tool.py). Le flux réel a été validé manuellement contre la
vraie base au moment de l'implémentation.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src import auth, config


class FakeCursor:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self._fetchone_result


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


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake:fake@localhost/fake")


class TestPasswordHashing:
    def test_correct_password_verifies(self):
        hashed = auth.hash_password("correct-horse-battery-staple")
        assert auth.verify_password("correct-horse-battery-staple", hashed)

    def test_wrong_password_does_not_verify(self):
        hashed = auth.hash_password("correct-horse-battery-staple")
        assert not auth.verify_password("wrong-password", hashed)

    def test_hash_is_never_the_plaintext(self):
        hashed = auth.hash_password("secret")
        assert hashed != "secret"


class TestAccessToken:
    def test_roundtrip(self):
        token = auth.create_access_token(user_id=1, username="streamlit-ui")
        payload = auth.decode_access_token(token)
        assert payload["sub"] == "streamlit-ui"
        assert payload["user_id"] == 1
        assert payload["type"] == "access"
        assert payload["role"] == "user"

    def test_role_is_embedded_when_provided(self):
        token = auth.create_access_token(user_id=1, username="demo-admin", role="admin")
        payload = auth.decode_access_token(token)
        assert payload["role"] == "admin"

    def test_expired_token_is_rejected(self):
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": "streamlit-ui", "user_id": 1, "type": "access",
            "iat": now - timedelta(hours=1), "exp": now - timedelta(minutes=1),
        }
        token = jwt.encode(expired_payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

        with pytest.raises(auth.AuthError, match="expiré"):
            auth.decode_access_token(token)

    def test_tampered_token_is_rejected(self):
        token = auth.create_access_token(user_id=1, username="streamlit-ui")
        with pytest.raises(auth.AuthError):
            auth.decode_access_token(token + "tampered")

    def test_refresh_token_type_is_rejected_as_access_token(self):
        """Un token qui n'a pas type=access (ex: confusion avec un refresh JWT) doit être rejeté."""
        now = datetime.now(timezone.utc)
        wrong_type_payload = {
            "sub": "streamlit-ui", "user_id": 1, "type": "refresh",
            "iat": now, "exp": now + timedelta(minutes=30),
        }
        token = jwt.encode(wrong_type_payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

        with pytest.raises(auth.AuthError, match="pas un access token"):
            auth.decode_access_token(token)


class TestGetUserByUsername:
    def test_found(self, monkeypatch):
        row = {"id": 1, "username": "streamlit-ui", "password_hash": "hash", "role": "user"}
        monkeypatch.setattr(auth, "get_conn", lambda: FakeConnection(FakeCursor(fetchone_result=row)))

        user = auth.get_user_by_username("streamlit-ui")

        assert user == row

    def test_not_found(self, monkeypatch):
        monkeypatch.setattr(auth, "get_conn", lambda: FakeConnection(FakeCursor(fetchone_result=None)))

        assert auth.get_user_by_username("ghost") is None


class TestCreateRefreshToken:
    def test_inserts_and_commits(self, monkeypatch):
        fake_cursor = FakeCursor()
        fake_conn = FakeConnection(fake_cursor)
        monkeypatch.setattr(auth, "get_conn", lambda: fake_conn)

        raw_token = auth.create_refresh_token(user_id=1)

        assert isinstance(raw_token, str) and len(raw_token) > 20
        assert any("INSERT INTO refresh_tokens" in q for q, _ in fake_cursor.executed)
        assert fake_conn.committed is True


class TestRevokeAllTokensForUser:
    def test_revokes_and_commits(self, monkeypatch):
        fake_cursor = FakeCursor()
        fake_conn = FakeConnection(fake_cursor)
        monkeypatch.setattr(auth, "get_conn", lambda: fake_conn)

        auth.revoke_all_tokens_for_user(user_id=1)

        assert any("UPDATE refresh_tokens" in q for q, _ in fake_cursor.executed)
        assert fake_conn.committed is True


class TestAuthenticateUser:
    def test_valid_credentials(self, monkeypatch):
        password_hash = auth.hash_password("correct")
        monkeypatch.setattr(auth, "get_user_by_username",
                             lambda u: {"id": 1, "username": u, "password_hash": password_hash})

        user = auth.authenticate_user("streamlit-ui", "correct")
        assert user["username"] == "streamlit-ui"

    def test_wrong_password_raises(self, monkeypatch):
        password_hash = auth.hash_password("correct")
        monkeypatch.setattr(auth, "get_user_by_username",
                             lambda u: {"id": 1, "username": u, "password_hash": password_hash})

        with pytest.raises(auth.AuthError):
            auth.authenticate_user("streamlit-ui", "wrong")

    def test_unknown_user_raises(self, monkeypatch):
        monkeypatch.setattr(auth, "get_user_by_username", lambda u: None)

        with pytest.raises(auth.AuthError):
            auth.authenticate_user("ghost", "whatever")


class TestRefreshTokenLifecycle:
    def test_valid_unexpired_token_succeeds_and_gets_revoked(self, monkeypatch):
        row = {
            "id": 42, "user_id": 1, "revoked": False,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "username": "streamlit-ui", "role": "user",
        }
        fake_cursor = FakeCursor(fetchone_result=row)
        fake_conn = FakeConnection(fake_cursor)
        monkeypatch.setattr(auth, "get_conn", lambda: fake_conn)

        result = auth.validate_and_rotate_refresh_token("some-raw-token")

        assert result == {"user_id": 1, "username": "streamlit-ui", "role": "user"}
        # La rotation doit avoir émis un UPDATE ... revoked = TRUE
        assert any("UPDATE refresh_tokens" in q for q, _ in fake_cursor.executed)
        assert fake_conn.committed is True

    def test_unknown_token_raises(self, monkeypatch):
        fake_conn = FakeConnection(FakeCursor(fetchone_result=None))
        monkeypatch.setattr(auth, "get_conn", lambda: fake_conn)

        with pytest.raises(auth.AuthError, match="inconnu"):
            auth.validate_and_rotate_refresh_token("never-issued")

    def test_already_revoked_token_raises(self, monkeypatch):
        row = {
            "id": 1, "user_id": 1, "revoked": True,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "username": "streamlit-ui", "role": "user",
        }
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(auth, "get_conn", lambda: fake_conn)

        with pytest.raises(auth.AuthError, match="révoqué"):
            auth.validate_and_rotate_refresh_token("reused-token")

    def test_expired_token_raises(self, monkeypatch):
        row = {
            "id": 1, "user_id": 1, "revoked": False,
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
            "username": "streamlit-ui", "role": "user",
        }
        fake_conn = FakeConnection(FakeCursor(fetchone_result=row))
        monkeypatch.setattr(auth, "get_conn", lambda: fake_conn)

        with pytest.raises(auth.AuthError, match="expiré"):
            auth.validate_and_rotate_refresh_token("old-token")


class TestIssueTokenPair:
    def test_returns_both_tokens(self, monkeypatch):
        monkeypatch.setattr(auth, "create_refresh_token", lambda user_id: "fake-refresh-raw")

        tokens = auth.issue_token_pair(user_id=1, username="streamlit-ui")

        assert tokens["refresh_token"] == "fake-refresh-raw"
        assert tokens["token_type"] == "bearer"
        decoded = auth.decode_access_token(tokens["access_token"])
        assert decoded["sub"] == "streamlit-ui"
