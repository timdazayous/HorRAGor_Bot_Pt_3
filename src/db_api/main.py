"""
db_api — micro-service interne encapsulant tous les accès SQL à Supabase
(Couche Données du cahier des charges MLOps).

Seul point d'accès psycopg2 restant dans le projet, avec
`migrations/apply_migrations.py` (DDL de schéma — cas à part documenté, ne
peut pas dépendre d'une API qui n'existe pas encore avant la migration).
`src/auth.py` et `src/tools/rag_tool.py` ne parlent plus jamais SQL
directement : ils appellent ce service en HTTP via `src/db_client.py`.

Accessible uniquement depuis le réseau Docker interne `db_internal` (voir
docker-compose.yml) — pas de label Caddy, pas de port publié côté hôte.
La frontière de confiance ici est l'isolation réseau elle-même (pas de
secret partagé supplémentaire), cohérent avec le choix déjà fait pour
Vault en mode dev dans ce même projet : exercice pédagogique, pas un vrai
périmètre de sécurité zero-trust.
"""
from fastapi import FastAPI, HTTPException
from psycopg2.extras import RealDictCursor

from src.db_api.db import get_conn
from src.db_api.schemas import BulkByIdsRequest, CreateRefreshTokenRequest

app = FastAPI(
    title="HorRAGor db-api",
    description="Encapsulation SQL interne (Couche Données) — non exposée publiquement.",
)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Utilisateurs / refresh tokens
# ---------------------------------------------------------------------------

@app.get("/users/{username}")
def get_user_by_username(username: str):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return dict(row)


@app.post("/refresh-tokens", status_code=201)
def create_refresh_token(body: CreateRefreshTokenRequest):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (body.user_id, body.token_hash, body.expires_at),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "created"}


@app.get("/refresh-tokens/by-hash/{token_hash}")
def get_refresh_token_by_hash(token_hash: str):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked, u.username, u.role
                FROM refresh_tokens rt
                JOIN users u ON u.id = rt.user_id
                WHERE rt.token_hash = %s
                """,
                (token_hash,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Refresh token inconnu")
    return dict(row)


@app.patch("/refresh-tokens/{token_id}/revoke")
def revoke_refresh_token_by_id(token_id: int):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE refresh_tokens SET revoked = TRUE WHERE id = %s", (token_id,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "revoked"}


@app.patch("/refresh-tokens/by-hash/{token_hash}/revoke")
def revoke_refresh_token_by_hash(token_hash: str):
    """Idempotent — même sémantique que l'UPDATE ... WHERE d'origine (0 ligne touchée = pas d'erreur)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = %s", (token_hash,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "revoked"}


@app.patch("/users/{user_id}/revoke-all-tokens")
def revoke_all_tokens_for_user(user_id: int):
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
    return {"status": "revoked"}


# ---------------------------------------------------------------------------
# Films (catalogue horreur — film / genre / film_genre / evaluation / analyse_spark)
# ---------------------------------------------------------------------------

@app.get("/films/search")
def search_film(title: str):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    f.title,
                    f.original_title,
                    EXTRACT(YEAR FROM f.release_date)::int          AS year,
                    f.overview,
                    ARRAY_AGG(DISTINCT g.name)
                        FILTER (WHERE g.name IS NOT NULL)           AS genres,
                    MAX(CASE WHEN e.source_name = 'TMDB'
                        THEN e.score_value END)                     AS tmdb_score,
                    MAX(CASE WHEN e.source_name = 'IMDB'
                        THEN e.score_value END)                     AS imdb_score
                FROM film f
                LEFT JOIN film_genre fg ON f.id = fg.film_id
                LEFT JOIN genre g       ON fg.genre_id = g.id
                LEFT JOIN evaluation e  ON f.id = e.film_id
                WHERE f.title ILIKE %s OR f.original_title ILIKE %s
                GROUP BY f.id, f.title, f.original_title, f.release_date,
                         f.overview, f.popularity
                ORDER BY
                    CASE WHEN LOWER(f.title)          = LOWER(%s) THEN 0
                         WHEN LOWER(f.original_title) = LOWER(%s) THEN 1
                         ELSE 2
                    END,
                    f.popularity DESC NULLS LAST
                LIMIT 1
                """,
                (f"%{title}%", f"%{title}%", title, title),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Film introuvable")
    return dict(row)


@app.get("/films/survival")
def survival_film(title: str):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    f.title,
                    f.original_title,
                    EXTRACT(YEAR FROM f.release_date)::int          AS year,
                    f.overview,
                    ARRAY_AGG(DISTINCT g.name)
                        FILTER (WHERE g.name IS NOT NULL)           AS genres,
                    -- Sous-requête scalaire plutôt qu'un JOIN + GROUP BY : le
                    -- type JSON/JSONB n'a pas d'opérateur d'égalité, donc
                    -- horror_keywords ne peut pas figurer dans un GROUP BY.
                    (SELECT horror_keywords FROM analyse_spark WHERE film_id = f.id) AS horror_keywords,
                    (SELECT richness_score  FROM analyse_spark WHERE film_id = f.id) AS richness_score
                FROM film f
                LEFT JOIN film_genre fg   ON f.id = fg.film_id
                LEFT JOIN genre g         ON fg.genre_id = g.id
                WHERE f.title ILIKE %s OR f.original_title ILIKE %s
                GROUP BY f.id, f.title, f.original_title, f.release_date,
                         f.overview, f.popularity
                ORDER BY
                    CASE WHEN LOWER(f.title)          = LOWER(%s) THEN 0
                         WHEN LOWER(f.original_title) = LOWER(%s) THEN 1
                         ELSE 2
                    END,
                    f.popularity DESC NULLS LAST
                LIMIT 1
                """,
                (f"%{title}%", f"%{title}%", title, title),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Film introuvable")
    return dict(row)


@app.get("/films/age")
def film_age(title: str):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT title, original_title, release_date FROM film
                WHERE title ILIKE %s OR original_title ILIKE %s
                ORDER BY
                    CASE WHEN LOWER(title)          = LOWER(%s) THEN 0
                         WHEN LOWER(original_title) = LOWER(%s) THEN 1
                         ELSE 2
                    END,
                    popularity DESC NULLS LAST
                LIMIT 1
                """,
                (f"%{title}%", f"%{title}%", title, title),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Film introuvable")
    return dict(row)


@app.post("/films/bulk-by-ids")
def films_bulk_by_ids(body: BulkByIdsRequest):
    if not body.ids:
        return []
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    f.id, f.title, f.overview,
                    EXTRACT(YEAR FROM f.release_date)::int          AS year,
                    ARRAY_AGG(DISTINCT g.name)
                        FILTER (WHERE g.name IS NOT NULL)           AS genres,
                    MAX(CASE WHEN e.source_name = 'TMDB'
                        THEN e.score_value END)                     AS tmdb_score
                FROM film f
                LEFT JOIN film_genre fg ON f.id = fg.film_id
                LEFT JOIN genre g       ON fg.genre_id = g.id
                LEFT JOIN evaluation e  ON f.id = e.film_id
                WHERE f.id = ANY(%s)
                GROUP BY f.id, f.title, f.overview, f.release_date
                """,
                (body.ids,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/films/find-source")
def find_source_film(title: str):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, overview FROM film
                WHERE title ILIKE %s OR original_title ILIKE %s
                ORDER BY
                    CASE WHEN LOWER(title)          = LOWER(%s) THEN 0
                         WHEN LOWER(original_title) = LOWER(%s) THEN 1
                         ELSE 2
                    END,
                    popularity DESC NULLS LAST
                LIMIT 1
                """,
                (f"%{title}%", f"%{title}%", title, title),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Film introuvable")
    return dict(row)
