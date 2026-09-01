"""
Test de bout en bout — scénario complet de la couche sécurité (projet final
"Sécuriser HorRAGor", projet-final-horragor.md).

Autonome : aucune connexion réelle à Supabase/Groq/FAISS n'est nécessaire.
- La persistance de src.auth (utilisateurs + refresh tokens) est remplacée
  par un magasin en mémoire fidèle au même contrat (mots de passe hachés via
  auth.hash_password/verify_password, rotation à usage unique, révocation) —
  "en mémoire suffit" pour cet exercice (brief, Partie 1).
- Le graphe multi-agent est bouchonné : /chat renvoie une réponse
  déterministe sans appeler Groq/FAISS/Supabase — seule la couche sécurité
  est notée (brief, "Périmètre de l'évaluation").

Ce fichier est aussi collecté par pytest (nom test_*.py) mais ne définit
aucune fonction test_* : toute la logique vit dans run_scenario(), qui ne
s'exécute que via `if __name__ == "__main__"` pour ne jamais patcher
globalement src.auth pendant une exécution normale de `pytest`.

Usage : uv run python test_e2e.py
"""
import secrets
import sys

from fastapi.testclient import TestClient

import src.main as main_module
from src import auth, config
from src import rate_limit as rate_limit_module
from src.main import app

client = TestClient(app)
_failures: list[str] = []


class InMemoryAuthStore:
    """Substitut de Supabase pour ce scénario — mêmes garanties, en mémoire."""

    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.refresh_tokens: dict[str, dict] = {}  # raw_token -> {user_id, revoked}
        self._next_user_id = 1

    def add_user(self, username: str, password: str, role: str = "user") -> None:
        self.users[username] = {
            "id": self._next_user_id,
            "username": username,
            "password_hash": auth.hash_password(password),
            "role": role,
        }
        self._next_user_id += 1

    def authenticate(self, username: str, password: str) -> dict:
        user = self.users.get(username)
        if not user or not auth.verify_password(password, user["password_hash"]):
            raise auth.AuthError("Identifiants invalides")
        return user

    def issue_tokens(self, user_id: int, username: str, role: str = "user") -> dict:
        access_token = auth.create_access_token(user_id, username, role)
        raw_refresh = secrets.token_urlsafe(48)
        self.refresh_tokens[raw_refresh] = {"user_id": user_id, "revoked": False}
        return {"access_token": access_token, "refresh_token": raw_refresh, "token_type": "bearer"}

    def rotate_refresh(self, raw_token: str) -> dict:
        entry = self.refresh_tokens.get(raw_token)
        if entry is None or entry["revoked"]:
            raise auth.AuthError("Refresh token inconnu ou déjà révoqué")
        entry["revoked"] = True
        user = next(u for u in self.users.values() if u["id"] == entry["user_id"])
        return {"user_id": user["id"], "username": user["username"], "role": user["role"]}

    def revoke(self, raw_token: str) -> None:
        entry = self.refresh_tokens.get(raw_token)
        if entry:
            entry["revoked"] = True


def _fake_graph_invoke(state, config=None):
    """Bouchon du graphe multi-agent — seule la couche sécurité est notée ici."""
    return {
        "final_answer": "Réponse bouchonnée pour le test e2e.",
        "tools_used": ["stub_agent"],
        "judge_verdict": None,
    }


def check(label: str, condition: bool) -> None:
    print(f"[{'OK' if condition else 'ECHEC'}] {label}")
    if not condition:
        _failures.append(label)


def run_scenario() -> None:
    print("=== Test end-to-end — couche sécurité HorRAGor ===\n")

    store = InMemoryAuthStore()
    store.add_user("demo-user", "user-password-123", role="user")
    store.add_user("demo-admin", "admin-password-123", role="admin")

    auth.authenticate_user = store.authenticate
    auth.issue_token_pair = store.issue_tokens
    auth.validate_and_rotate_refresh_token = store.rotate_refresh
    auth.revoke_refresh_token = store.revoke

    main_module.agent_graph.invoke = _fake_graph_invoke
    main_module.reload_index = lambda: 1179

    # 1. Login user -> access + refresh
    response = client.post("/token", data={"username": "demo-user", "password": "user-password-123"})
    check("1. Login user (/token) -> 200 avec access+refresh", response.status_code == 200)
    tokens = response.json()
    user_access = tokens.get("access_token", "")
    user_refresh = tokens.get("refresh_token", "")
    check("   access_token et refresh_token présents", bool(user_access) and bool(user_refresh))

    # 2. POST /chat avec l'access -> 200 (réponse du graphe, même bouchonné)
    response = client.post("/chat", json={"question": "test"}, headers={"Authorization": f"Bearer {user_access}"})
    check("2. /chat avec access token -> 200", response.status_code == 200)

    # 3. POST /chat sans token -> 401
    response = client.post("/chat", json={"question": "test"})
    check("3. /chat sans token -> 401", response.status_code == 401)

    # 4. POST /chat en présentant le refresh token -> 401
    response = client.post("/chat", json={"question": "test"}, headers={"Authorization": f"Bearer {user_refresh}"})
    check("4. /chat avec le refresh token -> 401", response.status_code == 401)

    # 5. Route admin avec le token user -> 403 ; après login admin -> 200
    response = client.post("/admin/reload-index", headers={"Authorization": f"Bearer {user_access}"})
    check("5a. Route admin avec token user -> 403", response.status_code == 403)

    response = client.post("/token", data={"username": "demo-admin", "password": "admin-password-123"})
    check("5b. Login admin (/token) -> 200", response.status_code == 200)
    admin_access = response.json().get("access_token", "")

    response = client.post("/admin/reload-index", headers={"Authorization": f"Bearer {admin_access}"})
    check("5c. Route admin avec token admin -> 200", response.status_code == 200)

    # 6. POST /auth/refresh -> nouveaux jetons ; rejouer l'ancien refresh -> 401 (rotation)
    response = client.post("/auth/refresh", json={"refresh_token": user_refresh})
    check("6a. /auth/refresh avec refresh valide -> 200", response.status_code == 200)
    new_tokens = response.json()

    response = client.post("/auth/refresh", json={"refresh_token": user_refresh})
    check("6b. Rejouer l'ancien refresh -> 401 (rotation)", response.status_code == 401)

    # 7. POST /logout -> le refresh courant ne fonctionne plus
    new_refresh = new_tokens.get("refresh_token", "")
    response = client.post("/logout", json={"refresh_token": new_refresh})
    check("7a. /logout -> 200", response.status_code == 200)

    response = client.post("/auth/refresh", json={"refresh_token": new_refresh})
    check("7b. Refresh révoqué par /logout -> 401", response.status_code == 401)

    # 8. Marteler /token avec de mauvais identifiants -> 429 au-delà du quota
    rate_limit_module.reset()
    last_status = None
    for _ in range(config.RATE_LIMIT_LOGIN_MAX_ATTEMPTS + 1):
        last_status = client.post("/token", data={"username": "demo-user", "password": "wrong"}).status_code
    check(f"8. Quota /token dépassé -> 429 (dernier statut={last_status})", last_status == 429)

    print()
    if _failures:
        print(f"{len(_failures)} étape(s) en échec : {_failures}")
        sys.exit(1)
    print("Scénario complet passé.")


if __name__ == "__main__":
    run_scenario()
