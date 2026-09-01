"""Tests unitaires — src/rate_limit.py (anti brute-force sur les routes de login)."""
import asyncio

import pytest

from src import rate_limit


class FakeClient:
    def __init__(self, host: str):
        self.host = host


class FakeURL:
    def __init__(self, path: str):
        self.path = path


class FakeRequest:
    def __init__(self, host: str = "1.2.3.4", path: str = "/token"):
        self.client = FakeClient(host)
        self.url = FakeURL(path)


def _enforce(request: FakeRequest) -> None:
    asyncio.run(rate_limit.enforce_login_rate_limit(request))


@pytest.fixture(autouse=True)
def _reset_state():
    rate_limit.reset()
    yield
    rate_limit.reset()


class TestEnforceLoginRateLimit:
    def test_allows_requests_under_the_quota(self, monkeypatch):
        monkeypatch.setattr(rate_limit.config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 3)
        request = FakeRequest()

        for _ in range(3):
            _enforce(request)  # ne lève pas

    def test_rejects_once_the_quota_is_exceeded(self, monkeypatch):
        monkeypatch.setattr(rate_limit.config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 3)
        request = FakeRequest()

        for _ in range(3):
            _enforce(request)

        with pytest.raises(Exception) as exc_info:
            _enforce(request)
        assert exc_info.value.status_code == 429

    def test_different_ips_have_independent_quotas(self, monkeypatch):
        monkeypatch.setattr(rate_limit.config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 1)

        _enforce(FakeRequest(host="1.1.1.1"))
        _enforce(FakeRequest(host="2.2.2.2"))  # ne lève pas

    def test_different_routes_have_independent_quotas(self, monkeypatch):
        monkeypatch.setattr(rate_limit.config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 1)

        _enforce(FakeRequest(path="/token"))
        _enforce(FakeRequest(path="/auth/login"))  # ne lève pas

    def test_old_attempts_fall_outside_the_window(self, monkeypatch):
        monkeypatch.setattr(rate_limit.config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 1)
        monkeypatch.setattr(rate_limit.config, "RATE_LIMIT_LOGIN_WINDOW_SECONDS", 60)
        request = FakeRequest()

        fake_now = [1000.0]
        monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_now[0])

        _enforce(request)
        fake_now[0] += 61  # fenêtre expirée
        _enforce(request)  # ne lève pas : ancienne tentative purgée
