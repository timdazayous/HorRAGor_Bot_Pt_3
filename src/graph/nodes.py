"""
nodes.py — Les Ouvriers (La Logique Métier)

Chaque fonction prend l'état actuel (AgentState) en paramètre unique et
retourne un dictionnaire des champs à fusionner dans le State. Les nœuds
ne savent jamais qui a travaillé avant eux ni qui prendra la suite.
"""
import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from loguru import logger

from src import config
from src.metrics import record_llm_usage, track_node
from src.models.state import AgentState
from src.tools.rag_tool import rag_search
from src.tools.scraper_tool import scrape_web_lore


def _last_user_query(state: AgentState) -> str:
    """Récupère la dernière question utilisateur (messages ou user_query direct)."""
    if state.get("user_query"):
        return state["user_query"]
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


# ---------------------------------------------------------------------------
# Agent RAG — Le Chercheur Local
# ---------------------------------------------------------------------------

_RAG_EXTRACT_PROMPT = SystemMessage(content=(
    "Voici l'historique de la conversation. Analyse la DERNIÈRE question de "
    "l'utilisateur — en t'appuyant sur les tours précédents si c'est une question "
    "de suivi (ex: 'et son année de sortie ?' après avoir parlé de 'The Shining' "
    "→ le sujet reste 'The Shining') — et réponds sur EXACTEMENT deux lignes, "
    "sans rien d'autre :\n"
    "TITRE ou THEME\n"
    "<le sujet nettoyé>\n\n"
    "Réponds 'TITRE' si une œuvre précise est identifiable — corrige alors "
    "l'orthographe/les approximations (ex: 'Shining' → 'The Shining'). "
    "Réponds 'THEME' si la demande est libre/thématique sans titre précis "
    "(ex: 'un film avec des fantômes', 'recommande-moi un film d'horreur'), "
    "et donne ses mots-clés."
))


def _parse_extraction(raw: str) -> tuple[str, bool]:
    """Découpe la réponse d'extraction en (sujet, is_title). Repli robuste si le LLM dévie du format."""
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if len(lines) >= 2 and lines[0].upper() in ("TITRE", "THEME"):
        return lines[1], lines[0].upper() == "TITRE"
    # Repli : on ne peut pas classifier, on traite comme un titre (comportement le plus prudent)
    return lines[0] if lines else raw.strip(), True

_RAG_SYSTEM_PROMPT = SystemMessage(content=(
    "Tu es le Chercheur Local de HorRAGor, spécialiste du lore d'horreur "
    "(cinéma, littérature, jeux vidéo). On te fournit des données brutes "
    "extraites d'une base de films d'horreur (métadonnées SQL ou recherche "
    "sémantique). Ta mission : synthétiser ces données en un dossier factuel "
    "clair, en corrigeant au passage les éventuelles approximations de titre "
    "de l'utilisateur (ex: 'Shining' → 'The Shining'). Reste factuel et concis, "
    "aucune fioriture littéraire — ce n'est pas ton rôle. Si les données brutes "
    "sont vides ou trop maigres, dis-le explicitement."
))


@track_node("rag_agent")
def rag_node(state: AgentState) -> dict:
    query = _last_user_query(state)

    llm = ChatGroq(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL,
                    temperature=config.RAG_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS)

    # 1. Extraction du sujet de recherche réel (corrige les approximations de titre).
    # On donne tout l'historique de conversation, pas seulement la dernière question,
    # pour résoudre les questions de suivi ("et son année de sortie ?" → le film cité juste avant).
    extraction = llm.invoke([_RAG_EXTRACT_PROMPT, *state["messages"]])
    record_llm_usage("rag_agent", extraction)
    search_subject, is_title = _parse_extraction(extraction.content)

    # 2. Interrogation du savoir local avec le sujet nettoyé
    raw = rag_search(search_subject, is_title=is_title)
    logger.info(f"[RAG] sujet={search_subject!r} is_title={is_title} rag_complete={raw['is_complete']}")

    # 3. Synthèse factuelle à partir des données brutes
    response = llm.invoke([
        _RAG_SYSTEM_PROMPT,
        HumanMessage(content=f"Question de l'utilisateur : {query}\n\nDonnées brutes :\n{raw['context']}"),
    ])
    record_llm_usage("rag_agent", response)

    return {
        "messages": [AIMessage(content=response.content, name="rag_agent")],
        "user_query": query,
        "rag_context": response.content,
        "matched_title": raw["matched_title"],
        "rag_complete": raw["is_complete"],
        "tools_used": ["rag_agent"],
    }


# ---------------------------------------------------------------------------
# Agent Scraper — L'Enquêteur du Web
# ---------------------------------------------------------------------------

_SCRAPER_SYSTEM_PROMPT = SystemMessage(content=(
    "Tu es l'Enquêteur du Web de HorRAGor. Le Chercheur Local n'a pas trouvé "
    "assez d'informations en base : ta mission est de creuser les anecdotes, "
    "le contexte de production et les détails manquants sur une œuvre "
    "d'horreur précise, à partir d'un extrait Wikipedia brut. Synthétise "
    "uniquement les faits pertinents pour un fan d'horreur — reste factuel, "
    "la mise en ambiance viendra plus tard d'un autre agent."
))


@track_node("scraper_agent")
def scraper_node(state: AgentState) -> dict:
    target = state.get("matched_title") or _last_user_query(state)
    raw = scrape_web_lore(target)
    logger.info(f"[Scraper] cible={target!r} trouvé={raw['found']}")

    llm = ChatGroq(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL,
                    temperature=config.SCRAPER_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS)
    response = llm.invoke([
        _SCRAPER_SYSTEM_PROMPT,
        HumanMessage(content=f"Œuvre concernée : {target}\n\nExtrait brut :\n{raw['context']}"),
    ])
    record_llm_usage("scraper_agent", response)

    return {
        "messages": [AIMessage(content=response.content, name="scraper_agent")],
        "scraper_context": response.content,
        "tools_used": ["scraper_agent"],
    }


# ---------------------------------------------------------------------------
# Agent de Narration — L'Écrivain Gothique
# ---------------------------------------------------------------------------

_NARRATION_SYSTEM_PROMPT = SystemMessage(content=(
    "Tu es l'Écrivain Gothique de HorRAGor. Tu reçois uniquement une synthèse "
    "factuelle sur une œuvre d'horreur — jamais les logs techniques, jamais "
    "les noms d'outils ou de bases de données. Ta mission : emballer ces "
    "informations dans une atmosphère textuelle terrifiante, immersive et "
    "hautement romancée, comme un conteur gothique s'adressant à un fan "
    "d'horreur. Ne mentionne jamais que ces données viennent d'une base de "
    "données, d'une recherche web ou d'un outil quelconque."
))


@track_node("narration_agent")
def narration_node(state: AgentState) -> dict:
    """
    Isolé de toute la plomberie technique : ce nœud ne lit QUE rag_context et
    scraper_context, jamais l'historique complet des messages (context trimming).

    Si le Juge a rejeté un précédent essai (retry_count > 0), sa critique est
    injectée pour orienter la régénération — c'est la SEULE information du
    Juge qui traverse jusqu'ici, jamais de log technique.
    """
    query   = state.get("user_query", "")
    dossier = state.get("rag_context") or ""
    if state.get("scraper_context"):
        dossier += f"\n\n{state['scraper_context']}"

    human_content = f"Question originale de l'utilisateur : {query}\n\nDossier :\n{dossier}"

    verdict = state.get("judge_verdict")
    is_retry = state.get("retry_count", 0) > 0 and verdict and not verdict.get("is_valid", True)
    if is_retry:
        human_content += (
            f"\n\n[Critique du Juge à corriger] {verdict.get('reasoning', '')} "
            "Corrige ta réponse précédente en restant fidèle au dossier ci-dessus, "
            "sans perdre l'atmosphère gothique."
        )
    logger.info(f"[Narration] retry={is_retry} retry_count={state.get('retry_count', 0)}")

    llm = ChatGroq(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL,
                    temperature=config.NARRATION_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS)
    response = llm.invoke([
        _NARRATION_SYSTEM_PROMPT,
        HumanMessage(content=human_content),
    ])
    record_llm_usage("narration_agent", response)

    return {
        "messages": [AIMessage(content=response.content, name="narration_agent")],
        "final_answer": response.content,
        "tools_used": ["narration_agent"],
    }


# ---------------------------------------------------------------------------
# Le Juge — Évaluateur qualité
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = SystemMessage(content=(
    "Tu es Le Juge, un évaluateur strict de HorRAGor BOT. "
    "Ta mission : détecter les hallucinations et vérifier la cohérence de la "
    "réponse finale par rapport au dossier factuel qui l'a nourrie. "
    "Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après. "
    'Format obligatoire : {"is_valid": true, "confidence": 0.95, "reasoning": "..."} '
    "is_valid = false si : hallucinations détectées, réponse hors sujet, "
    "contradiction avec le dossier, réponse vide ou incompréhensible. "
    "confidence entre 0.0 et 1.0."
))


def _parse_judge_verdict(raw: str) -> dict:
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"is_valid": True, "confidence": 0.75, "reasoning": "Évaluation automatique non disponible."}


@track_node("judge_agent")
def judge_node(state: AgentState) -> dict:
    """
    Évalue final_answer par rapport au dossier factuel (rag_context + scraper_context).
    Incrémente retry_count : le routeur décide ensuite s'il faut renvoyer vers
    la Narration (retry_count < JUDGE_MAX_RETRIES) ou terminer.
    """
    query   = state.get("user_query", "")
    answer  = state.get("final_answer", "")
    dossier = state.get("rag_context") or ""
    if state.get("scraper_context"):
        dossier += f"\n\n{state['scraper_context']}"

    llm = ChatGroq(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL,
                    temperature=config.JUDGE_TEMPERATURE, max_tokens=256)
    response = llm.invoke([
        _JUDGE_SYSTEM_PROMPT,
        HumanMessage(content=(
            f"Question posée : {query}\n\n"
            f"Dossier factuel :\n{dossier}\n\n"
            f"Réponse de l'Agent de Narration :\n{answer}\n\n"
            "La réponse est-elle fidèle au dossier, complète et sans hallucination ?\n"
            'Réponds en JSON : {"is_valid": true/false, "confidence": 0.0-1.0, "reasoning": "..."}'
        )),
    ])
    record_llm_usage("judge_agent", response)
    verdict = _parse_judge_verdict(response.content)

    logger.info(
        f"[Juge] valid={verdict.get('is_valid')} conf={verdict.get('confidence'):.2f} "
        f"— {verdict.get('reasoning', '')[:80]}"
    )

    return {
        "judge_verdict": verdict,
        "retry_count": state.get("retry_count", 0) + 1,
        "tools_used": ["judge_agent"],
    }
