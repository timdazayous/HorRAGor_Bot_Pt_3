"""
Tests unitaires — src/auth.py (authentification par Refresh Tokens)

Aucune connexion réelle à db-api/Supabase : src.auth.db_request (le seul
point de sortie HTTP vers le micro-service db-api, Couche Données) est
mocké. Le flux réel a été validé manuellement contre la vraie base au
moment de l'implémentation initiale, et de nouveau après le passage à
db-api (voir test_e2e.py pour le scénario de bout en bout).
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src import auth, config


class FakeResponse:
    """Imite juste assez httpx.Response pour les call sites de src/auth.py."""

    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


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
        monkeypatch.setattr(auth, "db_request", lambda method, path, **kw: FakeResponse(200, row))

        user = auth.get_user_by_username("streamlit-ui")

        assert user == row

    def test_not_found(self, monkeypatch):
        monkeypatch.setattr(auth, "db_request", lambda method, path, **kw: FakeResponse(404))

        assert auth.get_user_by_username("ghost") is None


class TestCreateRefreshToken:
    def test_inserts_and_returns_raw_token(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            auth, "db_request",
            lambda method, path, **kw: calls.append((method, path, kw)) or FakeResponse(201, {"status": "created"}),
        )

        raw_token = auth.create_refresh_token(user_id=1)

        assert isinstance(raw_token, str) and len(raw_token) > 20
        method, path, kw = calls[0]
        assert method == "POST" and path == "/refresh-tokens"
        assert kw["json"]["user_id"] == 1


class TestRevokeRefreshToken:
    def test_revokes(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            auth, "db_request",
            lambda method, path, **kw: calls.append((method, path)) or FakeResponse(200, {"status": "revoked"}),
        )

        auth.revoke_refresh_token("some-raw-refresh-token")

        assert calls[0][0] == "PATCH" and "/revoke" in calls[0][1]

    def test_is_idempotent_on_unknown_token(self, monkeypatch):
        """Pas d'exception si le token est déjà révoqué/inconnu (anti-énumération)."""
        monkeypatch.setattr(auth, "db_request", lambda method, path, **kw: FakeResponse(200, {"status": "revoked"}))

        auth.revoke_refresh_token("never-issued-token")  # ne lève pas


class TestRevokeAllTokensForUser:
    def test_revokes(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            auth, "db_request",
            lambda method, path, **kw: calls.append((method, path)) or FakeResponse(200, {"status": "revoked"}),
        )

        auth.revoke_all_tokens_for_user(user_id=1)

        assert calls[0][0] == "PATCH" and "revoke-all-tokens" in calls[0][1]


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
            # Comme db-api, sérialisé en ISO 8601 (traversée JSON).
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "username": "streamlit-ui", "role": "user",
        }
        calls = []

        def fake_db_request(method, path, **kw):
            calls.append((method, path))
            if method == "GET":
                return FakeResponse(200, row)
            return FakeResponse(200, {"status": "revoked"})

        monkeypatch.setattr(auth, "db_request", fake_db_request)

        result = auth.validate_and_rotate_refresh_token("some-raw-token")

        assert result == {"user_id": 1, "username": "streamlit-ui", "role": "user"}
        # La rotation doit avoir émis un PATCH .../revoke après le GET.
        assert calls[0][0] == "GET"
        assert calls[1] == ("PATCH", "/refresh-tokens/42/revoke")

    def test_unknown_token_raises(self, monkeypatch):
        monkeypatch.setattr(auth, "db_request", lambda method, path, **kw: FakeResponse(404))

        with pytest.raises(auth.AuthError, match="inconnu"):
            auth.validate_and_rotate_refresh_token("never-issued")

    def test_already_revoked_token_raises(self, monkeypatch):
        row = {
            "id": 1, "user_id": 1, "revoked": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "username": "streamlit-ui", "role": "user",
        }
        monkeypatch.setattr(auth, "db_request", lambda method, path, **kw: FakeResponse(200, row))

        with pytest.raises(auth.AuthError, match="révoqué"):
            auth.validate_and_rotate_refresh_token("reused-token")

    def test_expired_token_raises(self, monkeypatch):
        row = {
            "id": 1, "user_id": 1, "revoked": False,
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "username": "streamlit-ui", "role": "user",
        }
        monkeypatch.setattr(auth, "db_request", lambda method, path, **kw: FakeResponse(200, row))

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
