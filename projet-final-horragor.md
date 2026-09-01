# Projet final — Sécuriser HorRAGor (Partie 3)

**Durée estimée : 2 heures et plus**
**Objectif :** appliquer *tout* ce qui a été vu dans cette formation à votre propre projet
**HorRAGor Partie 3** — le cluster multi-agent LangGraph. On ne réimplémente pas le graphe :
**on le verrouille.**

---

## Contexte

Votre HorRAGor Partie 3 expose son graphe multi-agent derrière une API FastAPI. L'architecture,
les nœuds, le routeur et le monitoring Langfuse sont décrits dans **vos consignes de projet** :
on ne les reprend pas ici.

Ce qui nous concerne, c'est ce que l'**épilogue MLOps** exige noir sur blanc :

> « Pour sécuriser l'accès depuis l'extérieur, vous implémenterez un système d'authentification
> robuste par **Refresh Tokens** pour verrouiller les échanges avec l'IHM. »

C'est exactement ce que vous venez d'apprendre. **Ce projet, c'est ce livrable-là.**

> **Périmètre de l'évaluation** : seule la **couche sécurité** est notée. Le graphe multi-agent
> (nœuds, routeur, pipeline) est votre travail par ailleurs. Si votre graphe n'est pas encore
> prêt, remplacez-le par une fonction bouchon qui renvoie un texte : la sécurité se teste
> parfaitement sans Ollama ni FAISS.

---

## Prérequis

```bash
uv sync   # installe tout le kit (dépendances déclarées dans pyproject.toml)
```

---

## Ce que vous ajoutez

Trois fichiers à créer à côté de votre code existant (les noms sont indicatifs) :

| Fichier | Rôle |
|---|---|
| `security.py` | hachage des mots de passe + création / lecture des JWT |
| `auth.py` | dépendances `get_current_user` (401) et `require_admin` (403) |
| `store.py` | les `jti` des refresh tokens encore valides (rotation / révocation) |

Plus deux retouches : `config.py` (lire `SECRET_KEY` et les durées de vie depuis `.env`) et
`main.py` (brancher les dépendances sur les endpoints).

> **Le graphe n'est pas modifié.** `nodes.py`, `router.py`, `pipeline.py`, les outils et le
> monitoring restent tels quels : on ajoute une serrure, on ne refait pas la maison.

---

## Cahier des charges

### Partie 1 — Authentification (30 min)

- Base d'utilisateurs (en mémoire suffit) avec **au moins 2 comptes** : un `user` et un `admin`.
  Mots de passe **hachés** avec `pwdlib` (bcrypt) — jamais en clair.
- `POST /token` : login **OAuth2 Password Grant** (`OAuth2PasswordRequestForm`) qui renvoie
  un **access token** (court, ~15 min) **et** un **refresh token** (long, ~7 jours).
- Échec d'authentification → **401** avec l'en-tête `WWW-Authenticate: Bearer`.
- Les deux jetons se distinguent par un claim `type` (`"access"` / `"refresh"`).

### Partie 2 — Protéger le graphe (25 min)

- Dépendance `get_current_user` : décode le token, **impose l'algorithme**
  (`algorithms=["HS256"]`), vérifie l'expiration, et **refuse un refresh token**
  présenté sur une route de ressource.
- L'endpoint qui invoque le graphe (`POST /invoke`, `/chat`, peu importe le nom) devient
  **protégé** : sans token valide → **401**, avant même d'exécuter le moindre nœud.
- Le corps de la requête est validé par un **modèle Pydantic** (pas de `dict` brut).

### Partie 3 — Refresh robuste : rotation + révocation (35 min)

- `POST /refresh` : échange un refresh token valide contre un **nouvel access token ET un
  nouveau refresh token** (= **rotation**). L'ancien devient **inutilisable**.
- `POST /logout` : **révoque** le refresh token courant.
- Mécanisme : un `jti` unique par refresh token + un ensemble des `jti` encore valides côté
  serveur. Un `jti` absent ou inconnu → 401.

### Partie 4 — Autorisation par rôle (20 min)

Tout le monde ne fait pas tout sur un cluster d'agents :

- `POST /invoke` (interroger le graphe) → **tout utilisateur authentifié**.
- Route d'administration — au choix : recharger l'index FAISS, consulter les traces/coûts
  Langfuse, ou lister les utilisateurs → **réservée au rôle `admin`**.
- Un `user` qui appelle une route admin reçoit **403** (et non 401 : il est authentifié).

### Partie 5 — Durcissement (25 min)

- `SECRET_KEY` et durées de vie lues depuis l'**environnement** (`.env`), avec un
  `.env.example` fourni. L'application **refuse de démarrer** si la clé est absente
  (*fail-closed*) — pas de clé par défaut silencieuse.
- **Rate limiting** sur `/token` (anti-brute-force) → 429 au-delà du quota.
- **CORS** restreint à l'origine de l'IHM Streamlit (jamais `*` avec des credentials).
- **Anti-énumération** : message d'erreur identique que le compte existe ou non.
- **Journalisation avec `loguru`** de toute tentative refusée (login échoué, token invalide,
  403), sans jamais écrire le mot de passe ni le token.

---

## Test de bout en bout attendu

Écrivez un `test_e2e.py` (avec le `TestClient` de FastAPI) qui prouve le scénario complet :

1. Login `user` → access + refresh.
2. `POST /invoke` avec l'access → **200** (réponse du graphe, même bouchonné).
3. `POST /invoke` sans token → **401**.
4. `POST /invoke` en présentant le **refresh** token → **401**.
5. Route admin avec le token `user` → **403** ; après login `admin` → **200**.
6. `POST /refresh` → nouveaux jetons ; rejouer l'**ancien** refresh → **401** (rotation).
7. `POST /logout` → le refresh courant ne fonctionne plus.
8. Marteler `/token` avec de mauvais identifiants → **429** au-delà du quota.

```bash
uv run python test_e2e.py
```

---

## Qualité de code (exigée)

Le code doit passer les deux outils du kit, sans erreur :

```bash
uv run ruff check .        # linter
uv run ruff format .       # formateur
uv run ty check            # types
```

---

## Grille d'évaluation (sur 20)

| Critère | Points |
|---|---|
| `POST /token` fonctionne (bons identifiants → 2 jetons, mauvais → 401) | 3 |
| Mots de passe **hachés** (jamais en clair) | 2 |
| Endpoint du graphe **protégé** (401 sans token, refresh refusé dessus) | 3 |
| `POST /refresh` délivre un nouvel access token | 2 |
| **Rotation** du refresh (l'ancien devient invalide) | 2 |
| **Révocation** au logout fonctionnelle | 2 |
| Rôle **admin** exigé sur la route d'administration (403 pour un `user`) | 2 |
| `SECRET_KEY` via environnement + **fail-closed** au démarrage | 1 |
| Durcissement : rate limiting, CORS restreint, anti-énumération | 1 |
| Journalisation `loguru` des accès refusés | 1 |
| Test de bout en bout qui passe + `ruff`/`ty` propres | 1 |
| **Total** | **20** |

### Bonus (jusqu'à +3, hors barème)

- **Détection de réutilisation** des refresh tokens (familles + révocation en cascade) — atelier 4.
- **Scopes** OAuth2 (`OAuth2PasswordBearer(scopes=...)`) plutôt qu'un simple champ rôle.
- **Quota d'invocations par utilisateur** : un appel au graphe coûte du CPU/GPU et des tokens LLM.
- Remplacer le Password Grant par **Authorization Code + PKCE** (le flux recommandé en OAuth 2.1).

---

## Aide

- **Corrigé de ce projet** : `corriges/projet-horragor-securite/` — la couche sécurité complète,
  avec le graphe réduit à un bouchon (donc testable sans Ollama ni FAISS) et un `test_e2e.py`
  qui déroule les 8 étapes ci-dessus. *À garder pour la correction.*
- **Exemple de référence complet et corrigé** : `corriges/exemple-api-ia-securisee/` — une API
  qui sert un modèle IA avec exactement cette couche de sécurité. L'architecture `auth.py` /
  `security.py` / `store.py` y est directement transposable.
- Ateliers de renfort : `atelier-5-durcissement.md` (rate limiting, CORS, anti-énumération) et
  `atelier-6-serving-ia.md` (protéger un endpoint de serving, quotas).
- En cas de doute sur un terme : `ressources/glossaire.md`.
