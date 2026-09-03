# 🩸 HorRAGor BOT

**HorRAGor** est un agent conversationnel spécialisé dans l'univers de l'horreur
(cinéma, littérature, jeux vidéo). Le projet s'est construit en trois parties
successives, chacune corrigeant les limites de la précédente :

| Partie | Objectif | Statut |
|---|---|---|
| **Partie 1** | Pipeline d'ingestion de données — construire la base de connaissances (1 179 films, 5 sources, Supabase) | ✅ Acquis, socle de données |
| **Partie 2** | Agent conversationnel monolithique (architecture **ReAct**) — un seul LLM, 6 tools, "Le Juge" évaluateur | ✅ Acquis, **remplacé par la Partie 3** |
| **Partie 3** | Architecture **multi-agent distribuée** (LangGraph) + industrialisation MLOps complète (monitoring, tests, docs, CI/CD) | ✅ Acquis — ce README |
| **Projet final sécurité** | Durcissement de l'API : OAuth2, rôles, rotation/révocation, rate limiting, CORS, fail-closed (voir [`projet-final-horragor.md`](projet-final-horragor.md)) | ✅ Acquis — voir [Sécurité](#authentification--refresh-tokens) |

Ce document couvre l'état actuel du projet (Partie 3 + durcissement sécurité)
et résume les deux parties précédentes pour comprendre d'où vient le code.

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
  - [Vault & Traefik (stack locale)](#vault--traefik-stack-locale)
  - [Journalisation (Loguru)](#journalisation-loguru)
  - [Tests & couverture](#tests--couverture)
  - [Documentation technique (Sphinx)](#documentation-technique-sphinx)
  - [CI/CD](#cicd)
  - [Endpoints API](#endpoints-api)
  - [Structure du projet](#structure-du-projet)
  - [Dépannage](#dépannage)
- [Branches de développement](#branches-de-développement)
- [Sécurité — bilan du projet final](#sécurité--bilan-du-projet-final)

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
| Authentification | JWT (`pyjwt`) + refresh tokens opaques, rôles, rate limiting, mots de passe hashés (`bcrypt`) |
| Logs | **Loguru** (interception unifiée de tout `logging` stdlib) |
| Tests | `pytest` + `pytest-cov` (couverture ≥ 80 %) |
| Documentation | **Sphinx** (autodoc + OpenAPI + Mermaid) |
| CI/CD | GitHub Actions (lint, tests, docs, build & push Docker) |
| Dépendances | `uv` |
| Routing (stack locale) | **Traefik** — sous-domaines `*.horragor.localhost`, aucun port direct |
| Secrets (stack locale) | **HashiCorp Vault** (mode dev) + Vault Agent — rendu des secrets en `env_file` |

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

**Avec Docker (API + stack de monitoring complète + Vault + Traefik)**

```bash
bash scripts/up.sh
```

Premier lancement (ou après `docker compose down -v`) : utilise **ce script**,
pas `docker compose up -d` seul — Vault doit avoir fini de pousser puis de
rendre les secrets avant que l'API et Langfuse ne démarrent (détails dans
[Vault & Traefik](#vault--traefik-stack-locale)). Sur un redémarrage simple
(les secrets déjà rendus sont toujours sur disque), `docker compose up -d`
seul suffit.

Lève l'API, Langfuse, Prometheus, Grafana, Uptime Kuma, Vault et Traefik.
Plus aucun service n'expose de port direct : tout se joint par sous-domaine
via Traefik (`http://api.horragor.localhost`, etc.) — voir la section suivante.

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
Chaque compte porte un **rôle** (`user` par défaut, `admin`) — colonne
`users.role`, embarquée dans le claim `role` de l'access token — préparant
l'autorisation par rôle sur les futures routes d'administration.

**Mise en place (une fois)** :

```bash
uv run python migrations/apply_migrations.py       # crée/actualise les tables users / refresh_tokens
uv run python migrations/seed_service_account.py   # génère le compte de service (role=user)
# copie SERVICE_ACCOUNT_USERNAME / SERVICE_ACCOUNT_PASSWORD affichés dans .env

uv run python migrations/seed_demo_users.py         # optionnel : comptes demo-user / demo-admin
```

**Endpoints** :

| Route | Rôle |
|---|---|
| `POST /auth/login` | `{username, password}` (JSON) → `{access_token, refresh_token}` |
| `POST /token` | `username=...&password=...` (form, OAuth2 Password Grant) → même réponse — alimente le bouton *Authorize* de `/docs` |
| `POST /auth/refresh` | `{refresh_token}` → nouveau couple de tokens (rotation) |
| `POST /logout` | `{refresh_token}` → le révoque ; il ne fonctionne plus sur `/auth/refresh` ensuite |
| `POST /chat` | Exige `Authorization: Bearer <access_token>` — 401 (`WWW-Authenticate: Bearer`) sinon |
| `POST /admin/reload-index` | Exige en plus `role=admin` — 403 sinon |

> `/auth/login` et `/token` partagent exactement la même logique
> (`auth.authenticate_user` + `auth.issue_token_pair`) ; seul le format de la
> requête change. `/auth/login` reste celui utilisé par l'IHM Streamlit
> (JSON), `/token` suit le standard OAuth2 attendu par les outils/clients
> génériques. Un échec renvoie **401** avec l'en-tête `WWW-Authenticate:
> Bearer` et un message identique que le compte existe ou non
> (anti-énumération).

**Le graphe est protégé** : `require_auth` (dépendance FastAPI sur `/chat`)
décode le JWT en imposant l'algorithme (`algorithms=["HS256"]`), vérifie
l'expiration, et n'accepte que `type=access` — un refresh token présenté sur
`/chat` est donc rejeté (**401**), qu'il soit opaque comme émis en pratique
ou un JWT `type=refresh` forgé. FastAPI résout `require_auth` avant même
d'exécuter le corps de l'endpoint : sans token valide, **aucun nœud du graphe
n'est jamais invoqué**. Le corps de `/chat` est validé par le modèle
Pydantic `ChatRequest` (**422** si malformé). Voir `TestAuthEndpoints` dans
`test_api.py` pour le détail de ces garanties (y compris token signé en
algorithme `none`).

**Autorisation par rôle** : `require_admin` étend `require_auth` d'une
vérification du claim `role`. Un utilisateur authentifié mais non-admin reçoit
**403** (pas 401 : il est bien identifié, juste pas autorisé) — voir
`TestAdminEndpoints` dans `test_api.py`. Route d'administration exposée :
`POST /admin/reload-index`, qui recharge l'index FAISS (`src/tools/rag_tool.py::reload_index`)
depuis le disque sans redémarrer l'API, utile après un ré-enrichissement du
catalogue de films.

**Durcissement** :
- `JWT_SECRET_KEY` est **fail-closed** (`src/config.py`) : sans elle dans
  l'environnement, l'API refuse carrément de démarrer plutôt que de tourner
  avec une clé par défaut prévisible (génère la tienne avec `openssl rand -hex 32`).
- **Rate limiting anti brute-force** sur `/token` et `/auth/login`
  (`src/rate_limit.py`, fenêtre glissante en mémoire, par IP × route,
  configurable via `RATE_LIMIT_LOGIN_MAX_ATTEMPTS`/`_WINDOW_SECONDS`) — **429**
  au-delà du quota (5 tentatives / 60 s par défaut).
- **CORS restreint** à `ALLOWED_ORIGIN` (l'IHM Streamlit, `http://localhost:8501`
  par défaut) — jamais `*` alors que `allow_credentials=True`.
- **Anti-énumération** : message d'échec de connexion identique, que le
  compte existe ou non.
- **Journalisation Loguru** de toute tentative refusée (login échoué, token
  rejeté, 403 admin, quota dépassé) — jamais le mot de passe ni le token en clair.

### Monitoring — Langfuse, Prometheus, Grafana, Uptime Kuma

| Service | URL | Rôle |
|---|---|---|
| API HorRAGor | http://api.horragor.localhost | Le graphe multi-agent conteneurisé |
| Langfuse | http://langfuse.horragor.localhost | Traçage agent LLM (latence/nœud, tokens, décisions du graphe) |
| Prometheus | http://prometheus.horragor.localhost | Métriques brutes (`/metrics` de l'API) |
| Grafana | http://grafana.horragor.localhost | Dashboards (admin / voir mot de passe — [Vault & Traefik](#vault--traefik-stack-locale)) |
| Uptime Kuma | http://uptime.horragor.localhost | Supervision de disponibilité des services |

> Plus de ports directs (`8020`, `3000`, `3001`, `9095`, `3002`) : tout passe
> par Traefik, sur ces sous-domaines `*.horragor.localhost` (résolvent vers
> 127.0.0.1 nativement) — voir [Vault & Traefik](#vault--traefik-stack-locale).

**Premier lancement de Langfuse** — `bash scripts/up.sh` démarre aussi
Postgres/ClickHouse/Redis/Minio nécessaires (auto-hébergé, images officielles
`langfuse/langfuse:3`). Une fois les conteneurs `healthy` :

1. Rends-toi sur `http://langfuse.horragor.localhost`, crée un compte (local, un faux mail fonctionne).
2. Crée un nouveau projet pour obtenir tes clés API.
3. Renseigne-les dans `.env` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`).
4. Relance le service `api` (`docker compose up -d api`).

Le monitoring Langfuse est **optionnel** : sans clé, l'API démarre
normalement sans instrumentation. Chaque nœud du graphe est par ailleurs
toujours instrumenté (`src/metrics.py`) : latence, appels et tokens Groq
consommés **par agent**, exposés sur `/metrics` et visualisables via le
dashboard Grafana provisionné automatiquement.

### Vault & Traefik (stack locale)

Ajout pédagogique (cours HashiCorp / routing) sur la stack Docker locale —
**sans valeur en production tel quel**, voir les encarts "dev-only" ci-dessous.

**Traefik** (reverse proxy) route chaque service sur un sous-domaine plutôt
que d'exposer des ports directs, via la découverte automatique des conteneurs
Docker (labels `traefik.*` dans `docker-compose.yml` — aucune config statique
à maintenir en dehors du fichier compose lui-même) :

| Sous-domaine | Service |
|---|---|
| `traefik.horragor.localhost` (ou `:8080`) | Dashboard Traefik — carte en direct des routers/services découverts |
| `api.horragor.localhost` | API HorRAGor |
| `langfuse.horragor.localhost` | Langfuse |
| `grafana.horragor.localhost` | Grafana |
| `prometheus.horragor.localhost` | Prometheus |
| `uptime.horragor.localhost` | Uptime Kuma |
| `vault.horragor.localhost` | UI Vault |

> **Dev-only** : dashboard Traefik sans authentification (`--api.insecure=true`),
> pas de TLS (HTTP simple sur `:80`). À corriger avant tout déploiement partagé
> (middleware d'auth sur le dashboard, `entrypoints.websecure` + certificats).

> **Docker Desktop (Windows)** : le montage de `/var/run/docker.sock` (comment
> Traefik découvre les autres conteneurs) peut échouer selon l'installation —
> `docker compose logs traefik` boucle alors sur `Failed to retrieve
> information of the docker client and server host`. Cause identifiée sur
> Docker Desktop 4.89 : sa VM interne n'expose plus ce chemin classique.
> Détail et piste de résolution dans [Dépannage](#dépannage).

**Vault** (gestion de secrets, mode dev) remplace les secrets en clair de
`.env`/`docker-compose.yml` pour toute la stack (API + Langfuse + Grafana).
Séquence de démarrage (voir `scripts/up.sh`) :

```
vault (sain) → vault-seed (pousse .env dans Vault, one-shot)
             → vault-agent (rend vault/rendered/secrets.env, one-shot)
             → api / langfuse-* / grafana (env_file: secrets.env rendu)
```

`src/config.py` et le code applicatif **n'ont pas changé** : chaque conteneur
continue de lire de simples variables d'environnement, sans savoir que Vault
existe — c'est Vault Agent qui les matérialise dans un fichier avant que ces
conteneurs démarrent (`vault/agent-config.hcl`, `vault/secrets.env.tpl`).

> **Dev-only** : `vault` tourne en `-dev` (stockage en mémoire, perdu à
> chaque `docker compose down -v`, token racine fixe `VAULT_DEV_ROOT_TOKEN`).
> Authentification par token statique plutôt que par AppRole, pour rester
> simple. Explicitement **non persistant, non adapté à un vrai déploiement**.

**Pourquoi deux invocations (`scripts/up.sh`) plutôt qu'un seul
`docker compose up -d`** — Compose résout le contenu d'un `env_file:` une
seule fois, au moment où il construit la configuration de *toute*
l'invocation, pas au moment où chaque conteneur démarre réellement (même
avec `depends_on: condition: service_completed_successfully`). Si l'API et
Vault Agent sont lancés dans le même appel, le fichier de secrets rendu
n'existe pas encore quand Compose prépare la configuration de l'API : elle
démarrerait avec des secrets vides. Deux invocations séparées évitent le
problème.

> Secrets serveur (`LANGFUSE_SALT`, `NEXTAUTH_SECRET`, `CLICKHOUSE_PASSWORD`,
> `GRAFANA_ADMIN_PASSWORD`...) : valeurs par défaut dans `.env.example`, **à
> remplacer** (voir `openssl rand -hex 32`) avant tout déploiement partagé —
> elles ne servent plus qu'à amorcer Vault (`vault_seed.py`), pas à être lues
> directement par les conteneurs.

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
`app_frontend.py` repasse sous 80 % — actuellement **~93 %**.

- `tests/` : tests unitaires (mocks LangChain/Groq/psycopg2/FAISS — aucun
  appel réseau réel), dont `tests/test_auth.py` (hash, JWT, rotation des
  refresh tokens) et `tests/test_app_frontend.py` qui utilise le framework
  officiel `streamlit.testing.v1.AppTest`.
- `test_api.py` : tests de contrat de l'API FastAPI, graphe mocké pour rester
  rapide et déterministe.
- `test_e2e.py` : scénario de bout en bout de la couche sécurité (login →
  `/chat` protégé → refresh refusé sur route ressource → rôle admin →
  rotation → logout → rate limiting), autonome (utilisateurs + refresh
  tokens en mémoire, graphe bouchonné — aucune dépendance Supabase/Groq/FAISS).
  Se lance seul (`uv run python test_e2e.py`) ou via `pytest` (aucune fonction
  `test_*` n'y est définie, donc rien n'est collecté ni exécuté par erreur
  pendant une suite `pytest` normale).
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
| `test` | Suite complète + seuil de couverture ≥ 80 %, puis le scénario `test_e2e.py` |
| `docs` | Régénère OpenAPI + diagramme, build Sphinx (`-W`, warnings = erreurs) |
| `docker-build` | Build de `Dockerfile.api` |
| `publish` | Sur push vers `main` uniquement, si tout est vert : build & push sur `ghcr.io/<repo>-api` (via `GITHUB_TOKEN`, aucun secret à configurer) |

### Endpoints API

> Les exemples ci-dessous utilisent `http://localhost:8000` (lancement
> `uvicorn` direct, sans Docker). Avec la stack Docker (`bash scripts/up.sh`),
> remplace par `http://api.horragor.localhost` (voir [Vault & Traefik](#vault--traefik-stack-locale)) —
> il n'y a plus de port direct.

```bash
# Santé (public, pas d'authentification)
curl http://localhost:8000/health

# Authentification — récupère un couple de tokens
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "streamlit-ui", "password": "TON_MOT_DE_PASSE_DE_SERVICE"}'
# → {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# Équivalent OAuth2 standard (form-urlencoded) — utilisé par le bouton Authorize de /docs
curl -X POST "http://localhost:8000/token" \
  -d "username=streamlit-ui&password=TON_MOT_DE_PASSE_DE_SERVICE"

# Question à l'agent (authentification requise)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"question": "Parle-moi de The Shining"}'

# Rafraîchir un access token expiré (rotation : l'ancien refresh_token est révoqué)
curl -X POST "http://localhost:8000/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'

# Déconnexion — révoque le refresh token courant
curl -X POST "http://localhost:8000/logout" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'

# Recharger l'index FAISS (réservé au rôle admin — 403 sinon)
curl -X POST "http://localhost:8000/admin/reload-index" \
  -H "Authorization: Bearer <access_token_admin>"

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
│   ├── auth.py                        # Authentification par Refresh Tokens (rôles, rotation, révocation)
│   ├── rate_limit.py                  # Rate limiting anti brute-force (/token, /auth/login)
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
├── migrations/                        # Tables auth (users + role, refresh_tokens) + seed comptes + vault_seed.py
├── monitoring/                        # Config Prometheus + provisioning Grafana
├── vault/                             # agent-config.hcl + secrets.env.tpl (Vault Agent) — rendered/ généré, gitignored
├── scripts/up.sh                      # Démarrage 2 phases (Vault -> reste de la stack)
├── tests/                             # Tests unitaires Partie 3 + sécurité
├── test_api.py                        # Tests de contrat API (auth, admin, durcissement inclus)
├── test_e2e.py                        # Scénario de bout en bout — couche sécurité, autonome
├── .github/workflows/ci.yml           # Pipeline CI/CD
├── docker-compose.yml                 # API + Vault + Traefik + Langfuse + Prometheus + Grafana + Uptime Kuma
├── Dockerfile.api                     # Image de l'API multi-agent (réutilisée par le service vault-seed)
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
| `api`/`langfuse-*`/`grafana` démarrent avec des secrets vides ou plantent au démarrage | Lancé avec `docker compose up -d` seul au lieu de `bash scripts/up.sh` sur un premier démarrage — voir [Vault & Traefik](#vault--traefik-stack-locale) |
| `http://api.horragor.localhost` (ou autre sous-domaine) ne répond pas, dashboard Traefik vide (`api/overview` ne liste que `api@internal`/`dashboard@internal`) | `docker compose logs traefik` — si tu vois en boucle `Failed to retrieve information of the docker client and server host`, Traefik n'arrive pas à joindre `/var/run/docker.sock` monté depuis le conteneur. **Diagnostiqué sur Docker Desktop 4.89 (Windows, WSL2)** : la VM interne (`docker-desktop`) n'a plus de fichier à ce chemin classique — le vrai socket de l'API vit à `/run/guest-services/docker.proxy.sock`, et le mécanisme de compatibilité censé rediriger l'un vers l'autre pour les conteneurs montés ne fonctionnait pas sur cette installation (même après avoir posé un lien symbolique manuel côté VM et recréé le conteneur). **Pas un défaut de `docker-compose.yml`** — le chemin `/var/run/docker.sock` est le standard portable partout ailleurs (Linux, Mac, CI), donc pas question de le coder en dur en `/run/guest-services/...` dans le fichier versionné. Piste à essayer en premier : **quitter et relancer Docker Desktop entièrement** (pas juste `docker compose down/up`) — remède standard pour ce type de souci de proxy interne. Le reste de la stack (Vault, API, Langfuse...) fonctionne normalement, seul le routing Traefik est affecté. |
| `vault-seed` ou `vault-agent` échoue | `docker compose logs vault-seed` / `vault-agent` — le plus souvent `vault` pas encore `healthy` (relance) ou `VAULT_TOKEN`/`VAULT_DEV_ROOT_TOKEN` incohérent entre les deux services |

---

## Branches de développement

| Branche | Développeur |
|---------|-------------|
| `main` | Production |
| `dev-tim` | Tim — Front-End Streamlit, architecture multi-agent, MLOps |
| `dev-nicolas` | Nicolas — FAISS + similarité |
| `dev_julie` | Julie — API FastAPI + Tools |

---

## Sécurité — bilan du projet final

Le cahier des charges de la semaine sécurité ([`projet-final-horragor.md`](projet-final-horragor.md))
verrouille l'accès à l'API multi-agent en 5 parties. Toutes sont faites,
prouvées par [`test_e2e.py`](test_e2e.py) (scénario complet, `uv run python test_e2e.py`)
et par les classes `TestAuthEndpoints` / `TestAdminEndpoints` / `TestHardening`
de [`test_api.py`](test_api.py) :

| Partie | Livrable | Statut |
|---|---|---|
| 1 — Authentification | `POST /token` (OAuth2 Password Grant) + `/auth/login`, mots de passe hachés (bcrypt), 401 + `WWW-Authenticate` | ✅ |
| 2 — Protéger le graphe | `require_auth` (algorithme imposé, refresh token refusé sur route ressource), `/chat` protégé avant tout appel de nœud, corps validé par Pydantic | ✅ |
| 3 — Refresh robuste | Rotation à usage unique (`/auth/refresh`) + révocation (`POST /logout`) | ✅ |
| 4 — Autorisation par rôle | `require_admin` (claim `role`), `POST /admin/reload-index` réservée à `role=admin` (403 sinon) | ✅ |
| 5 — Durcissement | `JWT_SECRET_KEY` fail-closed, rate limiting `/token`+`/auth/login` (429), CORS restreint, anti-énumération, journalisation Loguru des refus | ✅ |

Détail technique de chaque point : voir [Authentification — Refresh Tokens](#authentification--refresh-tokens)
ci-dessus.

**Hors périmètre de ce livrable** (items plus larges du cahier des charges
MLOps de la Partie 3, non couverts par `projet-final-horragor.md`) :
- **Couche Données** : base de données encapsulée derrière sa propre API,
  dans un réseau Docker privé **étanche** (inaccessible de l'extérieur).
- **Couche Présentation** : UI Streamlit conteneurisée, communication
  chiffrée vers l'API.
- **Gouvernance** : CI/CD étendu aux 3 couches, anomalies trackées en
  **GitHub Issues**.
