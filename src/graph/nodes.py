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
from src.tools.rag_tool import calculate_movie_age, find_similar_movies, get_survival_context, rag_search
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

_RAG_INTENTS = ("TITRE", "THEME", "SURVIE", "AGE", "SIMILAIRE", "ANECDOTES")

_RAG_EXTRACT_PROMPT = SystemMessage(content=(
    "Tu es un CLASSIFIEUR, pas un assistant conversationnel. Ne réponds "
    "JAMAIS à la question de l'utilisateur, ne donne aucune recommandation, "
    "aucun titre de film similaire, aucune explication : ta seule tâche est "
    "de produire l'étiquette de classification ci-dessous, rien d'autre.\n\n"
    "Voici l'historique de la conversation. Analyse la DERNIÈRE question de "
    "l'utilisateur — en t'appuyant TOUJOURS sur les tours précédents pour "
    "résoudre les questions de suivi, quel que soit leur type (ex: 'et son "
    "année de sortie ?' ou 'quel est mon taux de survie dans ce dernier ?' "
    "après avoir parlé de 'The Shining' → le sujet reste 'The Shining', jamais "
    "un thème générique comme 'survie') — et réponds sur EXACTEMENT deux "
    "lignes, sans rien d'autre, sans phrase d'introduction ni de conclusion :\n"
    "TITRE ou THEME ou SURVIE ou AGE ou SIMILAIRE ou ANECDOTES\n"
    "<le sujet nettoyé>\n\n"
    "Toutes ces catégories SAUF 'THEME' doivent donner le TITRE précis d'une "
    "œuvre (corrigé des approximations, ex: 'Shining' → 'The Shining'), jamais "
    "un thème générique.\n"
    "- 'SURVIE' : l'utilisateur demande ses chances de survie, s'il "
    "survivrait, ou veut jouer avec le scénario d'un film précis.\n"
    "- 'AGE' : l'utilisateur demande depuis combien de temps un film est "
    "sorti, son ancienneté, ou si c'est un film récent/ancien.\n"
    "- 'SIMILAIRE' : l'utilisateur demande des films similaires/qui "
    "ressemblent à un titre précis.\n"
    "- 'ANECDOTES' : l'utilisateur demande explicitement des anecdotes, des "
    "détails de tournage, ou veut en savoir plus sur une œuvre précise "
    "(ex: 'dis-m'en plus', 'anecdotes sur ce film', 'comment a été fait le film').\n"
    "- 'TITRE' : une œuvre précise est identifiable, sans qu'aucune des "
    "catégories ci-dessus ne s'applique.\n"
    "- 'THEME' : la demande est libre/thématique sans titre précis (ex: 'un "
    "film avec des fantômes', 'recommande-moi un film d'horreur') — donne "
    "alors ses mots-clés plutôt qu'un titre."
))


def _parse_extraction(raw: str) -> tuple[str, str]:
    """Découpe la réponse d'extraction en (intent, sujet). Repli robuste si le LLM dévie du format."""
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if len(lines) >= 2 and lines[0].upper() in _RAG_INTENTS:
        return lines[0].upper(), lines[1]
    # Repli : on ne peut pas classifier, on traite comme un titre (comportement le plus prudent)
    return "TITRE", (lines[0] if lines else raw.strip())

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

    # 1. Extraction du sujet de recherche réel + de l'intention (corrige les
    # approximations de titre). On donne tout l'historique de conversation,
    # pas seulement la dernière question, pour résoudre les questions de suivi
    # ("et son année de sortie ?" → le film cité juste avant).
    # Température 0 : c'est une tâche de classification stricte, pas de
    # génération créative — la moindre variance ici fait dévier le LLM du
    # format à deux lignes attendu par _parse_extraction.
    extraction_llm = ChatGroq(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL,
                               temperature=0, max_tokens=config.LLM_MAX_TOKENS)
    extraction = extraction_llm.invoke([_RAG_EXTRACT_PROMPT, *state["messages"]])
    record_llm_usage("rag_agent", extraction)
    intent, search_subject = _parse_extraction(extraction.content)

    # 2. Interrogation du savoir local — chaque intent a son propre outil,
    # sauf THEME (recherche sémantique) et TITRE (correspondance exacte).
    if intent == "SURVIE":
        raw = get_survival_context(search_subject)
    elif intent == "AGE":
        raw = calculate_movie_age(search_subject)
    elif intent == "SIMILAIRE":
        raw = find_similar_movies(search_subject)
    elif intent == "THEME":
        raw = rag_search(search_subject, is_title=False)
    else:  # TITRE ou ANECDOTES
        raw = rag_search(search_subject, is_title=True)

    # Demande explicite de détails/anecdotes : on force le passage par le
    # Scraper même si la base locale a déjà le nécessaire — imite le
    # comportement de la Partie 2, où l'utilisateur pouvait toujours demander
    # "plus de détails" indépendamment de la BDD. Champ dédié (force_scrape)
    # plutôt que de détourner is_complete, qui doit rester le reflet fidèle de
    # l'état réel des données locales.
    force_scrape = intent == "ANECDOTES"

    logger.info(
        f"[RAG] intent={intent} sujet={search_subject!r} "
        f"rag_complete={raw['is_complete']} force_scrape={force_scrape}"
    )

    # 3. Synthèse factuelle à partir des données brutes
    response = llm.invoke([
        _RAG_SYSTEM_PROMPT,
        HumanMessage(content=f"Question de l'utilisateur : {query}\n\nDonnées brutes :\n{raw['context']}"),
    ])
    record_llm_usage("rag_agent", response)

    return {
        "messages": [AIMessage(content=response.content, name="rag_agent")],
        "user_query": query,
        "is_survival_mode": intent == "SURVIE",
        "rag_context": response.content,
        "matched_title": raw["matched_title"],
        "rag_complete": raw["is_complete"],
        "force_scrape": force_scrape,
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

_SURVIVAL_NARRATION_PROMPT = SystemMessage(content=(
    "Tu es le Simulateur de Survie de HorRAGor, un maître du jeu d'horreur "
    "sadique et omniscient. Tu reçois une synthèse factuelle sur une œuvre "
    "d'horreur précise — jamais les logs techniques ni les noms d'outils. "
    "À partir de ce dossier, génère un rapport de survie fictif, dramatique "
    "et amusant pour l'utilisateur qui demande ses chances de survie. "
    "Respecte STRICTEMENT ce format markdown :\n\n"
    "🩸 **SIMULATEUR DE SURVIE — [TITRE EN MAJUSCULES] ([ANNÉE])**\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "📊 **Probabilité de survie : XX%**\n"
    "*(sois impitoyable, les films d'horreur ne font pas de cadeau)*\n\n"
    "💀 **Cause de mort la plus probable :**\n"
    "[Description dramatique et précise basée sur les éléments du film — 2-3 phrases]\n\n"
    "🔪 **Les 3 menaces principales :**\n"
    "1. [Menace tirée du film]\n"
    "2. [Menace tirée du film]\n"
    "3. [Menace tirée du film]\n\n"
    "🛡️ **Tes seules chances :**\n"
    "• [Conseil spécifique au film, concret]\n"
    "• [Conseil spécifique au film, concret]\n"
    "• [Conseil spécifique au film, concret]\n\n"
    "☠️ **Verdict final :**\n"
    "*[Une phrase finale cinglante sur ton destin inévitable]*\n\n"
    "Sois créatif, précis sur les éléments du film, et garde un ton entre "
    "humour noir et horreur authentique. Si le dossier ne contient aucune "
    "information exploitable sur un film précis, dis-le clairement au lieu "
    "d'inventer un film."
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
    is_survival = state.get("is_survival_mode", False)
    system_prompt = _SURVIVAL_NARRATION_PROMPT if is_survival else _NARRATION_SYSTEM_PROMPT
    logger.info(f"[Narration] retry={is_retry} retry_count={state.get('retry_count', 0)} survival={is_survival}")

    llm = ChatGroq(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL,
                    temperature=config.NARRATION_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS)
    response = llm.invoke([
        system_prompt,
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
