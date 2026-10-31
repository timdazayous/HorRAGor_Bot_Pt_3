"""Modèles Pydantic des corps de requête acceptés par db-api."""
from pydantic import BaseModel


class CreateRefreshTokenRequest(BaseModel):
    user_id: int
    token_hash: str
    expires_at: str  # ISO 8601 — sérialisé côté appelant (src/auth.py)


class BulkByIdsRequest(BaseModel):
    ids: list[int]
