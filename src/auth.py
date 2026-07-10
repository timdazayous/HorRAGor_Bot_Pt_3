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
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import psycopg2
from loguru import logger
from psycopg2.extras import RealDictCursor

from src import config


class AuthError(Exception):
    """Erreur d'authentification (identifiants invalides, token expiré/révoqué...)."""


def get_conn() -> psycopg2.extensions.connection:
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL ou DATABASE_URL non configurée.")
    return psycopg2.connect(db_url)


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
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict:
    """Vérifie les identifiants. Lève AuthError si invalides."""
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthError("Identifiants invalides")
    return user


# ---------------------------------------------------------------------------
# Access tokens (JWT, stateless)
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "user_id": user_id,
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

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, _hash_token(raw_token), expires_at),
            )
        conn.commit()
    finally:
        conn.close()

    return raw_token


def validate_and_rotate_refresh_token(raw_token: str) -> dict:
    """
    Valide un refresh token puis le révoque immédiatement (rotation à usage
    unique). Lève AuthError si inconnu, déjà révoqué ou expiré.
    Retourne {"user_id":..., "username":...} en cas de succès.
    """
    token_hash = _hash_token(raw_token)

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked, u.username
                FROM refresh_tokens rt
                JOIN users u ON u.id = rt.user_id
                WHERE rt.token_hash = %s
                """,
                (token_hash,),
            )
            row = cur.fetchone()

            if not row:
                raise AuthError("Refresh token inconnu")
            if row["revoked"]:
                raise AuthError("Refresh token déjà révoqué")
            if row["expires_at"] < datetime.now(timezone.utc):
                raise AuthError("Refresh token expiré")

            cur.execute("UPDATE refresh_tokens SET revoked = TRUE WHERE id = %s", (row["id"],))
        conn.commit()
        return {"user_id": row["user_id"], "username": row["username"]}
    finally:
        conn.close()


def revoke_all_tokens_for_user(user_id: int) -> None:
    """Révoque tous les refresh tokens actifs d'un utilisateur (logout)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = %s AND revoked = FALSE",
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Point d'entrée haut niveau — émission d'une paire de tokens
# ---------------------------------------------------------------------------

def issue_token_pair(user_id: int, username: str) -> dict:
    access_token = create_access_token(user_id, username)
    refresh_token = create_refresh_token(user_id)
    logger.info(f"[Auth] Nouvelle paire de tokens émise pour {username!r}")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }
