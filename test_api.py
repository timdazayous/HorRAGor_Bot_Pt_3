"""
Tests de l'API FastAPI HorRAGor BOT

Le graphe multi-agent (src.main.agent_graph) est mocké pour tous ces tests :
aucun appel Groq, Supabase ou Wikipedia réel n'est déclenché — la logique du
graphe elle-même est testée séparément dans tests/test_graph_pipeline.py.
"""

import secrets

import jwt
import pytest
from fastapi.testclient import TestClient

import src.main as main_module
from src import config
from src import rate_limit as rate_limit_module
from src.main import ChatRequest, ChatResponse, JudgeVerdict, app, require_auth

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Isole chaque test du compteur anti brute-force (état module-level partagé)."""
    rate_limit_module.reset()
    yield
    rate_limit_module.reset()


@pytest.fixture(autouse=True)
def mock_agent_graph(monkeypatch):
    """Remplace l'invocation réelle du graphe par une réponse déterministe."""
    def fake_invoke(state, config=None):
        return {
            "final_answer": "Une réponse gothique simulée pour les tests.",
            "tools_used": ["rag_agent", "narration_agent", "judge_agent"],
            "judge_verdict": {"is_valid": True, "confidence": 0.9, "reasoning": "Cohérent (mock)."},
        }
    monkeypatch.setattr(main_module.agent_graph, "invoke", fake_invoke)


@pytest.fixture(autouse=True)
def bypass_auth():
    """
    /chat exige une authentification (Refresh Tokens) — ces tests portent sur
    le contrat de l'API, pas sur l'auth elle-même (voir tests/test_auth.py et
    TestAuthEndpoints ci-dessous) : on neutralise la dépendance par défaut.
    """
    app.dependency_overrides[require_auth] = lambda: {"sub": "test-user", "user_id": 1}
    yield
    app.dependency_overrides.pop(require_auth, None)


class TestHealthEndpoint:
    """Tests de l'endpoint /health"""

    def test_health_check_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestChatEndpoint:
    """Tests de l'endpoint /chat"""

    def test_chat_with_valid_request(self):
        """Test d'une requête valide"""
        payload = {
            "question": "Recommande-moi un film d'horreur",
            "user_id": "test_user",
            "conversation_id": "test_conv"
        }

        response = client.post("/chat", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "answer" in data
        assert "tools_used" in data
        assert "conversation_id" in data
        assert isinstance(data["tools_used"], list)

    def test_chat_with_minimal_request(self):
        """Test avec seulement la question obligatoire"""
        payload = {"question": "Parle-moi de The Shining"}

        response = client.post("/chat", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "answer" in data

    def test_chat_with_history_is_forwarded(self, monkeypatch):
        """L'historique {role, content} doit être converti en messages LangChain."""
        captured = {}

        def fake_invoke(state, config=None):
            captured["messages"] = state["messages"]
            return {
                "final_answer": "ok",
                "tools_used": [],
                "judge_verdict": None,
            }
        monkeypatch.setattr(main_module.agent_graph, "invoke", fake_invoke)

        payload = {
            "question": "Et son année de sortie ?",
            "history": [
                {"role": "user", "content": "Parle-moi de The Shining"},
                {"role": "assistant", "content": "Un chef-d'oeuvre de 1980."},
            ],
        }
        response = client.post("/chat", json=payload)

        assert response.status_code == 200
        assert len(captured["messages"]) == 3  # 2 historique + la question courante
        assert captured["messages"][-1].content == "Et son année de sortie ?"

    def test_chat_with_empty_question(self):
        """Test avec une question vide"""
        payload = {"question": ""}

        response = client.post("/chat", json=payload)
        assert response.status_code == 422  # Validation error

    def test_chat_with_missing_question(self):
        """Test sans la question"""
        payload = {"user_id": "test"}

        response = client.post("/chat", json=payload)
        assert response.status_code == 422  # Validation error

    def test_chat_propagates_graph_exception_as_500(self, monkeypatch):
        """Une exception dans le graphe doit remonter en 500, pas planter le process."""
        def fake_invoke(state, config=None):
            raise RuntimeError("Groq indisponible")
        monkeypatch.setattr(main_module.agent_graph, "invoke", fake_invoke)

        response = client.post("/chat", json={"question": "Test"})

        assert response.status_code == 500

    def test_chat_response_structure(self):
        """Test que la réponse a la bonne structure"""
        payload = {
            "question": "Test question",
            "user_id": "user1",
            "conversation_id": "conv1"
        }

        response = client.post("/chat", json=payload)
        assert response.status_code == 200

        data = response.json()

        # Vérifier les champs requis
        assert "answer" in data
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

        assert "tools_used" in data
        assert isinstance(data["tools_used"], list)

        assert "conversation_id" in data

        # Vérifier le judge_verdict si présent
        if data.get("judge_verdict"):
            verdict = data["judge_verdict"]
            assert "is_valid" in verdict
            assert "confidence" in verdict
            assert "reasoning" in verdict
            assert isinstance(verdict["is_valid"], bool)
            assert 0.0 <= verdict["confidence"] <= 1.0


class TestPydanticModels:
    """Tests de validation des modèles Pydantic"""

    def test_chat_request_validation(self):
        """Test la validation de ChatRequest"""
        # Valid request
        req = ChatRequest(question="Test question")
        assert req.question == "Test question"

        # Question vide
        with pytest.raises(ValueError):
            ChatRequest(question="")

        # Question trop longue
        with pytest.raises(ValueError):
            ChatRequest(question="x" * 6000)

    def test_judge_verdict_validation(self):
        """Test la validation de JudgeVerdict"""
        # Valid verdict
        verdict = JudgeVerdict(
            is_valid=True,
            confidence=0.85,
            reasoning="Test reasoning"
        )
        assert verdict.is_valid is True
        assert verdict.confidence == 0.85

        # Confidence en dehors de [0, 1]
        with pytest.raises(ValueError):
            JudgeVerdict(
                is_valid=True,
                confidence=1.5,
                reasoning="Test"
            )

    def test_chat_response_validation(self):
        """Test la validation de ChatResponse"""
        response = ChatResponse(
            answer="Test answer",
            conversation_id="conv123",
            tools_used=["tool1", "tool2"],
            judge_verdict=JudgeVerdict(
                is_valid=True,
                confidence=0.9,
                reasoning="Valid"
            )
        )
        assert response.answer == "Test answer"
        assert len(response.tools_used) == 2


class TestErrorHandling:
    """Tests de gestion des erreurs"""

    def test_chat_with_very_long_question(self):
        """Test avec une question trop longue"""
        payload = {"question": "x" * 5001}

        response = client.post("/chat", json=payload)
        assert response.status_code == 422

    def test_invalid_json(self):
        """Test avec du JSON invalide"""
        response = client.post(
            "/chat",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422


class TestInfoEndpoint:
    """Tests de l'endpoint /info"""

    def test_info_returns_agents(self):
        """Test que /info retourne les 4 agents du graphe multi-agent"""
        response = client.get("/info")
        assert response.status_code == 200

        data = response.json()
        assert "agents" in data
        assert len(data["agents"]) == 4
        assert any("rag_agent" in a for a in data["agents"])
        assert any("scraper_agent" in a for a in data["agents"])
        assert any("narration_agent" in a for a in data["agents"])
        assert any("judge_agent" in a for a in data["agents"])

    def test_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"


class TestAuthEndpoints:
    """
    Tests du flux d'authentification réel — la dépendance require_auth n'est
    PAS neutralisée ici : c'est justement ce qu'on veut vérifier.
    src.auth (DB/JWT) est mocké : aucun appel réseau réel.
    """

    def test_chat_without_token_is_rejected(self):
        app.dependency_overrides.pop(require_auth, None)
        response = client.post("/chat", json={"question": "test"})
        assert response.status_code == 401

    def test_chat_with_invalid_token_is_rejected(self):
        app.dependency_overrides.pop(require_auth, None)
        response = client.post(
            "/chat", json={"question": "test"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 401

    def test_chat_without_token_never_invokes_the_graph(self, monkeypatch):
        """401 doit être renvoyé avant même l'exécution du moindre nœud du graphe."""
        app.dependency_overrides.pop(require_auth, None)

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("Le graphe ne doit jamais être invoqué sans authentification")
        monkeypatch.setattr(main_module.agent_graph, "invoke", _fail_if_called)

        response = client.post("/chat", json={"question": "test"})

        assert response.status_code == 401

    def test_chat_with_a_real_refresh_token_is_rejected(self):
        """
        Un refresh token (chaîne opaque, pas un JWT) présenté sur une route de
        ressource doit être refusé — il échoue simplement au décodage JWT.
        """
        app.dependency_overrides.pop(require_auth, None)
        opaque_refresh_token = secrets.token_urlsafe(48)

        response = client.post(
            "/chat", json={"question": "test"},
            headers={"Authorization": f"Bearer {opaque_refresh_token}"},
        )

        assert response.status_code == 401

    def test_chat_with_a_refresh_typed_jwt_is_rejected(self):
        """
        Même si un refresh token était un JWT bien formé avec type=refresh
        (défense en profondeur), il doit être refusé sur une route protégée
        par require_auth — seul type=access est accepté.
        """
        app.dependency_overrides.pop(require_auth, None)
        refresh_payload = {"sub": "someone", "user_id": 1, "type": "refresh"}
        forged_refresh_jwt = jwt.encode(
            refresh_payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM
        )

        response = client.post(
            "/chat", json={"question": "test"},
            headers={"Authorization": f"Bearer {forged_refresh_jwt}"},
        )

        assert response.status_code == 401

    def test_chat_with_none_algorithm_token_is_rejected(self):
        """L'algorithme est imposé (HS256) — un token signé avec 'none' doit être refusé."""
        app.dependency_overrides.pop(require_auth, None)
        forged_unsigned_token = jwt.encode(
            {"sub": "attacker", "user_id": 1, "type": "access"}, key=None, algorithm="none"
        )

        response = client.post(
            "/chat", json={"question": "test"},
            headers={"Authorization": f"Bearer {forged_unsigned_token}"},
        )

        assert response.status_code == 401

    def test_chat_rejects_malformed_body_even_when_authenticated(self):
        """Le corps est validé par un modèle Pydantic — pas de dict brut accepté tel quel."""
        token = main_module.auth.create_access_token(user_id=1, username="streamlit-ui")
        response = client.post(
            "/chat", json={"not_a_question_field": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    def test_login_success_returns_token_pair(self, monkeypatch):
        monkeypatch.setattr(
            main_module.auth, "authenticate_user",
            lambda username, password: {"id": 1, "username": username, "role": "user"},
        )
        monkeypatch.setattr(
            main_module.auth, "issue_token_pair",
            lambda user_id, username, role="user": {
                "access_token": "a", "refresh_token": "b", "token_type": "bearer"
            },
        )

        response = client.post("/auth/login", json={"username": "streamlit-ui", "password": "correct"})

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "a"
        assert data["refresh_token"] == "b"

    def test_login_failure_returns_401_with_www_authenticate_header(self, monkeypatch):
        def _raise(username, password):
            raise main_module.auth.AuthError("Identifiants invalides")
        monkeypatch.setattr(main_module.auth, "authenticate_user", _raise)

        response = client.post("/auth/login", json={"username": "streamlit-ui", "password": "wrong"})

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_token_endpoint_success_returns_token_pair(self, monkeypatch):
        monkeypatch.setattr(
            main_module.auth, "authenticate_user",
            lambda username, password: {"id": 1, "username": username, "role": "admin"},
        )
        captured = {}

        def _issue(user_id, username, role="user"):
            captured["role"] = role
            return {"access_token": "a", "refresh_token": "b", "token_type": "bearer"}
        monkeypatch.setattr(main_module.auth, "issue_token_pair", _issue)

        response = client.post(
            "/token", data={"username": "demo-admin", "password": "correct"}
        )

        assert response.status_code == 200
        assert response.json()["access_token"] == "a"
        assert captured["role"] == "admin"

    def test_token_endpoint_failure_returns_401(self, monkeypatch):
        def _raise(username, password):
            raise main_module.auth.AuthError("Identifiants invalides")
        monkeypatch.setattr(main_module.auth, "authenticate_user", _raise)

        response = client.post("/token", data={"username": "demo-user", "password": "wrong"})

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_refresh_success_returns_new_token_pair(self, monkeypatch):
        monkeypatch.setattr(
            main_module.auth, "validate_and_rotate_refresh_token",
            lambda raw_token: {"user_id": 1, "username": "streamlit-ui", "role": "user"},
        )
        monkeypatch.setattr(
            main_module.auth, "issue_token_pair",
            lambda user_id, username, role="user": {
                "access_token": "new-a", "refresh_token": "new-b", "token_type": "bearer"
            },
        )

        response = client.post("/auth/refresh", json={"refresh_token": "some-refresh-token"})

        assert response.status_code == 200
        assert response.json()["access_token"] == "new-a"

    def test_refresh_with_revoked_token_returns_401(self, monkeypatch):
        def _raise(raw_token):
            raise main_module.auth.AuthError("Refresh token déjà révoqué")
        monkeypatch.setattr(main_module.auth, "validate_and_rotate_refresh_token", _raise)

        response = client.post("/auth/refresh", json={"refresh_token": "already-used"})

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_chat_with_valid_token_succeeds(self):
        app.dependency_overrides.pop(require_auth, None)
        token = main_module.auth.create_access_token(user_id=1, username="streamlit-ui")
        response = client.post(
            "/chat", json={"question": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestAdminEndpoints:
    """
    Autorisation par rôle : /admin/reload-index. La dépendance require_auth
    reste neutralisée par bypass_auth (autouse) mais sans role="admin" —
    exactement le cas "authentifié mais pas autorisé" qu'on veut vérifier.
    """

    def test_reload_index_without_token_is_401(self):
        app.dependency_overrides.pop(require_auth, None)
        response = client.post("/admin/reload-index")
        assert response.status_code == 401

    def test_reload_index_with_user_role_is_403(self):
        """Un utilisateur authentifié mais non-admin doit être rejeté (403, pas 401)."""
        response = client.post("/admin/reload-index")
        assert response.status_code == 403

    def test_reload_index_with_admin_role_succeeds(self, monkeypatch):
        app.dependency_overrides[require_auth] = lambda: {"sub": "demo-admin", "user_id": 2, "role": "admin"}
        monkeypatch.setattr(main_module, "reload_index", lambda: 1179)

        response = client.post("/admin/reload-index")

        assert response.status_code == 200
        assert response.json() == {"status": "reloaded", "vector_count": 1179}

    def test_reload_index_with_real_admin_token_succeeds(self, monkeypatch):
        """Bout en bout avec un vrai JWT porteur du claim role=admin (pas un override de dépendance)."""
        app.dependency_overrides.pop(require_auth, None)
        monkeypatch.setattr(main_module, "reload_index", lambda: 1179)
        token = main_module.auth.create_access_token(user_id=2, username="demo-admin", role="admin")

        response = client.post("/admin/reload-index", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200

    def test_reload_index_with_real_user_token_is_403(self):
        """Bout en bout avec un vrai JWT role=user (défaut) — pas d'accès admin."""
        app.dependency_overrides.pop(require_auth, None)
        token = main_module.auth.create_access_token(user_id=1, username="streamlit-ui")

        response = client.post("/admin/reload-index", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 403


class TestHardening:
    """Durcissement (Partie 5 sécurité) : rate limiting sur /token, CORS restreint."""

    def test_token_endpoint_rate_limited_beyond_quota(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 3)

        def _raise(username, password):
            raise main_module.auth.AuthError("Identifiants invalides")
        monkeypatch.setattr(main_module.auth, "authenticate_user", _raise)

        for _ in range(3):
            response = client.post("/token", data={"username": "attacker", "password": "wrong"})
            assert response.status_code == 401

        response = client.post("/token", data={"username": "attacker", "password": "wrong"})
        assert response.status_code == 429

    def test_login_endpoint_has_its_own_quota_independent_of_token(self, monkeypatch):
        """/token et /auth/login sont rate-limités indépendamment (routes distinctes)."""
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 1)

        def _raise(username, password):
            raise main_module.auth.AuthError("Identifiants invalides")
        monkeypatch.setattr(main_module.auth, "authenticate_user", _raise)

        assert client.post("/token", data={"username": "a", "password": "b"}).status_code == 401
        assert client.post("/token", data={"username": "a", "password": "b"}).status_code == 429
        # /auth/login n'a pas encore consommé son propre quota
        assert client.post("/auth/login", json={"username": "a", "password": "b"}).status_code == 401

    def test_cors_allows_configured_origin(self):
        response = client.get("/health", headers={"Origin": config.ALLOWED_ORIGIN})
        assert response.headers.get("access-control-allow-origin") == config.ALLOWED_ORIGIN

    def test_cors_rejects_unlisted_origin(self):
        response = client.get("/health", headers={"Origin": "https://attacker.example"})
        assert "access-control-allow-origin" not in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
