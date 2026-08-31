"""
Le State de confiance — mémoire commune partagée par les 3 agents du graphe.
"""
import operator
from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # Fil de conversation complet (reducer add_messages : fusionne, ne remplace pas)
    messages: Annotated[list[BaseMessage], add_messages]

    # Question brute de l'utilisateur, stable tout au long du graphe
    user_query: str

    # Synthèse produite par l'Agent RAG (lore local FAISS + Supabase)
    rag_context: Optional[str]

    # Titre du film identifié par l'Agent RAG — transmis au Scraper pour cibler sa recherche
    matched_title: Optional[str]

    # Verdict du routeur : la récolte locale suffit-elle à nourrir la narration ?
    rag_complete: bool

    # Demande explicite d'enrichissement (intention ANECDOTES) : force le
    # passage par le Scraper même si rag_complete=True. Distinct de
    # rag_complete pour que ce dernier garde son sens littéral (la donnée
    # locale est-elle réellement incomplète ?), conformément au principe de
    # routage du brief ("selon la présence ou l'absence d'informations").
    force_scrape: bool

    # L'utilisateur demande-t-il une simulation de survie ("mes chances de survie
    # dans X ?") — bascule le prompt de l'Agent de Narration vers le format
    # structuré du Simulateur de Survie plutôt que la narration gothique classique.
    is_survival_mode: bool

    # Synthèse produite par l'Agent Scraper (anecdotes web), absente si non déclenché
    scraper_context: Optional[str]

    # Réponse finale romancée par l'Agent de Narration
    final_answer: Optional[str]

    # Verdict du Juge sur la dernière réponse ({is_valid, confidence, reasoning})
    judge_verdict: Optional[dict]

    # Nombre de régénérations déjà effectuées suite à un rejet du Juge
    retry_count: int

    # Traçabilité : agents/outils traversés (accumulé via operator.add pour Langfuse/monitoring)
    tools_used: Annotated[list[str], operator.add]
