"""
Tests de l'API FastAPI HorRAGor BOT

Le graphe multi-agent (src.main.agent_graph) est mocké pour tous ces tests :
aucun appel Groq, Supabase ou Wikipedia réel n'est déclenché — la logique du
graphe elle-même est testée séparément dans tests/test_graph_pipeline.py.
"""

import pytest
from fastapi.testclient import TestClient

import src.main as main_module
from src.main import ChatRequest, ChatResponse, JudgeVerdict, app, require_auth

client = TestClient(app)


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

    def test_login_success_returns_token_pair(self, monkeypatch):
        monkeypatch.setattr(
            main_module.auth, "authenticate_user",
            lambda username, password: {"id": 1, "username": username},
        )
        monkeypatch.setattr(
            main_module.auth, "issue_token_pair",
            lambda user_id, username: {"access_token": "a", "refresh_token": "b", "token_type": "bearer"},
        )

        response = client.post("/auth/login", json={"username": "streamlit-ui", "password": "correct"})

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "a"
        assert data["refresh_token"] == "b"

    def test_login_failure_returns_401(self, monkeypatch):
        def _raise(username, password):
            raise main_module.auth.AuthError("Identifiants invalides")
        monkeypatch.setattr(main_module.auth, "authenticate_user", _raise)

        response = client.post("/auth/login", json={"username": "streamlit-ui", "password": "wrong"})

        assert response.status_code == 401

    def test_refresh_success_returns_new_token_pair(self, monkeypatch):
        monkeypatch.setattr(
            main_module.auth, "validate_and_rotate_refresh_token",
            lambda raw_token: {"user_id": 1, "username": "streamlit-ui"},
        )
        monkeypatch.setattr(
            main_module.auth, "issue_token_pair",
            lambda user_id, username: {"access_token": "new-a", "refresh_token": "new-b", "token_type": "bearer"},
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

    def test_chat_with_valid_token_succeeds(self):
        app.dependency_overrides.pop(require_auth, None)
        token = main_module.auth.create_access_token(user_id=1, username="streamlit-ui")
        response = client.post(
            "/chat", json={"question": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
