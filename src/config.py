"""
Configuration des LLM (Groq) et chemins partagés par le graphe multi-agent.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR       = Path(__file__).resolve().parent.parent
DATA_DIR       = BASE_DIR / "data"
FAISS_INDEX_DIR = DATA_DIR / "faiss_index"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL   = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")

# Chaque agent garde la même base de modèle mais peut varier la température :
# le Chercheur et l'Enquêteur restent factuels (froids), l'Écrivain a besoin
# de créativité pour la plume gothique.
RAG_TEMPERATURE       = float(os.environ.get("RAG_TEMPERATURE", 0.2))
SCRAPER_TEMPERATURE   = float(os.environ.get("SCRAPER_TEMPERATURE", 0.3))
NARRATION_TEMPERATURE = float(os.environ.get("NARRATION_TEMPERATURE", 0.9))
JUDGE_TEMPERATURE     = float(os.environ.get("JUDGE_TEMPERATURE", 0.1))

LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 2048))

# Le Juge : nombre max de régénérations de la Narration si la réponse est rejetée
JUDGE_MAX_RETRIES        = int(os.environ.get("JUDGE_MAX_RETRIES", 2))
JUDGE_CONFIDENCE_THRESHOLD = float(os.environ.get("JUDGE_CONFIDENCE_THRESHOLD", 0.65))

# Authentification — verrouille les échanges IHM <-> API (Refresh Tokens)
JWT_SECRET_KEY   = os.environ.get("JWT_SECRET_KEY", "changeme-dev-secret-do-not-use-in-prod")
JWT_ALGORITHM    = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7))
