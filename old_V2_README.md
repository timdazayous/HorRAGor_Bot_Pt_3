# 🩸 HorRAGor BOT — Partie 2

Agent conversationnel spécialisé dans l'univers de l'horreur (cinéma, littérature, jeux vidéo), basé sur une architecture **ReAct** avec Groq LLM, FAISS et Supabase.

---

## Architecture

```
┌──────────────────────────────────────┐
│   Streamlit  (Front-End)             │
│   app_frontend.py                    │
│   • Thème dark horror animé          │
│     (zombies, chauves-souris,        │
│      château, lune, brouillard)      │
│   • Zombies interactifs : drag &     │
│     throw, plateformes (nuages,      │
│      créneaux du château, orbite     │
│      autour de la lune)              │
│   • Verdict du Juge dans le          │
│     bandeau bas (🩸 / ⚠️ / 💀)       │
└──────────────────┬───────────────────┘
                   │ HTTP POST /chat
                   ▼
┌──────────────────────────────────────┐
│   FastAPI    (Back-End)              │
│   src/main.py                        │
│   • /chat  /health  /info            │
└──────────────────┬───────────────────┘
                   │ generate_response()
                   ▼
┌──────────────────────────────────────┐
│   Groq LLM  llama-3.3-70b            │
│   llm_groq.py                        │
│   • Tool-use (6 outils)              │
│   • Le Juge : évaluateur + retry     │
└──────┬───────────┬───────────────────┘
       │ tool calls│
       ▼           ▼
┌────────────┐  ┌──────────────────────┐
│ FAISS RAM  │  │ Supabase (PostgreSQL) │
│ 1179 films │  │ film / evaluation /  │
│ (synopsis) │  │ genre / analyse_spark│
└────────────┘  └──────────────────────┘
```

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| LLM | Groq — `llama-3.3-70b-versatile` |
| Back-End | FastAPI + Uvicorn (async) |
| Front-End | Streamlit — thème dark horror custom |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Mémoire vectorielle | FAISS (index en RAM) |
| Base de données | Supabase (PostgreSQL) via psycopg2 |
| Dépendances | `uv` |

---

## Prérequis

- Python 3.10+
- `uv` installé
- Compte [Groq](https://console.groq.com/) (gratuit)
- Accès Supabase (hérité Partie 1)

---

## Installation

```bash
git clone https://github.com/timdazayous/HorRAGor_Bot_Pt_3.git
cd HorRAGor_Bot_Pt_3
uv sync
```

---

## Configuration

Crée un fichier `.env` à la racine (copie `.env.example`) :

```env
# LLM
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx

# Base de données Supabase
# L'une OU l'autre suffit : le code utilise SUPABASE_DB_URL en priorité,
# sinon DATABASE_URL en fallback.
DATABASE_URL=postgresql://postgres:PASSWORD@db.XXXX.supabase.co:5432/postgres
SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.XXXX.supabase.co:5432/postgres

# Optionnel — configuration du serveur
API_HOST=0.0.0.0
API_PORT=8000
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2048
```

> La clé Groq est disponible sur [console.groq.com](https://console.groq.com/) → **API Keys** → **Create API Key**

---

## Lancement

**Terminal 1 — API FastAPI**
```bash
uvicorn src.main:app --reload
# → http://localhost:8000
# → Swagger : http://localhost:8000/docs
```

**Terminal 2 — Interface Streamlit**
```bash
streamlit run app_frontend.py
# → http://localhost:8501
```

---

## Outils de l'agent (Tools)

| # | Nom interne | Déclencheur LLM |
|---|-------------|-----------------|
| 1 | `query_movie_metadata` | Question sur un film précis ("parle-moi de X", "infos sur X") |
| 2 | `similar_movies` | Demande de films similaires à un titre |
| 3 | `search_horror_movies` | Recherche sémantique libre (requête FAISS) |
| 4 | `movie_age` | Âge d'un film, ancienneté, "est-ce récent ?" |
| 5 | `detailed_synopsis` | Détails approfondis, anecdotes, contexte de production |
| 6 | `survival_sim` | Simulation de survie dans un film ("je survivrais dans X ?") |

### Exemples de questions

```
"Parle-moi de The Shining"               → query_movie_metadata
"Films similaires à Hereditary"          → similar_movies
"Recommande un film de possession"       → search_horror_movies
"Quel âge a Halloween ?"                 → movie_age
"Donne-moi des anecdotes sur Get Out"    → detailed_synopsis
"Je survivrais dans Scream ?"            → survival_sim
```

---

## Le Juge (évaluateur de réponse)

Le Juge est un **4ᵉ agent du graphe LangGraph**, placé après l'Agent de Narration
(`src/graph/nodes.py::judge_node`). Il évalue la réponse finale par rapport au
dossier factuel (synthèse RAG + Scraper) qui l'a nourrie :

- Détecte les hallucinations et incohérences avec le dossier factuel
- Fournit un score de confiance (0.0 → 1.0)
- Déclenche un **retry automatique** (max `JUDGE_MAX_RETRIES`, défaut 2) si la
  réponse est invalide ET que la confiance est < `JUDGE_CONFIDENCE_THRESHOLD`
  (défaut 0.65) — la critique du Juge est alors réinjectée dans l'Agent de
  Narration pour la régénération (`src/graph/router.py::should_retry_or_end`)

Le verdict s'affiche en temps réel dans le **bandeau bas** de l'interface Streamlit :

| Icône | Label | Condition |
|-------|-------|-----------|
| 🩸 | LE JUGE A APPROUVÉ | is_valid=True et confiance ≥ 80 % |
| ⚠️ | LE JUGE EST MITIGÉ | is_valid=True et confiance < 80 % |
| 💀 | LE JUGE CONDAMNE | is_valid=False |

Le bandeau affiche aussi les **agents traversés** (`⚙ rag_agent › narration_agent › judge_agent`, etc.).
Les noms d'agents n'apparaissent jamais dans le corps de la réponse elle-même :
ils sont réservés au bandeau du Juge pour garder les messages naturels.

---

## Monitoring — stack complète (Langfuse, Prometheus, Grafana, Uptime Kuma)

Une seule commande lève toute l'infrastructure d'observabilité **+ l'API** elle-même :

```bash
docker compose up -d
```

| Service | URL | Rôle |
|---|---|---|
| API HorRAGor | http://localhost:8020 | Le graphe multi-agent conteneurisé |
| Langfuse | http://localhost:3000 | Traçage agent LLM (latence/nœud, tokens, décisions du graphe) |
| Prometheus | http://localhost:9095 | Métriques brutes (`/metrics` de l'API — Phase 11) |
| Grafana | http://localhost:3001 | Dashboards (admin / voir `GRAFANA_ADMIN_PASSWORD` dans `.env`) |
| Uptime Kuma | http://localhost:3002 | Supervision de disponibilité des services |

> Port 8020 plutôt que 8000 par défaut, pour éviter tout conflit avec un autre
> service déjà présent sur la machine hôte — ajustable dans `docker-compose.yml`.

### Premier lancement de Langfuse

`docker compose up -d` démarre aussi Postgres/ClickHouse/Redis/Minio nécessaires à
Langfuse (auto-hébergé, images officielles `langfuse/langfuse:3`). Une fois les
conteneurs `healthy` :

1. Rendez-vous sur `http://localhost:3000`, créez un compte (local, un faux mail fonctionne).
2. Créez un nouveau projet pour obtenir vos clés API.
3. Renseignez-les dans `.env` :

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

4. Relancez le service `api` (`docker compose up -d api`) pour qu'il prenne en compte les clés.

Le monitoring est **optionnel** : si `LANGFUSE_PUBLIC_KEY` est absente, l'API démarre
normalement sans instrumentation (voir les logs au démarrage : `Langfuse non configuré`
ou `Monitoring Langfuse activé`). Une fois configuré, chaque appel à `/chat` trace
automatiquement les 4 agents (RAG, Scraper, Narration, Juge) dans l'interface Langfuse.

### Secrets à changer avant tout déploiement partagé

`.env.example` liste les secrets serveur de la stack (`LANGFUSE_SALT`,
`LANGFUSE_ENCRYPTION_KEY`, `NEXTAUTH_SECRET`, `CLICKHOUSE_PASSWORD`, `REDIS_AUTH`,
`MINIO_ROOT_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`) avec des valeurs par défaut
**à remplacer** (voir commentaires `openssl rand -hex 32`) dès que la stack sort
d'un usage strictement local/pédagogique.

---

## Interface interactive (thème dark horror)

L'arrière-plan animé de Streamlit est entièrement injecté en JS/SVG (canvas + overlay).
Les zombies sont **manipulables à la souris** :

- **Drag & throw** — attrape un zombie, déplace-le et relâche pour le lancer ;
  une physique de gravité le fait retomber jusqu'au sol en arc.
- **Plateformes** — un zombie lancé peut atterrir et marcher sur :
  - les **nuages** dérivants (il en tombe s'il dépasse le bord),
  - les **créneaux du château** (5 plateformes statiques),
  - la **lune**, autour de laquelle il marche en orbite, y compris tête en bas.

> Les zombies marchent **au premier plan** (z-index élevé), devant le bandeau
> d'input et le verdict du Juge, sans jamais bloquer la saisie
> (couche `pointer-events:none`, sauf sur le corps d'un zombie pour le drag).

---

## Endpoints API

### `GET /health`
```bash
curl http://localhost:8000/health
```

### `POST /chat`
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "Parle-moi de The Shining"}'
```

Réponse :
```json
{
  "answer": "Titre : The Shining (The Shining)\nAnnée : 1980\n...\n--------\nUn chef-d'œuvre de Kubrick...",
  "tools_used": ["query_movie_metadata", "groq-llm"],
  "judge_verdict": {
    "is_valid": true,
    "confidence": 0.95,
    "reasoning": "Réponse cohérente avec les données de la base."
  },
  "conversation_id": "conv_anonymous"
}
```

### `GET /info`
```bash
curl http://localhost:8000/info
```

---

## Structure du projet

```
HorRAGor_Bot_Pt_3/
├── app_frontend.py                    # Interface Streamlit (thème dark horror animé)
├── .streamlit/config.toml             # Config Streamlit
├── src/
│   ├── main.py                        # API FastAPI
│   ├── models/                        # State partagé multi-agent (Partie 3)
│   ├── tools/                         # rag_tool.py, scraper_tool.py (Partie 3)
│   └── graph/                         # nodes.py, router.py, pipeline.py (Partie 3)
├── tools/
│   ├── __init__.py
│   ├── query_movie_metadata.py        # Tool 1 — métadonnées SQL Supabase
│   ├── find_similar_horror_movies.py  # Tool 2 — similarité FAISS + Supabase
│   ├── calculate_movie_age.py         # Tool 4 — calcul âge film (date en FR)
│   ├── scrape_detailed_synopsis.py    # Tool 5 — scraping Wikipedia
│   └── horror_survival_simulator.py   # Tool 6 — simulation survie ludique
├── utils/
│   └── build_faiss_index.py           # Construction de l'index FAISS
├── data/
│   └── faiss_index/
│       ├── faiss.index                # Index vectoriel (1179 films)
│       └── id_map.npy                 # Mapping index → ID film en base
├── llm_groq.py                        # Client Groq + dispatch tools + Le Juge
├── .env.example                       # Template de configuration
└── pyproject.toml                     # Dépendances (uv)
```

---

## Tests & couverture

```bash
uv run pytest
```

Lance toute la suite (API, graphe multi-agent, outils, UI Streamlit) avec un
rapport de couverture. Le seuil `--cov-fail-under=80` (configuré dans
`pyproject.toml`) fait échouer la commande si la couverture de `src/` et
`app_frontend.py` repasse sous 80 %.

- `tests/` : tests unitaires Partie 3 (mocks LangChain/Groq/psycopg2/FAISS —
  aucun appel réseau réel), plus `tests/test_app_frontend.py` qui utilise le
  framework officiel `streamlit.testing.v1.AppTest` pour exécuter et interagir
  avec l'interface Streamlit.
- `test_api.py` : tests de contrat de l'API FastAPI (`/chat`, `/health`, `/info`),
  le graphe multi-agent y est mocké pour rester rapide et déterministe.
- Les scripts `check_data_pipeline.py` / `check_groq_config.py` sont des
  diagnostics manuels de la Partie 1/2 (`python check_*.py`), pas des tests
  automatisés — volontairement hors du nom `test_*.py`.

---

## Documentation technique (Sphinx)

```bash
uv run python docs/generate_openapi.py       # (ré)génère la spec OpenAPI
uv run python docs/generate_graph_diagram.py # (ré)génère le diagramme du graphe
uv run sphinx-build -b html docs/source docs/build
```

Ouvre ensuite `docs/build/index.html` dans un navigateur. La documentation couvre :

- **la doc automatique de l'API** Intelligence (`src/main.py`) — schéma OpenAPI
  réel exporté et rendu via `sphinxcontrib-openapi` ;
- **le schéma relationnel de la base de données** (Hub & Spoke, MCD/MLD/MPD,
  repris de `Merise.md`) ;
- **la cartographie complète du graphe multi-agent** — diagramme Mermaid généré
  directement depuis la topologie réelle du `StateGraph` compilé
  (`app.get_graph().draw_mermaid()`), donc jamais obsolète ;
- **la référence du code** (autodoc sur `src/` : nœuds, routeur, pipeline,
  outils, métriques, config).

> La Couche Données (API dédiée + réseau Docker privé étanche) n'existe pas
> encore — sa documentation sera ajoutée à la semaine sécurité.

---

## CI/CD

`.github/workflows/ci.yml` s'exécute sur chaque push / pull request :

| Job | Rôle |
|---|---|
| `lint` | `ruff check` sur `src/`, `tests/`, `test_api.py`, `app_frontend.py` |
| `test` | `uv run pytest` — suite complète + seuil de couverture ≥ 80 % |
| `docs` | Régénère la spec OpenAPI + le diagramme du graphe, build Sphinx avec `-W` (warnings = erreurs) |
| `docker-build` | Build de `Dockerfile.api` (Couche Intelligence) — doit réussir sans erreur |
| `publish` | Uniquement sur push vers `main`, si tout le reste est vert : build & push de l'image sur GitHub Container Registry (`ghcr.io/<repo>-api`) |

Aucun secret à configurer : `publish` utilise `GITHUB_TOKEN`, fourni
automatiquement par GitHub Actions.

> Le pipeline CI/CD de la Couche Données (2ᵉ API) et de la Couche Présentation
> (image Docker de l'UI Streamlit) sera complété à la semaine sécurité, en
> même temps que ces services seront eux-mêmes conteneurisés/isolés.

---

## Dépannage

| Erreur | Solution |
|--------|----------|
| `GROQ_API_KEY non configurée` | Vérifie le fichier `.env` |
| `SUPABASE_DB_URL et DATABASE_URL absentes` | Renseigne au moins `DATABASE_URL` dans `.env` |
| L'agent répond "base inaccessible" | Supabase est en pause (Free Tier après 7 j) — réactive le projet sur le dashboard Supabase (voir logs API : `psycopg2.OperationalError`) |
| L'agent répond "aucun film trouvé" alors que la base tourne | Vérifie le schéma Hub & Spoke : genres via `film_genre`/`genre`, notes via `evaluation` (voir logs API pour l'erreur SQL exacte) |
| `ModuleNotFoundError` | Lance `uv sync` |
| `Connection refused` sur /chat | Vérifie que `uvicorn src.main:app` tourne |
| HuggingFace télécharge le modèle | Normal au 1er lancement (~91 Mo, mis en cache ensuite) |
| Index FAISS manquant | Lance `python utils/build_faiss_index.py` |

---

## Branches de développement

| Branche | Développeur |
|---------|-------------|
| `main` | Production |
| `dev-tim` | Tim — Front-End Streamlit |
| `dev-nicolas` | Nicolas — FAISS + similarité |
| `dev_julie` | Julie — API FastAPI + Tools |

---

## Partie 1

Le pipeline de données (ingestion TMDB, Kaggle, IMDB, Rotten Tomatoes, PySpark) est documenté dans [HorRAGor BOT Partie 1.pdf](HorRAGor%20BOT%20Partie%201.pdf) et dans [old_README.md](old_README.md).
