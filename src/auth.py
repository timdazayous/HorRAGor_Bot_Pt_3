"""
Authentification par Refresh Tokens — verrouille les échanges entre l'IHM
(Streamlit) et l'API Intelligence.

Schéma :
  - access_token  : JWT signé (HS256), courte durée, jamais persisté côté
                    serveur — vérifié par simple décodage à chaque requête.
  - refresh_token : chaîne aléatoire opaque, dont seul le hash SHA-256 est
                    stocké en base (table refresh_tokens). Usage unique :
                    chaque rafraîchissement le révoque et en émet un nouveau
                    (rotation), pour limiter la fenêtre d'exploitation d'un
                    token volé.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from loguru import logger

from src import config
from src.db_client import db_request


class AuthError(Exception):
    """Erreur d'authentification (identifiants invalides, token expiré/révoqué...)."""


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------

def get_user_by_username(username: str) -> Optional[dict]:
    resp = db_request("GET", f"/users/{username}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def authenticate_user(username: str, password: str) -> dict:
    """Vérifie les identifiants. Lève AuthError si invalides."""
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthError("Identifiants invalides")
    return user


# ---------------------------------------------------------------------------
# Access tokens (JWT, stateless)
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, username: str, role: str = "user") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Décode et valide un access token. Lève AuthError si invalide/expiré/mauvais type."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("Access token expiré")
    except jwt.InvalidTokenError:
        raise AuthError("Access token invalide")

    if payload.get("type") != "access":
        raise AuthError("Ce token n'est pas un access token")
    return payload


# ---------------------------------------------------------------------------
# Refresh tokens (opaques, hash stocké en base, rotation à usage unique)
# ---------------------------------------------------------------------------

def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_refresh_token(user_id: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS)

    resp = db_request(
        "POST",
        "/refresh-tokens",
        json={
            "user_id": user_id,
            "token_hash": _hash_token(raw_token),
            "expires_at": expires_at.isoformat(),
        },
    )
    resp.raise_for_status()

    return raw_token


def validate_and_rotate_refresh_token(raw_token: str) -> dict:
    """
    Valide un refresh token puis le révoque immédiatement (rotation à usage
    unique). Lève AuthError si inconnu, déjà révoqué ou expiré.
    Retourne {"user_id":..., "username":...} en cas de succès.
    """
    token_hash = _hash_token(raw_token)

    resp = db_request("GET", f"/refresh-tokens/by-hash/{token_hash}")
    if resp.status_code == 404:
        raise AuthError("Refresh token inconnu")
    resp.raise_for_status()
    row = resp.json()

    if row["revoked"]:
        raise AuthError("Refresh token déjà révoqué")
    # Les dates traversent JSON en ISO 8601 (pas d'objet datetime natif côté HTTP).
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        raise AuthError("Refresh token expiré")

    db_request("PATCH", f"/refresh-tokens/{row['id']}/revoke").raise_for_status()
    return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}


def revoke_refresh_token(raw_token: str) -> None:
    """
    Révoque un refresh token précis (logout — endpoint POST /logout).
    Idempotent : silencieux si le token est déjà révoqué ou inconnu, pour ne
    donner à l'appelant aucune information exploitable sur l'état réel du
    token (cohérent avec l'anti-énumération du login).
    """
    token_hash = _hash_token(raw_token)
    db_request("PATCH", f"/refresh-tokens/by-hash/{token_hash}/revoke").raise_for_status()


def revoke_all_tokens_for_user(user_id: int) -> None:
    """Révoque toutes les sessions actives (tous les refresh tokens) d'un utilisateur."""
    db_request("PATCH", f"/users/{user_id}/revoke-all-tokens").raise_for_status()


# ---------------------------------------------------------------------------
# Point d'entrée haut niveau — émission d'une paire de tokens
# ---------------------------------------------------------------------------

def issue_token_pair(user_id: int, username: str, role: str = "user") -> dict:
    access_token = create_access_token(user_id, username, role)
    refresh_token = create_refresh_token(user_id)
    logger.info(f"[Auth] Nouvelle paire de tokens émise pour {username!r}")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }
