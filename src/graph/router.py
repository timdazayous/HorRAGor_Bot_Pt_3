"""
router.py — Les Aiguilleurs (La Logique Décisionnelle)

Une fonction de routage examine le State et renvoie uniquement une chaîne
de caractères : la destination suivante. Aucune logique métier ici.
"""
from src import config
from src.models.state import AgentState


def should_scrape_or_narrate(state: AgentState) -> str:
    """
    Aiguille le flux après l'Agent RAG :
      - "narration" si le lore local est suffisant (rag_complete=True) et
        qu'aucun enrichissement n'a été explicitement demandé
      - "scraper"   si le dossier local est incomplet (rag_complete=False),
        ou si l'utilisateur a explicitement demandé des anecdotes
        (force_scrape=True)
    """
    if state.get("rag_complete") and not state.get("force_scrape"):
        return "narration"
    return "scraper"


def should_retry_or_end(state: AgentState) -> str:
    """
    Aiguille le flux après Le Juge :
      - "retry" si la réponse est rejetée (confiance insuffisante) ET qu'il
        reste des tentatives — retour vers l'Agent de Narration
      - "end"   si la réponse est jugée satisfaisante, ou si le budget de
        retries est épuisé (on rend la dernière version plutôt que de boucler
        indéfiniment)
    """
    verdict = state.get("judge_verdict") or {}
    is_satisfactory = verdict.get("is_valid", True) or verdict.get("confidence", 1.0) >= config.JUDGE_CONFIDENCE_THRESHOLD

    if is_satisfactory:
        return "end"
    if state.get("retry_count", 0) >= config.JUDGE_MAX_RETRIES:
        return "end"
    return "retry"
