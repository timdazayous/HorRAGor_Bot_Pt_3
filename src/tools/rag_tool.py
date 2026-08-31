"""
rag_tool.py — Outil natif de l'Agent RAG (Le Chercheur Local)

Interroge le savoir structuré (Supabase) et vectoriel (FAISS) pour extraire
le lore brut des œuvres d'horreur, en corrigeant les approximations de
l'utilisateur (recherche floue ILIKE + similarité sémantique en repli).
"""
import os
from datetime import date
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
import psycopg2
from loguru import logger
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

_MOIS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]

_BASE_DIR         = Path(__file__).resolve().parent.parent.parent
_FAISS_INDEX_PATH = _BASE_DIR / "data" / "faiss_index" / "faiss.index"
_ID_MAP_PATH      = _BASE_DIR / "data" / "faiss_index" / "id_map.npy"

_model:  Optional[SentenceTransformer] = None
_index:  Optional[faiss.Index]         = None
_id_map: Optional[np.ndarray]          = None


def _get_retriever() -> tuple[SentenceTransformer, faiss.Index, np.ndarray]:
    global _model, _index, _id_map
    if _index is not None:
        return _model, _index, _id_map
    logger.info("Chargement SentenceTransformer + index FAISS...")
    _model  = SentenceTransformer("all-MiniLM-L6-v2")
    _index  = faiss.read_index(str(_FAISS_INDEX_PATH))
    _id_map = np.load(str(_ID_MAP_PATH))
    logger.info(f"Index FAISS chargé : {_index.ntotal} vecteurs")
    return _model, _index, _id_map


def initialize_retriever() -> None:
    """Pré-charge le modèle et l'index FAISS (à appeler au démarrage de l'API)."""
    _get_retriever()


def _get_conn() -> psycopg2.extensions.connection:
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL ou DATABASE_URL non configurée.")
    return psycopg2.connect(db_url)


# ---------------------------------------------------------------------------
# Niveau 1 — Correspondance exacte/floue (corrige les approximations du titre)
# ---------------------------------------------------------------------------

def _match_exact_movie(movie_name: str) -> Optional[dict]:
    """
    Cherche un film par ILIKE (tolère fautes de frappe partielles et variantes
    de titre). Retourne les métadonnées complètes si trouvé, sinon None.
    """
    try:
        conn = _get_conn()
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
                (f"%{movie_name}%", f"%{movie_name}%", movie_name, movie_name)
            )
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Erreur _match_exact_movie({movie_name!r}) : {e}")
        return None


def _get_survival_row(movie_name: str) -> Optional[dict]:
    """Comme _match_exact_movie, mais ajoute les mots-clés horreur (analyse_spark) pour le simulateur de survie."""
    try:
        conn = _get_conn()
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
                (f"%{movie_name}%", f"%{movie_name}%", movie_name, movie_name)
            )
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Erreur _get_survival_row({movie_name!r}) : {e}")
        return None


def get_survival_context(movie_name: str) -> dict:
    """
    Récupère le synopsis + les mots-clés horreur (analyse_spark) d'un film
    pour nourrir le Simulateur de Survie de l'Agent de Narration.
    Même forme de retour que rag_search : { context, is_complete, matched_title }.
    """
    row = _get_survival_row(movie_name)
    if not row:
        return {
            "context": f"Aucun film nommé « {movie_name} » trouvé dans la base locale.",
            "is_complete": False,
            "matched_title": None,
        }

    title = row["title"]
    if row.get("original_title") and row["original_title"] != row["title"]:
        title += f" ({row['original_title']})"
    genres = ", ".join(row["genres"]) if row.get("genres") else "Horreur"

    keywords = ""
    kw = row.get("horror_keywords")
    if isinstance(kw, list):
        keywords = ", ".join(kw[:15])
    elif isinstance(kw, str) and kw:
        keywords = kw

    context = (
        f"Film : {title} ({row.get('year') or '?'})\n"
        f"Genres : {genres}\n"
        f"Synopsis : {row.get('overview') or 'Non disponible'}\n"
    )
    if keywords:
        context += f"Éléments d'horreur clés : {keywords}\n"

    return {
        "context": context,
        "is_complete": bool(row.get("overview")),
        "matched_title": row["title"],
    }


def calculate_movie_age(movie_name: str) -> dict:
    """
    Calcule l'âge exact d'un film depuis sa date de sortie en base.
    Même forme de retour que rag_search : { context, is_complete, matched_title }.
    """
    try:
        conn = _get_conn()
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
                (f"%{movie_name}%", f"%{movie_name}%", movie_name, movie_name)
            )
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        logger.error(f"Erreur calculate_movie_age({movie_name!r}) : {e}")
        return {"context": f"Impossible de calculer l'âge de « {movie_name} ».", "is_complete": False, "matched_title": None}

    if not row:
        return {"context": f"Film « {movie_name} » introuvable dans la base locale.", "is_complete": False, "matched_title": None}
    if not row["release_date"]:
        return {
            "context": f"La date de sortie de « {row['title']} » n'est pas renseignée en base.",
            "is_complete": False, "matched_title": row["title"],
        }

    release = row["release_date"]
    today = date.today()
    age = today.year - release.year - ((today.month, today.day) < (release.month, release.day))

    title_display = row["title"]
    if row.get("original_title") and row["original_title"] != row["title"]:
        title_display += f" ({row['original_title']})"
    date_fr = f"{release.day} {_MOIS_FR[release.month]} {release.year}"

    context = (
        f"« {title_display} » est sorti le {date_fr}.\n"
        f"Il y a exactement {age} an{'s' if age > 1 else ''} (en {today.year})."
    )
    return {"context": context, "is_complete": True, "matched_title": row["title"]}


def _format_movie(row: dict) -> str:
    genres_str = ", ".join(row["genres"]) if row.get("genres") else "Non renseigné"
    scores = []
    if row.get("tmdb_score") is not None:
        scores.append(f"TMDB : {row['tmdb_score']:.1f}/10")
    if row.get("imdb_score") is not None:
        scores.append(f"IMDB : {row['imdb_score']:.1f}/10")
    scores_str = " | ".join(scores) if scores else "Non disponible"

    title_line = row["title"]
    if row.get("original_title") and row["original_title"] != row["title"]:
        title_line += f" ({row['original_title']})"

    return (
        f"Titre : {title_line}\n"
        f"Année : {row.get('year') or 'Inconnue'}\n"
        f"Genres : {genres_str}\n"
        f"Notes : {scores_str}\n"
        f"Synopsis : {row.get('overview') or 'Aucun synopsis disponible.'}"
    )


# ---------------------------------------------------------------------------
# Niveau 2 — Recherche sémantique (repli si pas de titre précis)
# ---------------------------------------------------------------------------

def _fetch_films_from_db(film_ids: list[int]) -> list[dict]:
    if not film_ids:
        return []
    try:
        conn = _get_conn()
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
                (film_ids,)
            )
            rows = cur.fetchall()
        conn.close()
        rows_by_id = {r["id"]: dict(r) for r in rows}
        return [rows_by_id[fid] for fid in film_ids if fid in rows_by_id]
    except Exception as e:
        logger.error(f"Erreur _fetch_films_from_db : {e}")
        return []


# Seuil de similarité cosinus (IndexFlatIP + vecteurs normalisés) en dessous
# duquel le film "le plus proche" est jugé non pertinent plutôt qu'une réponse.
_SEMANTIC_SCORE_THRESHOLD = 0.45


def _semantic_search(query: str, k: int = 5) -> list[tuple[float, dict]]:
    model, index, id_map = _get_retriever()
    vec = model.encode([query], normalize_embeddings=True).astype("float32")
    scores, indices = index.search(vec, k)
    film_ids = [int(id_map[i]) for i in indices[0] if i < len(id_map)]
    films = _fetch_films_from_db(film_ids)
    films_by_id = {f["id"]: f for f in films}
    return [
        (float(score), films_by_id[fid])
        for score, fid in zip(scores[0], film_ids)
        if fid in films_by_id
    ]


def _format_semantic_hit(f: dict) -> str:
    genres = ", ".join(f.get("genres") or []) or "N/A"
    score  = f"{f['tmdb_score']:.1f}/10" if f.get("tmdb_score") else "N/A"
    return (
        f"Titre : {f['title']} ({f.get('year') or '?'})\n"
        f"Genres : {genres}\n"
        f"Note TMDB : {score}\n"
        f"Synopsis : {f.get('overview') or ''}"
    )


def find_similar_movies(movie_name: str, k: int = 5) -> dict:
    """
    Trouve les k films les plus similaires à movie_name (similarité cosinus
    FAISS sur les synopsis). Même forme de retour que rag_search.
    """
    try:
        conn = _get_conn()
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
                (f"%{movie_name}%", f"%{movie_name}%", movie_name, movie_name)
            )
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        logger.error(f"Erreur find_similar_movies({movie_name!r}) : {e}")
        return {"context": f"Impossible de trouver des films similaires à « {movie_name} ».", "is_complete": False, "matched_title": None}

    if not row:
        return {"context": f"Film « {movie_name} » introuvable dans la base locale.", "is_complete": False, "matched_title": None}

    source_id, found_title = row["id"], row["title"]
    query_text = row["overview"] or found_title

    model, index, id_map = _get_retriever()
    vec = model.encode([query_text], normalize_embeddings=True).astype("float32")
    _, indices = index.search(vec, k + 1)  # +1 pour pouvoir exclure le film source

    film_ids = [int(id_map[i]) for i in indices[0] if i < len(id_map)]
    film_ids = [fid for fid in film_ids if fid != source_id][:k]

    films = _fetch_films_from_db(film_ids)
    if not films:
        return {"context": f"Aucun film similaire trouvé pour « {found_title} ».", "is_complete": False, "matched_title": found_title}

    lines = [f"Films similaires à « {found_title} » :\n"]
    for i, f in enumerate(films, 1):
        genres = ", ".join(f.get("genres") or []) or "N/A"
        score  = f"{f['tmdb_score']:.1f}/10" if f.get("tmdb_score") else "N/A"
        lines.append(f"{i}. {f['title']} ({f.get('year') or '?'}) — {genres} — TMDB {score}")

    return {"context": "\n".join(lines), "is_complete": True, "matched_title": found_title}


# ---------------------------------------------------------------------------
# Point d'entrée unique pour le rag_node
# ---------------------------------------------------------------------------

def rag_search(query: str, is_title: bool = True, k: int = 5) -> dict:
    """
    Cherche dans le savoir local (Supabase + FAISS) pour répondre à la requête.

    is_title=True  : `query` est un titre précis (corrigé des approximations
                      de l'utilisateur) — on cherche une correspondance exacte
                      ILIKE uniquement. Pas de repli sémantique : chercher le
                      plus proche voisin d'un titre absent de la base renverrait
                      un film sans rapport, ce qui casserait la confiance du
                      routeur (faux "is_complete=True").
    is_title=False : `query` est une demande thématique libre (ex: "un film
                      avec des fantômes") — recherche sémantique FAISS avec un
                      seuil de similarité minimal pour écarter les faux positifs.

    Retourne un dict : { "context": str, "is_complete": bool, "matched_title": str | None }
    is_complete=False signale au routeur que le lore local est insuffisant et
    qu'il faut déléguer à l'Agent Scraper.
    """
    if is_title:
        exact = _match_exact_movie(query)
        if not exact:
            return {
                "context": f"Aucun film nommé « {query} » trouvé dans la base locale.",
                "is_complete": False,
                "matched_title": None,
            }
        return {
            "context": _format_movie(exact),
            "is_complete": bool(exact.get("overview")),
            "matched_title": exact["title"],
        }

    hits = _semantic_search(query, k=k)
    if not hits or hits[0][0] < _SEMANTIC_SCORE_THRESHOLD:
        return {
            "context": "Aucun film suffisamment pertinent trouvé dans la base locale.",
            "is_complete": False,
            "matched_title": None,
        }

    parts = [_format_semantic_hit(f) for _, f in hits]
    return {
        "context": "\n\n".join(parts),
        "is_complete": True,
        "matched_title": hits[0][1]["title"],
    }
