"""
Rate limiting en mémoire — anti brute-force sur les endpoints de login.

Fenêtre glissante par (IP, route), sans backend externe : suffisant pour une
API qui tourne en un seul worker Uvicorn. À remplacer par un backend partagé
(Redis) si l'API est un jour répartie sur plusieurs instances/workers, chacun
aurait sinon son propre compteur et le quota réel serait multiplié par le
nombre de workers.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from loguru import logger

from src import config

_attempts: dict[str, deque] = defaultdict(deque)


def _bucket_key(request: Request) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"{client_ip}:{request.url.path}"


async def enforce_login_rate_limit(request: Request) -> None:
    """
    Dépendance FastAPI : limite le nombre de tentatives sur une route de
    login, par IP, sur une fenêtre glissante. Lève 429 au-delà du quota.
    """
    key = _bucket_key(request)
    now = time.monotonic()
    window_start = now - config.RATE_LIMIT_LOGIN_WINDOW_SECONDS

    bucket = _attempts[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= config.RATE_LIMIT_LOGIN_MAX_ATTEMPTS:
        logger.warning(f"[RateLimit] Quota dépassé pour {key!r}")
        raise HTTPException(status_code=429, detail="Trop de tentatives, réessaie plus tard.")

    bucket.append(now)


def reset() -> None:
    """Vide l'état du limiteur — usage tests uniquement."""
    _attempts.clear()
