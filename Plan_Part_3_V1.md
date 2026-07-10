Phase 0 — Dépendances
Ajouter langgraph (+ langgraph-checkpoint si besoin de mémoire persistante) et langfuse au pyproject.toml, puis uv sync.

Phase 1 — Restructuration mécanique

Créer src/, src/models/, src/tools/, src/graph/
frontend/app.py → app_frontend.py (racine, adapter les chemins/imports)
data/faiss.index + id_map.npy → data/faiss_index/
main_api.py → src/main.py
Le pipeline Partie 1 (app/, main.py racine, ingestion TMDB/Kaggle/Spark) reste intact, non concerné par cette partie.
Phase 2 — src/models/state.py
AgentState (TypedDict) : messages, user_query, rag_context, rag_complete (bool), scraper_context, final_answer, tools_used. On tranchera ensemble si "Le Juge" de la Partie 2 devient un 4ᵉ maillon après narration, ou reste en option.

Phase 3 — src/tools/

rag_tool.py : fusion de la recherche FAISS+Supabase existante (search_horror_movies, query_movie_metadata, find_similar_horror_movies)
scraper_tool.py : basé sur scrape_detailed_synopsis.py (Wikipedia), qui colle déjà à "creuser le web en direct"
Phase 4 — src/graph/nodes.py
rag_node, scraper_node, narration_node — chacun avec son propre SystemMessage spécialisé (Chercheur Local / Enquêteur / Écrivain Gothique), la narration ne recevant que la synthèse, pas les logs techniques (context trimming).

Phase 5 — src/graph/router.py
should_scrape_or_narrate(state) : renvoie "scraper" ou "narration" selon la complétude du contexte RAG.

Phase 6 — src/graph/pipeline.py
StateGraph + add_node/add_edge/add_conditional_edges → app = workflow.compile().

Phase 7 — src/main.py
FastAPI qui invoque le graphe compilé au lieu d'appeler llm_groq.generate_response directement.

Phase 8 — Langfuse
docker compose up -d (repo cloné à part comme indiqué au brief) + CallbackHandler branché sur l'invoke du graphe + variables LANGFUSE_* dans .env.example.

Phase 9 — Vérification
Tests manuels (cas RAG suffisant vs cas nécessitant le scraper), vérification des traces dans Langfuse, mise à jour du README.