# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**HorRAGor BOT**, an horror-themed conversational agent, built in three successive parts (see README.md for the full history):

- **Partie 1** (done, stable): data ingestion pipeline (`app/`, `main.py`, `tools/`) — 1179 horror movies merged from TMDB/Rotten Tomatoes/Kaggle/IMDB/PySpark into Supabase (PostgreSQL). Not touched by current work.
- **Partie 2** (done, superseded): monolithic ReAct agent (`llm_groq.py`). Kept in the repo for reference, no longer invoked by the running API.
- **Partie 3** (current focus): the code under `src/` — a LangGraph multi-agent architecture replacing the Partie 2 monolith, plus the MLOps stack (Langfuse/Prometheus/Grafana/Uptime Kuma monitoring, Sphinx docs, CI/CD, pytest coverage ≥80%). This is what `src/main.py` actually serves.
- **Security layer** (Parties 1–4 done, Partie 5 done): `projet-final-horragor.md` is a separate, more detailed brief for hardening the API's auth (OAuth2 `/token`, role-based authorization, rate limiting, CORS, fail-closed secrets). Work is tracked part-by-part directly against `src/auth.py` and `src/main.py` — not a rewrite into the `security.py`/`store.py` files the brief suggests as indicative names, since `src/auth.py` already owns that responsibility. Implemented: `users.role` + role claim in the JWT (Partie 1), `require_auth` proven to reject refresh tokens/alg-confusion on resource routes (Partie 2), rotation+revocation (Partie 3, pre-existing), `require_admin` + `POST /admin/reload-index` (Partie 4), fail-closed `JWT_SECRET_KEY` + rate-limited `/token`/`/auth/login` (`src/rate_limit.py`) + restricted CORS (`ALLOWED_ORIGIN`) + refusal logging (Partie 5).

Two brief documents describe what Partie 3 asked for: `Contexte_Part_3_V2.md` (official brief text) and `Plan_Part_3_V1.md` (the original migration plan from the Partie 2 monolith). `projet-final-horragor.md` is the security brief.

**Fail-closed gotcha**: `src/config.py` raises `RuntimeError` at import time if `JWT_SECRET_KEY` is unset — any script/test that imports `src.config` (directly or transitively via `src.auth`/`src.main`) needs that env var present. Locally `.env` covers it; CI sets a dummy value explicitly in the `test` and `docs` jobs (`.github/workflows/ci.yml`) — remember to do the same for any new job that imports the app.

## Commands

```bash
uv sync                                          # install dependencies

# Run the API / UI (no Docker)
uvicorn src.main:app --reload                    # API on :8000, Swagger at /docs
streamlit run app_frontend.py                    # UI on :8501

# Full stack with monitoring
docker compose up -d                             # API (:8020) + Langfuse + Prometheus + Grafana + Uptime Kuma

# Tests
uv run pytest                                    # full suite, coverage gate at 80% (currently ~93%)
uv run pytest tests/test_auth.py                 # single file
uv run pytest tests/test_auth.py::TestAccessToken::test_roundtrip -q   # single test
uv run pytest -k "refresh"                       # by keyword
uv run python test_e2e.py                        # standalone security scenario (login->chat->refresh->admin->logout->rate-limit), no real DB/LLM needed

# Quality gates (all required by CI)
uv run ruff check src/ tests/ test_api.py test_e2e.py app_frontend.py
uv run sphinx-build -b html docs/source docs/build -W   # warnings fail the build

# Docs regeneration (must run before a Sphinx build if the graph or API shape changed)
uv run python docs/generate_openapi.py
uv run python docs/generate_graph_diagram.py

# DB migrations (Supabase/Postgres) — plain .sql files applied alphabetically, idempotent
uv run python migrations/apply_migrations.py
uv run python migrations/seed_service_account.py   # streamlit-ui service account
uv run python migrations/seed_demo_users.py        # demo-user / demo-admin (role testing)
```

Note: `uv run ruff check .` (whole repo, no path filter) will surface pre-existing lint/format issues in `app/`, `tools/`, `utils/`, and Partie 1/2 legacy code that CI does not check and that are out of scope for Partie 3 / security work — only `src/`, `tests/`, `test_api.py`, `app_frontend.py` are the CI-enforced surface.

## Architecture

### The graph (`src/graph/`)

Four LangGraph nodes share one `AgentState` (`src/models/state.py`, a `TypedDict`) that is merged incrementally at each node — never overwritten:

```
START → rag ──(complet)────────────→ narration ⇄ judge ──(satisfaisant/épuisé)──→ END
         │                               ↑           │(rejeté, retries restants)
         └─(incomplet)→ scraper ─────────┘           └────────────────┘
```

- `rag_node` (`src/graph/nodes.py`) — first stop. Classifies the user's question via an LLM call (temperature=0, strict classifier prompt) into one of 6 intents: `TITRE`, `THEME`, `SURVIE`, `AGE`, `SIMILAIRE`, `ANECDOTES`. Each intent maps to a dedicated function in `src/tools/rag_tool.py`. `ANECDOTES` sets `force_scrape=True` on the state to force the Scraper even when the local data is already complete — this is a separate field from `rag_complete` specifically so `rag_complete` keeps its literal meaning ("is the local data actually incomplete?") for the router.
- `scraper_node` — conditional, triggered when RAG is incomplete OR `force_scrape` is set. Live Wikipedia lookup (`src/tools/scraper_tool.py`).
- `narration_node` — deliberately isolated from all technical plumbing (context trimming): receives only the factual synthesis, never raw tool logs or tool names. Switches to a dedicated survival-simulator prompt format when `is_survival_mode` is set.
- `judge_node` — evaluates the final answer against the factual dossier; triggers a bounded number of narration retries (`JUDGE_MAX_RETRIES`) if confidence is too low. The retry budget strictly decreases, which is what guarantees the graph terminates.

`src/graph/router.py` holds the two conditional-edge functions (`should_scrape_or_narrate`, `should_retry_or_end`) — this is the only place routing decisions are made; nodes never decide their own successor.

`src/graph/pipeline.py` assembles and compiles the `StateGraph`. The Sphinx docs' graph diagram is generated from this compiled graph (`docs/generate_graph_diagram.py`), never hand-drawn — regenerate it whenever nodes/edges change.

### Auth (`src/auth.py`, wired into `src/main.py`)

- Access token: JWT (HS256, `pyjwt`), short-lived (~30 min), stateless — never persisted server-side, just decoded and validated on each request via the `require_auth` FastAPI dependency.
- Refresh token: opaque random string; only its SHA-256 hash is stored in the `refresh_tokens` table. Single-use rotation — every refresh revokes the old one and issues a new pair. This is stronger than a JWT-based refresh token because the server can actually invalidate it.
- Both tokens carry a `role` claim (`user` default, `admin`) — added to `users.role` and threaded through login/refresh/rotation so future role-gated routes don't force a re-login.
- `POST /auth/login` (JSON) is what the Streamlit UI uses; `POST /token` (OAuth2 `application/x-www-form-urlencoded`, `OAuth2PasswordRequestForm`) is the standards-compliant equivalent that feeds the Swagger "Authorize" button. Same underlying logic (`auth.authenticate_user` + `auth.issue_token_pair`), different request shape — don't let them drift apart.
- Only one production user actually exists in practice: `streamlit-ui`, a single service account the UI authenticates as silently (no login screen). `demo-user`/`demo-admin` (via `migrations/seed_demo_users.py`) exist purely to exercise role-based authorization in tests/manual checks.
- Password hashing uses `bcrypt` directly (not `pwdlib`, despite `projet-final-horragor.md` naming it) — already in place, already tested, functionally equivalent for the brief's requirement ("hashed, never plaintext").

### State/DB layout

Supabase (Postgres) hosts both the Partie 1 movie data (`film`, `genre`, `film_genre`, `evaluation`, `analyse_spark`, `source` — see `Merise.md`) and the Partie 3 auth tables (`users`, `refresh_tokens` — see `migrations/`). Same database, two unrelated concerns sharing infrastructure.

### Observability

`src/metrics.py` instruments every graph node individually (latency, Groq token usage) exposed on `/metrics` for Prometheus/Grafana. Langfuse tracing is optional — wired via a `CallbackHandler` on the graph's `invoke()` call in `src/main.py`, only active when `LANGFUSE_PUBLIC_KEY` is set; its absence must not break the API. `src/logging_config.py` intercepts all logging (including third-party libs) into Loguru, one unified format.

### Testing conventions

No real network calls in `tests/` or `test_api.py` — Groq/LangChain, psycopg2, and FAISS are always mocked (see `FakeCursor`/`FakeConnection` pattern in `tests/test_auth.py`, reused in `tests/test_rag_tool.py`). `test_api.py` mocks the compiled graph itself to keep API contract tests fast and deterministic. `tests/test_app_frontend.py` uses Streamlit's official `streamlit.testing.v1.AppTest` framework rather than mocking internals.

## Working across the two active tracks

Changes to the multi-agent graph (nodes/router/pipeline/tools) and changes to the security layer (auth/main endpoints) are largely independent — the security brief explicitly scopes itself to auth only ("le graphe multi-agent... est votre travail par ailleurs"). Don't let a security-focused session touch `src/graph/` or `src/tools/`, and don't let a graph-focused session touch `src/auth.py` beyond what's needed to keep `require_auth` working.
