# 🩸 HorRAGor BOT

**HorRAGor** est un agent conversationnel spécialisé dans l'univers de l'horreur
(cinéma, littérature, jeux vidéo). Le projet s'est construit en trois parties
successives, chacune corrigeant les limites de la précédente :

| Partie | Objectif | Statut |
|---|---|---|
| **Partie 1** | Pipeline d'ingestion de données — construire la base de connaissances (1 179 films, 5 sources, Supabase) | ✅ Acquis, socle de données |
| **Partie 2** | Agent conversationnel monolithique (architecture **ReAct**) — un seul LLM, 6 tools, "Le Juge" évaluateur | ✅ Acquis, **remplacé par la Partie 3** |
| **Partie 3** | Architecture **multi-agent distribuée** (LangGraph) + industrialisation MLOps complète (monitoring, tests, docs, CI/CD) | 🚧 En cours — ce README |

Ce document couvre l'état actuel du projet (Partie 3) et résume les deux
parties précédentes pour comprendre d'où vient le code.

---

## Sommaire

- [Partie 1 — Pipeline de données](#partie-1--pipeline-de-données)
- [Partie 2 — Agent monolithique ReAct (historique)](#partie-2--agent-monolithique-react-historique)
- [Partie 3 — Architecture multi-agent](#partie-3--architecture-multi-agent)
  - [Pourquoi casser le monolithe](#pourquoi-casser-le-monolithe)
  - [Les 4 agents](#les-4-agents)
  - [Stack technique](#stack-technique)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Lancement](#lancement)
  - [Authentification — Refresh Tokens](#authentification--refresh-tokens)
  - [Monitoring — Langfuse, Prometheus, Grafana, Uptime Kuma](#monitoring--langfuse-prometheus-grafana-uptime-kuma)
  - [Journalisation (Loguru)](#journalisation-loguru)
  - [Tests & couverture](#tests--couverture)
  - [Documentation technique (Sphinx)](#documentation-technique-sphinx)
  - [CI/CD](#cicd)
  - [Endpoints API](#endpoints-api)
  - [Structure du projet](#structure-du-projet)
  - [Dépannage](#dépannage)
- [Branches de développement](#branches-de-développement)
- [Prochaine étape — semaine sécurité](#prochaine-étape--semaine-sécurité)

---

## Partie 1 — Pipeline de données

Avant de pouvoir discuter d'horreur, encore fallait-il un socle de
connaissances fiable. La Partie 1 construit ce socle : un pipeline **MDM
(Master Data Management)** qui collecte, fusionne et nettoie les données de
**1 179 films d'horreur** depuis 5 sources, puis les persiste dans Supabase
(PostgreSQL).

| Source | Rôle | Technologie |
|---|---|---|
| **TMDB** (API REST) | Source maîtresse — fournit les IDs de référence (`tmdb_id`, `imdb_id`) | `requests` |
| **Rotten Tomatoes** | Enrichissement scores critiques/audience | Selenium + Chrome headless |
| **Kaggle** (CSV) | Enrichissement synopsis/budget manquants | Polars |
| **IMDB** (SQLite) | Enrichissement notes communauté | SQLite |
| **PySpark** | Analyse textuelle des synopsis (langue, mots-clés horreur, richesse) | PySpark / Python pur (Windows) |

**Principe MDM** : TMDB est la source de référence ; les 4 autres
enrichissent uniquement les champs manquants — jamais de création de film ni
d'écrasement des données déjà présentes.

**Modélisation Merise** (Hub & Spoke) — 6 tables PostgreSQL : `film` (hub
central), `genre`, `film_genre` (liaison N-N), `evaluation` (scores
multi-sources unifiés), `analyse_spark` (enrichissement NLP), `source`
(traçabilité MDM). Détail complet dans [`Merise.md`](Merise.md) et repris
dans la [documentation Sphinx](#documentation-technique-sphinx).

📄 Détails complets : [HorRAGor BOT Partie 1.pdf](HorRAGor%20BOT%20Partie%201.pdf) · [old_README.md](old_README.md)

---

## Partie 2 — Agent monolithique ReAct (historique)

La Partie 2 a construit le premier "cerveau" du bot : un agent unique basé sur
l'architecture **ReAct**, exposé via FastAPI + Streamlit.

- **LLM** : Groq (`llama-3.3-70b-versatile`) — cloud, rapide, gratuit en développement
- **6 tools** dispatchés manuellement par le LLM : `query_movie_metadata`,
  `find_similar_horror_movies`, `search_horror_movies` (FAISS), `movie_age`,
  `scrape_detailed_synopsis` (Wikipedia), `horror_survival_simulator`
- **Le Juge** : un second appel LLM qui évalue chaque réponse (hallucinations,
  cohérence) et déclenche un retry si la confiance est trop basse
- **FAISS** (1 179 vecteurs, `sentence-transformers/all-MiniLM-L6-v2`) pour la
  recherche sémantique, **Supabase** pour les métadonnées structurées

**Limite identifiée** : un agent monolithique unique sature vite en
production — *prompt drowning* (trop de logique technique et de résultats
d'outils dans un seul contexte), risques de conflits décisionnels, et
affaiblissement de la plume narrative noyée dans les données techniques.
C'est ce problème que la Partie 3 résout en éclatant l'agent en équipe
spécialisée.

Le code de cette étape (`llm_groq.py`, `tools/`) reste dans le dépôt à titre
de référence mais n'est **plus utilisé** par l'API en cours d'exécution
(`src/main.py` invoque désormais le graphe multi-agent).

---

## Partie 3 — Architecture multi-agent

### Pourquoi casser le monolithe

L'agent ReAct unique de la Partie 2 est remplacé par une architecture
**Multi-Agent distribuée et collaborative** sous [LangGraph](https://langchain-ai.github.io/langgraph/) :
une équipe de 4 profils ultra-spécialisés qui partagent un **State** commun
et se passent le relais, **sans agent "Chef de Projet" central**.

### Les 4 agents

```
START → rag ──(complet)────────────→ narration ⇄ judge ──(satisfaisant/épuisé)──→ END
         │                               ↑           │(rejeté, retries restants)
         └─(incomplet)→ scraper ─────────┘           └────────────────┘
```

| Agent | Rôle | Fichier |
|---|---|---|
| 🔎 **RAG** (Le Chercheur Local) | Premier point de contact — interroge FAISS + Supabase, extrait le lore brut, corrige les approximations de titre de l'utilisateur | `src/graph/nodes.py::rag_node` |
| 🕸️ **Scraper** (L'Enquêteur du Web) | Déclenché si le RAG est incomplet (routage conditionnel), **ou systématiquement pour l'intention `ANECDOTES`** — va chercher des anecdotes sur Wikipedia en direct | `src/graph/nodes.py::scraper_node` |
| ✍️ **Narration** (L'Écrivain Gothique) | Isolé de toute la plomberie technique (*context trimming*) — ne reçoit que la synthèse factuelle, jamais les logs bruts ni les noms d'outils | `src/graph/nodes.py::narration_node` |
| ⚖️ **Juge** (Évaluateur qualité) | Évalue la réponse finale contre le dossier factuel ; déclenche une régénération de la Narration si la confiance est insuffisante (budget de retry borné, `JUDGE_MAX_RETRIES`) | `src/graph/nodes.py::judge_node` |

### Les 6 intentions du RAG (parité avec les outils de la Partie 2)

Le `rag_node` classifie chaque question via un appel LLM en une des 6
intentions suivantes, en résolvant les follow-up conversationnels (« ce
dernier », « et lui ? ») sur le film réellement discuté grâce à l'historique
des messages :

| Intention | Équivalent Partie 2 | Comportement |
|---|---|---|
| `TITRE` | `query_movie_metadata` | Fiche complète d'un film précis |
| `THEME` | `search_horror_movies` (FAISS) | Recherche sémantique par thème/ambiance |
| `SURVIE` | `horror_survival_simulator` | Simulateur de survie (narration au format dédié : % de survie, cause de mort, menaces, conseils) |
| `AGE` | `movie_age` | Calcul de l'ancienneté du film |
| `SIMILAIRE` | `find_similar_horror_movies` | k plus proches voisins FAISS (hors le film source) |
| `ANECDOTES` | `scrape_detailed_synopsis` | Force le passage par le Scraper même si la fiche RAG est déjà complète en base |

Toutes ces fonctions (`src/tools/rag_tool.py`) respectent le même contrat de
retour que `rag_search` (`{context, is_complete, matched_title}`), donc la
Narration et le Juge n'ont nécessité aucune modification pour les accueillir.
Seul `router.py` a gagné une condition supplémentaire, pour le cas `ANECDOTES`
(voir encart ci-dessous).

> La classification (extraction du couple intent/sujet) tourne à
> **`temperature=0`** avec un prompt qui interdit explicitement au LLM de
> répondre à la question — sans ça, le modèle dévie parfois du format à deux
> lignes attendu (il répond directement au lieu de classifier), ce qui fait
> silencieusement retomber sur `TITRE` par défaut. Vérifié en conditions
> réelles (Groq) sur les 6 intentions.

> Le forçage du Scraper pour `ANECDOTES` passe par un champ dédié du State,
> **`force_scrape`**, distinct de `rag_complete`. Ce dernier garde ainsi son
> sens littéral (la donnée locale est-elle réellement incomplète ?), et
> `router.py` reste fidèle au principe du brief : un routage qui reflète
> honnêtement la présence ou l'absence d'informations dans le State, jamais
> une valeur détournée pour produire un effet de bord.

Le **routage conditionnel** (`src/graph/router.py`) matérialise l'intelligence
dynamique du réseau :
- `should_scrape_or_narrate` : dossier RAG suffisant → Narration directe ;
  sinon → Scraper, qui repasse la main à la Narration.
- `should_retry_or_end` : après le Juge, rejet + budget restant → retour vers
  la Narration avec la critique injectée ; sinon → fin. Le budget de retry
  strictement décroissant garantit la terminaison du graphe.

Toutes les données transitent par un **State** unique (`src/models/state.py`,
`AgentState`) fusionné de façon incrémentale à chaque nœud — jamais écrasé.

La cartographie **exacte** du graphe (générée depuis le code réel, jamais
dessinée à la main) est disponible dans la
[documentation Sphinx](#documentation-technique-sphinx).

### Stack technique

| Composant | Technologie |
|---|---|
| Orchestration multi-agent | **LangGraph** (`StateGraph`) |
| LLM | Groq — `llama-3.3-70b-versatile` (un client par agent, températures différenciées) |
| Back-End | FastAPI + Uvicorn (async) |
| Front-End | Streamlit — thème dark horror animé |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Mémoire vectorielle | FAISS (1 179 vecteurs, en RAM) |
| Base de données | Supabase (PostgreSQL) via `psycopg2` |
| Monitoring agent | **Langfuse** (auto-hébergé) |
| Métriques | **Prometheus** + **Grafana** |
| Supervision disponibilité | **Uptime Kuma** |
| Authentification | JWT (`pyjwt`) + refresh tokens opaques, mots de passe hashés (`bcrypt`) |
| Logs | **Loguru** (interception unifiée de tout `logging` stdlib) |
| Tests | `pytest` + `pytest-cov` (couverture ≥ 80 %) |
| Documentation | **Sphinx** (autodoc + OpenAPI + Mermaid) |
| CI/CD | GitHub Actions (lint, tests, docs, build & push Docker) |
| Dépendances | `uv` |

### Installation

```bash
git clone https://github.com/timdazayous/HorRAGor_Bot_Pt_3.git
cd HorRAGor_Bot_Pt_3
uv sync
```

**Prérequis** : Python 3.10+, `uv`, un compte [Groq](https://console.groq.com/)
(gratuit), un accès Supabase (hérité de la Partie 1), et Docker Desktop si tu
veux la stack de monitoring complète.

### Configuration

Copie `.env.example` vers `.env` et renseigne au minimum :

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
SUPABASE_DB_URL=postgresql://postgres.TON_PROJET:PASSWORD@aws-0-xx-xxxx-1.pooler.supabase.com:6543/postgres
```

> Utilise l'URL du **connection pooler** Supabase (Project Settings → Database
> → Connection pooling), pas la connexion directe `db.xxxx.supabase.co` : cette
> dernière n'a souvent qu'une adresse IPv6, injoignable depuis le réseau Docker
> par défaut (Docker Desktop). Le pooler résout en IPv4.

Tout le reste (`RAG_TEMPERATURE`, `JUDGE_MAX_RETRIES`, clés Langfuse, secrets
de la stack Docker...) a des valeurs par défaut raisonnables — voir les
commentaires de `.env.example`.

### Lancement

**Sans Docker (développement)**

```bash
# Terminal 1 — API FastAPI (graphe multi-agent)
uvicorn src.main:app --reload
# → http://localhost:8000  (Swagger : /docs)

# Terminal 2 — Interface Streamlit
streamlit run app_frontend.py
# → http://localhost:8501
```

**Avec Docker (API + stack de monitoring complète)**

```bash
docker compose up -d
```

Lève l'API (`http://localhost:8020`) **et** Langfuse, Prometheus, Grafana,
Uptime Kuma en une seule commande — voir la section suivante.

### Authentification — Refresh Tokens

L'endpoint `/chat` exige désormais une authentification : ça verrouille les
échanges entre l'IHM Streamlit et l'API Intelligence contre tout appel externe
non autorisé.

**Schéma** : `access_token` JWT (courte durée, 30 min par défaut) + `refresh_token`
opaque (longue durée, 7 jours), dont seul le hash SHA-256 est stocké en base
(table `refresh_tokens`). Chaque rafraîchissement **révoque** l'ancien refresh
token et en émet un nouveau (rotation à usage unique) — un token volé ne reste
exploitable qu'une seule fois.

**Qui s'authentifie ?** Un unique compte de service (`streamlit-ui`), pas les
visiteurs du chatbot — l'IHM s'authentifie silencieusement au démarrage et se
ré-authentifie en arrière-plan sur un 401, sans écran de connexion visible.

**Mise en place (une fois)** :

```bash
uv run python migrations/apply_migrations.py       # crée les tables users / refresh_tokens
uv run python migrations/seed_service_account.py   # génère le compte de service
# copie SERVICE_ACCOUNT_USERNAME / SERVICE_ACCOUNT_PASSWORD affichés dans .env
```

**Endpoints** :

| Route | Rôle |
|---|---|
| `POST /auth/login` | `{username, password}` → `{access_token, refresh_token}` |
| `POST /auth/refresh` | `{refresh_token}` → nouveau couple de tokens (rotation) |
| `POST /chat` | Exige `Authorization: Bearer <access_token>` — 401 sinon |

### Monitoring — Langfuse, Prometheus, Grafana, Uptime Kuma

| Service | URL | Rôle |
|---|---|---|
| API HorRAGor | http://localhost:8020 | Le graphe multi-agent conteneurisé |
| Langfuse | http://localhost:3000 | Traçage agent LLM (latence/nœud, tokens, décisions du graphe) |
| Prometheus | http://localhost:9095 | Métriques brutes (`/metrics` de l'API) |
| Grafana | http://localhost:3001 | Dashboards (admin / voir `GRAFANA_ADMIN_PASSWORD` dans `.env`) |
| Uptime Kuma | http://localhost:3002 | Supervision de disponibilité des services |

> Port **8020** plutôt que 8000 par défaut, pour éviter tout conflit avec un
> autre service déjà présent sur la machine hôte.

**Premier lancement de Langfuse** — `docker compose up -d` démarre aussi
Postgres/ClickHouse/Redis/Minio nécessaires (auto-hébergé, images officielles
`langfuse/langfuse:3`). Une fois les conteneurs `healthy` :

1. Rends-toi sur `http://localhost:3000`, crée un compte (local, un faux mail fonctionne).
2. Crée un nouveau projet pour obtenir tes clés API.
3. Renseigne-les dans `.env` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`).
4. Relance le service `api` (`docker compose up -d api`).

Le monitoring Langfuse est **optionnel** : sans clé, l'API démarre
normalement sans instrumentation. Chaque nœud du graphe est par ailleurs
toujours instrumenté (`src/metrics.py`) : latence, appels et tokens Groq
consommés **par agent**, exposés sur `/metrics` et visualisables via le
dashboard Grafana provisionné automatiquement.

> Secrets serveur (`LANGFUSE_SALT`, `NEXTAUTH_SECRET`, `CLICKHOUSE_PASSWORD`,
> `GRAFANA_ADMIN_PASSWORD`...) : valeurs par défaut dans `.env.example`, **à
> remplacer** (voir `openssl rand -hex 32`) avant tout déploiement partagé.

### Journalisation (Loguru)

`src/logging_config.py` intercepte **tous** les logs — API, graphe
multi-agent, outils, mais aussi les librairies tierces (uvicorn, httpx,
sentence_transformers) — vers un format unifié : console colorée + fichier
rotatif (`logs/horragor.log`, 10 Mo, rétention 7 jours). Plus jamais deux
formats de logs à recouper.

### Tests & couverture

```bash
uv run pytest
```

Lance toute la suite (API, graphe multi-agent, outils, UI Streamlit) avec un
rapport de couverture. Le seuil `--cov-fail-under=80` (configuré dans
`pyproject.toml`) fait échouer la commande si la couverture de `src/` et
`app_frontend.py` repasse sous 80 % — actuellement **~92 %**.

- `tests/` : tests unitaires (mocks LangChain/Groq/psycopg2/FAISS — aucun
  appel réseau réel), dont `tests/test_auth.py` (hash, JWT, rotation des
  refresh tokens) et `tests/test_app_frontend.py` qui utilise le framework
  officiel `streamlit.testing.v1.AppTest`.
- `test_api.py` : tests de contrat de l'API FastAPI, graphe mocké pour rester
  rapide et déterministe.
- `check_data_pipeline.py` / `check_groq_config.py` : diagnostics manuels
  Partie 1/2 (`python check_*.py`), volontairement hors du nom `test_*.py`.

### Documentation technique (Sphinx)

```bash
uv run python docs/generate_openapi.py       # (ré)génère la spec OpenAPI
uv run python docs/generate_graph_diagram.py # (ré)génère le diagramme du graphe
uv run sphinx-build -b html docs/source docs/build
```

Ouvre `docs/build/index.html`. Couvre la doc auto de l'API Intelligence
(OpenAPI), le schéma relationnel de la base de données, et la cartographie
complète du graphe multi-agent (diagramme Mermaid généré depuis la topologie
réelle du `StateGraph` compilé — jamais obsolète).

### CI/CD

`.github/workflows/ci.yml` s'exécute sur chaque push / pull request :

| Job | Rôle |
|---|---|
| `lint` | `ruff check` |
| `test` | Suite complète + seuil de couverture ≥ 80 % |
| `docs` | Régénère OpenAPI + diagramme, build Sphinx (`-W`, warnings = erreurs) |
| `docker-build` | Build de `Dockerfile.api` |
| `publish` | Sur push vers `main` uniquement, si tout est vert : build & push sur `ghcr.io/<repo>-api` (via `GITHUB_TOKEN`, aucun secret à configurer) |

### Endpoints API

> Les exemples ci-dessous utilisent `:8000` (lancement `uvicorn` direct, sans
> Docker). En passant par `docker compose up -d`, remplace par `:8020` (voir
> section Monitoring).

```bash
# Santé (public, pas d'authentification)
curl http://localhost:8000/health

# Authentification — récupère un couple de tokens
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "streamlit-ui", "password": "TON_MOT_DE_PASSE_DE_SERVICE"}'
# → {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# Question à l'agent (authentification requise)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"question": "Parle-moi de The Shining"}'

# Rafraîchir un access token expiré (rotation : l'ancien refresh_token est révoqué)
curl -X POST "http://localhost:8000/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'

# Infos système
curl http://localhost:8000/info
```

Réponse type de `/chat` :

```json
{
  "answer": "Mon cher ami des ténèbres, laisse-toi conter l'histoire de The Shining...",
  "tools_used": ["rag_agent", "narration_agent", "judge_agent"],
  "judge_verdict": {
    "is_valid": true,
    "confidence": 0.95,
    "reasoning": "Réponse fidèle au dossier factuel, sans hallucination."
  },
  "conversation_id": "conv_anonymous"
}
```

### Structure du projet

```
HorRAGor_Bot_Pt_3/
├── app_frontend.py                    # Interface Streamlit (thème dark horror animé)
├── .streamlit/config.toml             # Config Streamlit
├── src/
│   ├── main.py                        # API FastAPI — endpoint /chat, branche le graphe
│   ├── config.py                      # Configuration LLM (Groq) et chemins
│   ├── auth.py                        # Authentification par Refresh Tokens
│   ├── metrics.py                     # Instrumentation Prometheus par agent
│   ├── logging_config.py              # Journalisation Loguru unifiée
│   ├── models/state.py                # AgentState — State partagé multi-agent
│   ├── tools/
│   │   ├── rag_tool.py                # FAISS + Supabase (recherche, âge, films similaires, simulateur de survie)
│   │   └── scraper_tool.py            # Recherche Wikipedia en direct
│   └── graph/
│       ├── nodes.py                   # rag_node / scraper_node / narration_node / judge_node
│       ├── router.py                  # Aiguillage conditionnel
│       └── pipeline.py                # Assemblage et compilation du StateGraph
├── docs/                              # Documentation Sphinx (source + scripts de génération)
├── migrations/                        # Tables auth (users, refresh_tokens) + seed du compte de service
├── monitoring/                        # Config Prometheus + provisioning Grafana
├── tests/                             # Tests unitaires Partie 3
├── .github/workflows/ci.yml           # Pipeline CI/CD
├── docker-compose.yml                 # API + Langfuse + Prometheus + Grafana + Uptime Kuma
├── Dockerfile.api                     # Image de l'API multi-agent
│
├── app/                                # Pipeline d'ingestion (Partie 1 — Data)
├── tools/                              # Tools legacy Partie 2 (query_movie_metadata, etc.)
├── utils/build_faiss_index.py          # Construction de l'index FAISS
├── llm_groq.py                         # Agent monolithique ReAct (Partie 2 — non utilisé par l'API)
│
├── data/faiss_index/                  # Index vectoriel (1 179 films)
├── Merise.md                           # Modélisation Merise de la BDD (Partie 1)
├── .env.example                        # Template de configuration
└── pyproject.toml                      # Dépendances (uv)
```

### Dépannage

| Erreur | Solution |
|--------|----------|
| `GROQ_API_KEY non configurée` | Vérifie le fichier `.env` |
| `SUPABASE_DB_URL et DATABASE_URL absentes` | Renseigne au moins `DATABASE_URL` dans `.env` |
| L'agent répond "base inaccessible" | Supabase en pause (Free Tier après 7 j) — réactive sur le dashboard Supabase |
| `ModuleNotFoundError` | Lance `uv sync` |
| `Connection refused` sur `/chat` | Vérifie que `uvicorn src.main:app` (ou le conteneur `api`) tourne |
| Index FAISS manquant | Lance `python utils/build_faiss_index.py` |
| Port déjà utilisé (Docker) | Un autre projet occupe le port — ajuste le mapping dans `docker-compose.yml` |
| Grafana boucle au démarrage | Volume `grafana_data` corrompu par un changement de config datasource — `docker compose rm -f grafana && docker volume rm horragor_bot_pt_3_grafana_data` puis relance |
| `/auth/login` répond 500 ("Network is unreachable") depuis Docker | `SUPABASE_DB_URL` pointe sur la connexion directe (IPv6 seule) — utilise l'URL du connection pooler (voir section Configuration) |
| `/chat` répond 401 alors que tu as un token | Le token a expiré (30 min par défaut) — l'IHM se rafraîchit automatiquement ; en curl, relance `/auth/login` |

---

## Branches de développement

| Branche | Développeur |
|---------|-------------|
| `main` | Production |
| `dev-tim` | Tim — Front-End Streamlit, architecture multi-agent, MLOps |
| `dev-nicolas` | Nicolas — FAISS + similarité |
| `dev_julie` | Julie — API FastAPI + Tools |

---

## Prochaine étape — semaine sécurité

Le cahier des charges MLOps prévoit un dernier livrable pour la semaine dédiée
à la sécurité :

- ✅ **Couche Intelligence** : authentification par **Refresh Tokens** entre
  l'IHM et l'API multi-agent — fait (voir section Authentification ci-dessus).
- **Couche Données** : base de données encapsulée derrière sa propre API,
  dans un réseau Docker privé **étanche** (inaccessible de l'extérieur).
- **Couche Présentation** : UI Streamlit conteneurisée, communication
  chiffrée vers l'API.
- **Gouvernance** : CI/CD étendu aux 3 couches, anomalies trackées en
  **GitHub Issues**.

Ce README sera complété en conséquence une fois ces briques en place.
