"""
Client HTTP partagé vers le micro-service interne db-api (Couche Données).

src/auth.py et src/tools/rag_tool.py ne parlent plus SQL directement : ils
passent par db_request(), seul point de sortie réseau vers db-api. Le
timeout court (10s) reflète le fait que db-api tourne sur le même réseau
Docker interne, pas sur un hop public.
"""
import httpx

from src import config


def db_request(method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, f"{config.DB_API_URL}{path}", timeout=10, **kwargs)
