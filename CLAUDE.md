# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**HorRAGor BOT**, an horror-themed conversational agent, built in three successive parts (see README.md for the full history):

- **Partie 1** (done, stable): data ingestion pipeline (`app/`, `main.py`, `tools/`) — 1179 horror movies merged from TMDB/Rotten Tomatoes/Kaggle/IMDB/PySpark into Supabase (PostgreSQL). Not touched by current work.
- **Partie 2** (done, superseded): monolithic ReAct agent (`llm_groq.py`). Kept in the repo for reference, no longer invoked by the running API.
- **Partie 3** (current focus): the code under `src/` — a LangGraph multi-agent architecture replacing the Partie 2 monolith, plus the MLOps stack (Langfuse/Prometheus/Grafana/Uptime Kuma monitoring, Sphinx docs, CI/CD, pytest coverage ≥80%). This is what `src/main.py` actually serves.
- **Security layer** (all 5 parts done): `projet-final-horragor.md` is a separate, more detailed brief for hardening the API's auth (OAuth2 `/token`, role-based authorization, rotation/revocation, rate limiting, CORS, fail-closed secrets). Work is tracked part-by-part directly against `src/auth.py` and `src/main.py` — not a rewrite into the `security.py`/`store.py` files the brief suggests as indicative names, since `src/auth.py` already owns that responsibility. Implemented: `users.role` + role claim in the JWT + `POST /token` OAuth2 endpoint (Partie 1), `require_auth` proven to reject refresh tokens/alg-confusion on resource routes, `ChatRequest` Pydantic-validated (Partie 2), refresh rotation (pre-existing) + `POST /logout` revocation (Partie 3 — this endpoint was a real gap, added after the fact), `require_admin` + `POST /admin/reload-index` (Partie 4), fail-closed `JWT_SECRET_KEY` + rate-limited `/token`+`/auth/login` (`src/rate_limit.py`) + restricted CORS (`ALLOWED_ORIGIN`) + refusal logging (Partie 5). `test_e2e.py` runs the brief's full 8-step scenario standalone (in-memory user store, stubbed graph) — `uv run python test_e2e.py`.

Two brief documents describe what Partie 3 asked for: `Contexte_Part_3_V2.md` (official brief text) and `Plan_Part_3_V1.md` (the original migration plan from the Partie 2 monolith). `projet-final-horragor.md` is the security brief.

**Fail-closed gotcha**: `src/config.py` raises `RuntimeError` at import time if `JWT_SECRET_KEY` is unset — any script/test that imports `src.config` (directly or transitively via `src.auth`/`src.main`) needs that env var present. Locally `.env` covers it; CI sets a dummy value explicitly in the `test` and `docs` jobs (`.github/workflows/ci.yml`) — remember to do the same for any new job that imports the app.

## Commands

```bash
uv sync                                          # install dependencies

# Run the API / UI (no Docker)
uvicorn src.main:app --reload                    # API on :8000, Swagger at /docs
streamlit run app_frontend.py                    # UI on :8501

# Full stack with monitoring + Vault + Traefik (fresh start / after `docker compose down -v`)
bash scripts/up.sh                               # API + Langfuse + Prometheus + Grafana + Uptime Kuma, routed via *.horragor.localhost
docker compose up -d                             # subsequent restarts only — needs vault/rendered/secrets.env already on disk

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

### Auth (`src/auth.py` + `src/rate_limit.py`, wired into `src/main.py`)

- Access token: JWT (HS256, `pyjwt`), short-lived (~30 min), stateless — never persisted server-side, just decoded and validated on each request via the `require_auth` FastAPI dependency (imposes `algorithms=["HS256"]` explicitly — rejects `alg=none` and any refresh token, since those aren't valid `type=access` JWTs).
- Refresh token: opaque random string; only its SHA-256 hash is stored in the `refresh_tokens` table. Single-use rotation on `POST /auth/refresh` — every refresh revokes the old one and issues a new pair. `POST /logout` revokes a specific refresh token on demand (`auth.revoke_refresh_token`, idempotent). Opaque + hashed is stronger than a JWT-based refresh token because the server can actually invalidate it before expiry.
- Both tokens carry a `role` claim (`user` default, `admin`) — added to `users.role` and threaded through login/refresh/rotation so role-gated routes don't force a re-login. `require_admin` (built on `require_auth`) checks it and returns 403 (not 401) for an authenticated non-admin. `POST /admin/reload-index` is the one admin-gated route so far — reloads the FAISS index from disk (`rag_tool.reload_index`) without restarting the API.
- `POST /auth/login` (JSON) is what the Streamlit UI uses; `POST /token` (OAuth2 `application/x-www-form-urlencoded`, `OAuth2PasswordRequestForm`) is the standards-compliant equivalent that feeds the Swagger "Authorize" button. Same underlying logic (`auth.authenticate_user` + `auth.issue_token_pair`), different request shape — don't let them drift apart.
- `src/rate_limit.py`: in-memory sliding-window limiter keyed by `(client IP, route path)`, applied to `/token` and `/auth/login` independently (`Depends(enforce_login_rate_limit)`) — 429 past `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` per `RATE_LIMIT_LOGIN_WINDOW_SECONDS`. Single-process only (no Redis); state must be reset between tests (`rate_limit.reset()` — see the `reset_rate_limiter` autouse fixture in `test_api.py`) or attempts leak across unrelated test cases.
- `config.JWT_SECRET_KEY` is fail-closed: `src/config.py` raises `RuntimeError` at import time if it's unset, no silent default.
- Only one production user actually exists in practice: `streamlit-ui`, a single service account the UI authenticates as silently (no login screen). `demo-user`/`demo-admin` (via `migrations/seed_demo_users.py`) exist purely to exercise role-based authorization in tests/manual checks.
- Password hashing uses `bcrypt` directly (not `pwdlib`, despite `projet-final-horragor.md` naming it) — already in place, already tested, functionally equivalent for the brief's requirement ("hashed, never plaintext").

### State/DB layout

Supabase (Postgres) hosts both the Partie 1 movie data (`film`, `genre`, `film_genre`, `evaluation`, `analyse_spark`, `source` — see `Merise.md`) and the Partie 3 auth tables (`users`, `refresh_tokens` — see `migrations/`). Same database, two unrelated concerns sharing infrastructure.

### Local Docker stack — Vault + Traefik (learning exercise, not production)

`docker-compose.yml` also runs HashiCorp Vault (dev mode) and Traefik, added purely to learn the tools (course-driven, not a project requirement) — see the "Vault & Traefik" section of README.md for the full picture. Key points if you touch this:

- **Application code (`src/`) does not know Vault exists.** Vault Agent (`vault-agent` service, one-shot, `exit_after_auth = true`) renders `vault/secrets.env.tpl` into `vault/rendered/secrets.env` (gitignored), and every secret-consuming service (`api`, `langfuse-*`, `grafana`) reads it via a plain `env_file:` entry — same as any other env var. `src/config.py`'s fail-closed checks are unmodified and still the only real guard.
- **Startup is two Compose invocations, not one** (`scripts/up.sh`): Compose resolves `env_file:` content once, when it builds the config for *all* services in a single `up` call — not lazily per-container respecting `depends_on`. Verified empirically (a fresh `docker compose up` run shows a `depends_on: condition: service_completed_successfully`-gated consumer still getting an empty env var from a file its dependency wrote moments earlier in the *same* invocation). So `scripts/up.sh` runs `docker compose up vault-agent` (blocks until Vault → seed → render completes) *then* `docker compose up -d` (now the file already exists on disk before this second invocation parses configs). A plain `docker compose up -d` only works once `vault/rendered/secrets.env` already exists from a prior run.
- Real Vault secret paths (`secret/horragor/api`, `secret/horragor/langfuse`, `secret/horragor/monitoring`) are seeded by `migrations/vault_seed.py` (one-shot `vault-seed` service, reuses `Dockerfile.api`'s image — that Dockerfile now also `COPY migrations/`) from the plaintext values still sitting in `.env` — `.env` is the bootstrap source, Vault becomes canonical after that.
- The Vault Agent template's output variable names (`SALT`, `GF_SECURITY_ADMIN_PASSWORD`, `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY`, ...) intentionally match each third-party image's *actual* expected env var name, not a "friendly" name — check `docker-compose.yml`'s original `${VAR:-default}` substitutions before renaming anything in `vault/secrets.env.tpl`.
- `langfuse-redis`'s password can't come from `env_file` the normal way — Redis needs it as a `--requirepass` CLI arg, so the service uses `entrypoint: sh` + `command: -c 'redis-server --requirepass "$$REDIS_AUTH" ...'` (the `$$` escapes Compose's own interpolation so the container's shell expands it from its real env at runtime, not Compose at parse time).
- All of `traefik`/`vault`/`vault-seed`/`vault-agent` and every proxied service's Traefik `labels:` are dev-only shortcuts (`--api.insecure=true` dashboard, HTTP-only entrypoint, Vault `-dev` in-memory storage with a fixed root token) — flagged as such in the README, don't carry these patterns into anything resembling production without hardening them first.
- **Verified end-to-end on this machine (Docker Desktop, Windows)**: the Vault chain (vault → vault-seed → vault-agent → all secret-consuming containers, including the `$$REDIS_AUTH` escaping) works exactly as designed — confirmed by actually running `docker compose up vault-agent` then `docker compose up -d` and inspecting the rendered `secrets.env`, container logs, and a `redis-cli` auth check. Traefik's routing could *not* be verified the same way: its Docker-socket provider fails with `Failed to retrieve information of the docker client and server host`. Root-caused (not just observed) by inspecting Docker Desktop's internal `docker-desktop` WSL2 distro directly (`wsl -d docker-desktop`): on this install (Docker Desktop 4.89), `/var/run/docker.sock` genuinely doesn't exist inside that VM anymore — the real engine socket lives at `/run/guest-services/docker.proxy.sock`, and whatever compatibility shim is supposed to bridge the classic path to that one isn't working here. Manually symlinking `/var/run/docker.sock -> /run/guest-services/docker.proxy.sock` inside the VM let a plain `docker run -v /var/run/docker.sock:...` reach the real socket (got a permission-denied from a non-root client, a valid Docker API response as root) — but a `docker compose`-created `traefik` container, even force-recreated *after* the symlink existed, still saw the old dead placeholder. So Docker Desktop appears to manage that exact path specially (independent of the VM's real filesystem state), not something fixable from outside its own internals. **Not a `docker-compose.yml` bug** — `/var/run/docker.sock` is correct, portable, and works everywhere else (Linux, Mac, CI); don't hardcode the Windows-internal `guest-services` path into the committed compose file. Next thing to try if this recurs: fully quit and restart Docker Desktop (not just the containers).

### Observability

`src/metrics.py` instruments every graph node individually (latency, Groq token usage) exposed on `/metrics` for Prometheus/Grafana. Langfuse tracing is optional — wired via a `CallbackHandler` on the graph's `invoke()` call in `src/main.py`, only active when `LANGFUSE_PUBLIC_KEY` is set; its absence must not break the API. `src/logging_config.py` intercepts all logging (including third-party libs) into Loguru, one unified format.

### Testing conventions

No real network calls in `tests/` or `test_api.py` — Groq/LangChain, psycopg2, and FAISS are always mocked (see `FakeCursor`/`FakeConnection` pattern in `tests/test_auth.py`, reused in `tests/test_rag_tool.py`). `test_api.py` mocks the compiled graph itself to keep API contract tests fast and deterministic. `tests/test_app_frontend.py` uses Streamlit's official `streamlit.testing.v1.AppTest` framework rather than mocking internals.

`test_e2e.py` is a standalone script (not a pytest suite) proving the security brief's 8-step scenario end to end against the real endpoints, with its own in-memory `InMemoryAuthStore` standing in for Supabase and the graph stubbed out. All its logic lives inside `run_scenario()`, gated by `if __name__ == "__main__"` — pytest still collects the file (name matches `test_*.py`) but finds no `test_*` function in it, so nothing runs and nothing gets globally monkey-patched during a normal `pytest` run. If you add scenario steps, keep that guard: module-level side effects here would leak into the rest of the suite.

`ty` (Astral's type checker) is a dev dependency, requested by `projet-final-horragor.md`, but **not wired into CI** — `uv run ty check src/` currently flags ~15 pre-existing diagnostics in `src/graph/nodes.py`, `src/graph/pipeline.py`, `src/tools/rag_tool.py`, and the `/chat` handler in `src/main.py` (LangGraph's generic `invoke()` return type is a wide union `ty` can't narrow, plus a `sentence-transformers` Tensor-vs-ndarray stub mismatch). The auth/security files (`src/auth.py`, `src/config.py`, `src/rate_limit.py`, the `/token`/`/logout`/`/admin` endpoints) are clean. Fixing the graph-side diagnostics is a separate task, not security work.

## Working across the two active tracks

Changes to the multi-agent graph (nodes/router/pipeline/tools) and changes to the security layer (auth/main endpoints) are largely independent — the security brief explicitly scopes itself to auth only ("le graphe multi-agent... est votre travail par ailleurs"). Don't let a security-focused session touch `src/graph/` or `src/tools/`, and don't let a graph-focused session touch `src/auth.py` beyond what's needed to keep `require_auth` working.
