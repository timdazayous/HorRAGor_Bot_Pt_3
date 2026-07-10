"""
scraper_tool.py — Outil natif de l'Agent Scraper (L'Enquêteur du Web)

Déclenché uniquement quand le lore local (rag_tool) est incomplet.
Va creuser Wikipedia en direct pour extraire les anecdotes et détails
manquants sur une œuvre spécifique (API REST, pas de scraping HTML brut).
"""
import re

import requests
from loguru import logger

_HEADERS = {
    "User-Agent": "HorRAGorBot/3.0 (educational project; contact: horragor@example.com)"
}
_WIKI_API_URL = "https://fr.wikipedia.org/w/api.php"
_MAX_CHARS = 2000


def _search_wikipedia_page(query: str) -> str | None:
    """Cherche une page Wikipedia et retourne son titre exact."""
    params = {
        "action":   "query",
        "list":     "search",
        "srsearch": f"{query} film horreur",
        "srlimit":  3,
        "format":   "json",
        "origin":   "*",
    }
    try:
        resp = requests.get(_WIKI_API_URL, params=params, headers=_HEADERS, timeout=8)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        if results:
            return results[0]["title"]
    except Exception as e:
        logger.error(f"Erreur recherche Wikipedia : {e}")
    return None


def _get_page_extract(page_title: str) -> str:
    """Récupère le texte de la section principale de la page Wikipedia."""
    params = {
        "action":      "query",
        "prop":        "extracts",
        "exintro":     False,
        "explaintext": True,
        "titles":      page_title,
        "format":      "json",
        "origin":      "*",
    }
    try:
        resp = requests.get(_WIKI_API_URL, params=params, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        page  = next(iter(pages.values()))
        return page.get("extract", "")
    except Exception as e:
        logger.error(f"Erreur extraction Wikipedia : {e}")
    return ""


def _clean_and_truncate(text: str, max_chars: int = _MAX_CHARS) -> str:
    """Nettoie le texte Wikipedia et le tronque proprement."""
    for section in ["== Références ==", "== Liens externes ==",
                    "== Notes ==", "== Voir aussi =="]:
        idx = text.find(section)
        if idx != -1:
            text = text[:idx]

    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_dot  = truncated.rfind(".")
    if last_dot > max_chars * 0.7:
        truncated = truncated[:last_dot + 1]

    return truncated + "\n\n[...] (résumé tronqué)"


def scrape_web_lore(movie_name: str) -> dict:
    """
    Récupère un complément d'information depuis Wikipedia pour enrichir
    le dossier d'une œuvre d'horreur incomplète en base locale.

    Retourne un dict : { "context": str, "found": bool }
    """
    page_title = _search_wikipedia_page(movie_name)
    if not page_title:
        return {
            "context": f"Aucune page Wikipedia trouvée pour « {movie_name} ».",
            "found": False,
        }

    logger.info(f"Page Wikipedia trouvée : {page_title!r}")

    extract = _get_page_extract(page_title)
    if not extract:
        return {
            "context": f"La page Wikipedia « {page_title} » existe mais son contenu est vide.",
            "found": False,
        }

    clean = _clean_and_truncate(extract)
    return {
        "context": f"Source Wikipedia — « {page_title} » :\n\n{clean}",
        "found": True,
    }
