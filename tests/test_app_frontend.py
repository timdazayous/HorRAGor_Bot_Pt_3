"""
Tests — app_frontend.py (interface Streamlit)

`_sanitize_markdown` et `_inject_judge_verdict` sont des fonctions pures/quasi
pures testées directement. Le smoke test `AppTest` (framework officiel
Streamlit) charge et exécute le script complet en simulant un vrai navigateur,
avec l'appel réseau vers l'API mocké.
"""
import httpx
import streamlit as st
from streamlit.testing.v1 import AppTest

import app_frontend


class TestSanitizeMarkdown:
    def test_dash_separator_after_text_gets_blank_line_inserted(self):
        text = "Un titre\n---\nLa suite du texte."
        result = app_frontend._sanitize_markdown(text)
        assert result == "Un titre\n\n---\nLa suite du texte."

    def test_dash_separator_at_start_is_untouched(self):
        text = "---\nDu texte après."
        assert app_frontend._sanitize_markdown(text) == text

    def test_equals_separator_is_also_handled(self):
        text = "Titre\n===\nSuite."
        result = app_frontend._sanitize_markdown(text)
        assert result == "Titre\n\n===\nSuite."

    def test_short_dash_sequence_is_untouched(self):
        # Moins de 3 tirets : ce n'est pas un setext heading, on ne touche rien.
        text = "Un titre\n--\nLa suite."
        assert app_frontend._sanitize_markdown(text) == text

    def test_no_separator_is_a_noop(self):
        text = "Juste du texte normal.\nSur plusieurs lignes."
        assert app_frontend._sanitize_markdown(text) == text


class TestInjectJudgeVerdict:
    def test_no_verdict_does_not_call_components_html(self, monkeypatch):
        called = {"html": False}
        monkeypatch.setattr(app_frontend.components, "html", lambda *a, **k: called.update(html=True))

        app_frontend._inject_judge_verdict(None)

        assert called["html"] is False

    def test_valid_high_confidence_shows_approved_label(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app_frontend.components, "html", lambda html, **k: captured.update(html=html))

        app_frontend._inject_judge_verdict({"is_valid": True, "confidence": 0.9, "reasoning": "Cohérent."})

        assert "LE JUGE A APPROUVÉ" in captured["html"]
        assert "90\xa0%" in captured["html"]  # espace insécable délibérée (pas de coupure de ligne)

    def test_valid_low_confidence_shows_mitige_label(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app_frontend.components, "html", lambda html, **k: captured.update(html=html))

        app_frontend._inject_judge_verdict({"is_valid": True, "confidence": 0.5, "reasoning": "Bof."})

        assert "LE JUGE EST MITIGÉ" in captured["html"]

    def test_invalid_shows_condemns_label(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app_frontend.components, "html", lambda html, **k: captured.update(html=html))

        app_frontend._inject_judge_verdict({"is_valid": False, "confidence": 0.1, "reasoning": "Hors sujet."})

        assert "LE JUGE CONDAMNE" in captured["html"]

    def test_tools_used_excludes_groq_llm_placeholder(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app_frontend.components, "html", lambda html, **k: captured.update(html=html))

        app_frontend._inject_judge_verdict(
            {"is_valid": True, "confidence": 0.9, "reasoning": "ok"},
            tools_used=["groq-llm", "rag_agent", "narration_agent"],
        )

        assert "rag_agent" in captured["html"]
        assert "narration_agent" in captured["html"]

    def test_reasoning_is_html_escaped(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app_frontend.components, "html", lambda html, **k: captured.update(html=html))

        app_frontend._inject_judge_verdict({"is_valid": True, "confidence": 0.9, "reasoning": 'Il a dit "salut"'})

        assert "&quot;salut&quot;" in captured["html"]

    def test_long_reasoning_is_truncated(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app_frontend.components, "html", lambda html, **k: captured.update(html=html))

        app_frontend._inject_judge_verdict({"is_valid": True, "confidence": 0.9, "reasoning": "x" * 200})

        assert "…" in captured["html"]


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erreur", request=None, response=self)

    def json(self):
        return self._payload


def _make_fake_post(chat_answer: str):
    """
    Route par URL : /auth/login et /auth/refresh renvoient une paire de
    tokens, l'endpoint /chat renvoie la réponse de l'agent — reproduit le
    flux réel (login silencieux avant le premier /chat).
    """
    def fake_post(url, json=None, timeout=None, headers=None):
        if url.endswith("/auth/login") or url.endswith("/auth/refresh"):
            return _FakeResponse({"access_token": "fake-access", "refresh_token": "fake-refresh", "token_type": "bearer"})
        return _FakeResponse({
            "answer": chat_answer,
            "tools_used": ["rag_agent", "narration_agent"],
            "judge_verdict": {"is_valid": True, "confidence": 0.9, "reasoning": "ok"},
        })
    return fake_post


class TestAppSmoke:
    def test_app_loads_without_exception(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", _make_fake_post("Une réponse gothique de test."))

        at = AppTest.from_file("app_frontend.py")
        at.run(timeout=30)

        assert not at.exception

    def test_submitting_a_question_shows_the_answer(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", _make_fake_post("Voici une réponse gothique de test."))

        at = AppTest.from_file("app_frontend.py")
        at.run(timeout=30)
        at.chat_input[0].set_value("Parle-moi de The Shining").run(timeout=30)

        assert not at.exception
        assert len(at.chat_message) == 2  # question utilisateur + réponse assistant
        rendered_texts = [md.value for m in at.chat_message for md in m.markdown]
        assert "Parle-moi de The Shining" in rendered_texts
        assert "Voici une réponse gothique de test." in rendered_texts


class TestAuthenticatedPost:
    """Le login est silencieux pour l'utilisateur : ces tests vérifient la mécanique de retry/refresh."""

    def setup_method(self):
        if "tokens" in st.session_state:
            del st.session_state["tokens"]

    def test_logs_in_once_then_reuses_the_token(self, monkeypatch):
        calls = []

        def fake_post(url, json=None, timeout=None, headers=None):
            calls.append(url)
            if url == app_frontend.AUTH_LOGIN_URL:
                return _FakeResponse({"access_token": "tok-1", "refresh_token": "ref-1"})
            return _FakeResponse({"answer": "ok"})

        monkeypatch.setattr(httpx, "post", fake_post)

        app_frontend._authenticated_post(app_frontend.API_URL, json={"question": "a"}, timeout=5.0)
        app_frontend._authenticated_post(app_frontend.API_URL, json={"question": "b"}, timeout=5.0)

        assert calls.count(app_frontend.AUTH_LOGIN_URL) == 1  # un seul login pour les deux appels
        assert calls.count(app_frontend.API_URL) == 2

    def test_401_triggers_refresh_then_retries(self, monkeypatch):
        st.session_state.tokens = {"access_token": "expired", "refresh_token": "ref-old"}
        chat_calls = []

        def fake_post(url, json=None, timeout=None, headers=None):
            if url == app_frontend.AUTH_REFRESH_URL:
                return _FakeResponse({"access_token": "tok-new", "refresh_token": "ref-new"})
            if url == app_frontend.API_URL:
                chat_calls.append(headers["Authorization"])
                if len(chat_calls) == 1:
                    return _FakeResponse({"detail": "expired"}, status_code=401)
                return _FakeResponse({"answer": "ok"})
            raise AssertionError(f"URL inattendue : {url}")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = app_frontend._authenticated_post(app_frontend.API_URL, json={"question": "a"}, timeout=5.0)

        assert response.status_code == 200
        assert chat_calls == ["Bearer expired", "Bearer tok-new"]
        assert st.session_state.tokens["access_token"] == "tok-new"

    def test_falls_back_to_full_login_if_refresh_token_also_invalid(self, monkeypatch):
        st.session_state.tokens = {"access_token": "expired", "refresh_token": "also-expired"}
        chat_calls = []

        def fake_post(url, json=None, timeout=None, headers=None):
            if url == app_frontend.AUTH_REFRESH_URL:
                return _FakeResponse({"detail": "expired"}, status_code=401)
            if url == app_frontend.AUTH_LOGIN_URL:
                return _FakeResponse({"access_token": "tok-fresh", "refresh_token": "ref-fresh"})
            if url == app_frontend.API_URL:
                chat_calls.append(headers["Authorization"])
                return _FakeResponse({"answer": "ok"} if len(chat_calls) > 1 else {"detail": "expired"},
                                      status_code=200 if len(chat_calls) > 1 else 401)
            raise AssertionError(f"URL inattendue : {url}")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = app_frontend._authenticated_post(app_frontend.API_URL, json={"question": "a"}, timeout=5.0)

        assert response.status_code == 200
        assert st.session_state.tokens["access_token"] == "tok-fresh"
