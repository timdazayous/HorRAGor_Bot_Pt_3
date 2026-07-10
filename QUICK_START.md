🚀 HorRAGor BOT — Quick Start (Partie 3 — Multi-Agent LangGraph)
⚡ Démarrage rapide

Step 1: Obtenir une clé API Groq
Allez sur : https://console.groq.com/
Connectez-vous / créez un compte
Accédez à API Keys
Cliquez sur Create New API Key
Copiez la clé (commence généralement par gsk_...)

Step 2: Configurer .env

Copiez .env.example vers .env et renseignez au minimum :

GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SUPABASE_DB_URL=postgresql://postgres:MOT_DE_PASSE@db.XXXX.supabase.co:5432/postgres

LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST sont optionnelles
(monitoring désactivé si absentes — voir README, section Langfuse).

Step 3: Installer les dépendances (uv)
uv sync

Step 4: Vérifier que l'index FAISS existe
data/faiss_index/faiss.index et data/faiss_index/id_map.npy doivent être présents.
S'ils manquent :
uv run python utils/build_faiss_index.py

Step 5: Lancer l'API

🖥️ Terminal 1 — FastAPI
uvicorn src.main:app --reload

👉 Documentation Swagger :
http://localhost:8000/docs

🎨 Terminal 2 — Streamlit
streamlit run app_frontend.py

👉 Interface :
http://localhost:8501

🧪 Tester l'API avec curl
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Recommande-moi un film d'\''horreur comme The Shining"
  }'

Réponse attendue :
{
  "answer": "[Réponse romancée générée par l'Agent de Narration, validée par Le Juge...]",
  "tools_used": ["rag_agent", "narration_agent", "judge_agent"],
  "judge_verdict": {
    "is_valid": true,
    "confidence": 0.95,
    "reasoning": "Réponse fidèle au dossier factuel, sans hallucination."
  },
  "conversation_id": "conv_default"
}

(tools_used contiendra aussi "scraper_agent" si le RAG local était incomplet,
et plusieurs "narration_agent"/"judge_agent" en cas de retry.)

📝 Architecture

┌─────────────────┐
│   Streamlit     │
│  app_frontend.py│
└────────┬────────┘
         │ HTTP POST /chat
         ↓
┌─────────────────┐
│   FastAPI       │
│   src/main.py   │
└────────┬────────┘
         │ agent_graph.invoke()
         ↓
┌────────────────────────────────────────────────────────────────┐
│  Graphe multi-agent LangGraph (src/graph/)                     │
│                                                                  │
│  rag_node ──(complet)────────→ narration_node ⇄ judge_node ──→ END
│     │                               ↑              │(rejeté,   │
│     └─(incomplet)→ scraper_node ────┘              │ retries   │
│                                                     │ restants) │
│                                     └───────────────┘           │
└──────────────────────────────────────────────────────────────┘
         │                    │
         ↓                    ↓
   FAISS + Supabase      Wikipedia (live)

🔑 Fichiers clés
Fichier                        Rôle
src/main.py                    API FastAPI, endpoint /chat, branche le graphe
src/graph/pipeline.py          Assemble et compile le StateGraph
src/graph/nodes.py             rag_node / scraper_node / narration_node / judge_node
src/graph/router.py            Routage conditionnel (RAG suffisant ?)
src/models/state.py            AgentState partagé entre les 3 agents
src/tools/rag_tool.py          Recherche FAISS + Supabase
src/tools/scraper_tool.py      Recherche Wikipedia en direct
app_frontend.py                Interface Streamlit
.env                           Configuration (GROQ_API_KEY, Supabase, Langfuse)

📚 Endpoints disponibles
1. /health (GET)
curl http://localhost:8000/health
2. /chat (POST)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "Ta question ici"}'
3. /info (GET)
curl http://localhost:8000/info
4. /docs (Swagger UI)

👉 http://localhost:8000/docs

⚙️ Configuration avancée

Éditer .env :

# Modèle Groq (partagé par les 3 agents)
LLM_MODEL=llama-3.3-70b-versatile

# Températures par agent (factuel → créatif)
RAG_TEMPERATURE=0.2
SCRAPER_TEMPERATURE=0.3
NARRATION_TEMPERATURE=0.9

LLM_MAX_TOKENS=2048

🐛 Dépannage
❌ "GROQ_API_KEY non configurée"
→ Vérifie ton fichier .env

❌ "Connection refused" sur /chat
→ Lance l'API :
uvicorn src.main:app --reload

❌ "ModuleNotFoundError"
uv sync

❌ Index FAISS manquant
uv run python utils/build_faiss_index.py

❌ Streamlit n'arrive pas à joindre l'API
Vérifie dans app_frontend.py :
API_URL = "http://localhost:8000/chat"

📖 Documentation
https://console.groq.com/
https://docs.groq.com/
https://langchain-ai.github.io/langgraph/
https://langfuse.com/docs
https://fastapi.tiangolo.com/
https://docs.streamlit.io/

💡 Pistes suivantes
Ajouter un checkpointer LangGraph pour la mémoire conversationnelle persistante
Ajouter un cache des réponses par agent

👻 HorRAGor BOT est prêt

✔ Backend FastAPI branché sur le graphe multi-agent
✔ 3 agents spécialisés (RAG, Scraper, Narration) via LangGraph
✔ Frontend Streamlit
✔ Monitoring Langfuse optionnel
