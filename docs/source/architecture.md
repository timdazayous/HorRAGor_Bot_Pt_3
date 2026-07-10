# Architecture multi-agent

HorRAGor BOT rompt avec l'architecture monolithique ReAct de la Partie 2 pour
adopter un réseau **peer-to-peer** de 4 agents spécialisés, orchestrés par
[LangGraph](https://langchain-ai.github.io/langgraph/). Aucun agent "Chef de
Projet" central : chaque agent traite sa tâche puis passe la main.

## Cartographie du graphe (générée depuis le code réel)

Le diagramme ci-dessous est produit par
`app.get_graph().draw_mermaid()` sur le `StateGraph` compilé
(`src/graph/pipeline.py`) — il reflète donc **toujours** la topologie réelle
du code, jamais un schéma dessiné à la main qui pourrait diverger. Pour le
régénérer après une modification du graphe :

```bash
uv run python docs/generate_graph_diagram.py
```

```{eval-rst}
.. mermaid:: _static/graph.mmd
```

## Les 4 agents

| Agent | Rôle | Fichier |
|---|---|---|
| **RAG** (Le Chercheur Local) | Interroge FAISS + Supabase, extrait le lore brut, corrige les approximations de titre de l'utilisateur | `src/graph/nodes.py::rag_node` |
| **Scraper** (L'Enquêteur du Web) | Déclenché uniquement si le RAG est incomplet — va chercher des anecdotes sur Wikipedia en direct | `src/graph/nodes.py::scraper_node` |
| **Narration** (L'Écrivain Gothique) | Isolé de toute la plomberie technique (*context trimming*) — ne reçoit que la synthèse factuelle, jamais les logs bruts | `src/graph/nodes.py::narration_node` |
| **Juge** (Évaluateur qualité) | Évalue la réponse finale contre le dossier factuel ; déclenche une régénération de la Narration si la confiance est insuffisante (budget de retry borné) | `src/graph/nodes.py::judge_node` |

## Routage conditionnel (`src/graph/router.py`)

- `should_scrape_or_narrate` : si le dossier RAG est complet → Narration
  directement ; sinon → Scraper, qui repasse ensuite la main à la Narration.
- `should_retry_or_end` : après le Juge, si la réponse est rejetée **et**
  qu'il reste du budget de retry (`JUDGE_MAX_RETRIES`, défaut 2) → retour vers
  la Narration avec la critique du Juge injectée ; sinon → fin du graphe. Le
  graphe ne boucle jamais indéfiniment : le budget de retry est strictement
  décroissant, garantissant la terminaison.

## Le State partagé (`src/models/state.py`)

Toutes les données transitent par un unique `TypedDict` (`AgentState`) fusionné
de manière incrémentale à chaque nœud — jamais écrasé :

- `messages` : historique complet, fusionné via le reducer `add_messages`
- `rag_context` / `scraper_context` / `final_answer` : synthèses successives
- `rag_complete`, `judge_verdict`, `retry_count` : signaux de routage
- `tools_used` : traçabilité (accumulée via `operator.add`) — agents traversés

## Monitoring

Chaque nœud du graphe est instrumenté (`src/metrics.py`) : latence, nombre
d'appels et tokens Groq consommés par agent, exposés sur `/metrics`
(Prometheus) et tracés en détail dans Langfuse (voir le README, section
Monitoring).
