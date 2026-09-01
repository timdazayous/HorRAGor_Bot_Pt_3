"""
API FastAPI pour HorRAGor BOT
Composant Back-End : réception des messages Streamlit et traitement via le
graphe multi-agent LangGraph (Agent RAG → routeur → Agent Scraper → Agent de Narration)
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, ConfigDict, Field

from src import auth, config
from src.graph.pipeline import app as agent_graph
from src.logging_config import setup_logging
from src.rate_limit import enforce_login_rate_limit
from src.tools.rag_tool import initialize_retriever, reload_index

# ============================================================================
# CONFIGURATION
# ============================================================================

load_dotenv()
setup_logging()

# ============================================================================
# MONITORING LANGFUSE (optionnel — actif seulement si les clés sont configurées)
# ============================================================================

_langfuse_handler = None
if os.environ.get("LANGFUSE_PUBLIC_KEY"):
    from langfuse.langchain import CallbackHandler
    _langfuse_handler = CallbackHandler()
    logger.info("Monitoring Langfuse activé")
else:
    logger.info("Langfuse non configuré (LANGFUSE_PUBLIC_KEY absente) — monitoring désactivé")

# ============================================================================
# APPLICATION FASTAPI
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(initialize_retriever)
    logger.info("Retriever FAISS pré-chargé au démarrage")
    yield


app = FastAPI(
    title="HorRAGor BOT API",
    description="Agent conversationnel spécialisé dans l'univers de l'horreur",
    version="3.0.0",
    lifespan=lifespan
)

# ============================================================================
# MONITORING PROMETHEUS — latence/statut par route + métriques par agent
# (src/metrics.py) exposées sur GET /metrics
# ============================================================================

Instrumentator().instrument(app).expose(app, include_in_schema=False)

# ============================================================================
# CORS — restreint à l'origine de l'IHM Streamlit (jamais "*" avec credentials)
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.ALLOWED_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ============================================================================
# AUTHENTIFICATION — Refresh Tokens (verrouille les échanges IHM <-> API)
# ============================================================================

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    Dépendance FastAPI : exige un access token JWT valide (header
    Authorization: Bearer <token>). Lève 401 si absent, invalide ou expiré.
    """
    if credentials is None:
        raise HTTPException(
            status_code=401, detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return auth.decode_access_token(credentials.credentials)
    except auth.AuthError as e:
        logger.warning(f"[Auth] Token rejeté sur route protégée : {e}")
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"})


async def require_admin(identity: dict = Depends(require_auth)) -> dict:
    """
    Dépendance FastAPI : comme require_auth, mais exige en plus le rôle
    `admin` porté par le claim `role` de l'access token. Un utilisateur
    authentifié mais non-admin reçoit 403 (et non 401 : il est bien identifié,
    seulement pas autorisé).
    """
    if identity.get("role") != "admin":
        logger.warning(f"[Auth] Accès admin refusé pour {identity.get('sub')!r} (role={identity.get('role')!r})")
        raise HTTPException(status_code=403, detail="Rôle admin requis")
    return identity


# ============================================================================
# MODÈLES PYDANTIC
# ============================================================================


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChatRequest(BaseModel):
    """
    Requête utilisateur.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Quel film d'horreur me recommandes-tu si j'aime The Shining ?",
                "user_id": "user_123",
                "conversation_id": "conv_456"
            }
        }
    )

    question: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Question utilisateur"
    )

    user_id: Optional[str] = Field(
        default=None,
        description="Identifiant utilisateur"
    )

    conversation_id: Optional[str] = Field(
        default=None,
        description="Identifiant conversation"
    )

    history: list[dict] = Field(
        default_factory=list,
        description="Historique de la conversation (messages {role, content})"
    )


class ToolResult(BaseModel):
    """
    Résultat d'un outil.
    """

    tool_name: str
    status: str
    data: Optional[dict] = None
    error_message: Optional[str] = None


class JudgeVerdict(BaseModel):
    """
    Verdict qualité.
    """

    is_valid: bool

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0
    )

    reasoning: str


class ChatResponse(BaseModel):
    """
    Réponse du chatbot.
    """

    answer: str

    tools_used: list[str] = Field(
        default_factory=list
    )

    judge_verdict: Optional[JudgeVerdict] = None

    conversation_id: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Je te recommande The Haunting (1963).",
                "tools_used": ["groq-llm"],
                "judge_verdict": {
                    "is_valid": True,
                    "confidence": 0.95,
                    "reasoning": "Réponse cohérente et pertinente."
                },
                "conversation_id": "conv_456"
            }
        }
    )


class ErrorResponse(BaseModel):
    """
    Réponse d'erreur.
    """

    error: str
    detail: str
    request_id: Optional[str] = None


class ReloadIndexResponse(BaseModel):
    """
    Résultat du rechargement de l'index FAISS.
    """

    status: str = "reloaded"
    vector_count: int


# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get(
    "/",
    tags=["Root"]
)
async def root():
    """
    Endpoint racine.
    """

    return {
        "name": "HorRAGor BOT API",
        "version": "1.0.0",
        "status": "running"
    }


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["Auth"],
    summary="Authentification — émet une paire access/refresh token",
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(request: LoginRequest) -> TokenResponse:
    try:
        user = await asyncio.to_thread(auth.authenticate_user, request.username, request.password)
    except auth.AuthError:
        # Message identique, que le compte existe ou non (anti-énumération).
        logger.warning(f"[Auth] Échec de connexion pour {request.username!r} (/auth/login)")
        raise HTTPException(
            status_code=401,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = await asyncio.to_thread(
        auth.issue_token_pair, user["id"], user["username"], user.get("role", "user")
    )
    return TokenResponse(**tokens)


@app.post(
    "/token",
    response_model=TokenResponse,
    tags=["Auth"],
    summary="Login OAuth2 Password Grant (standard — alimente le bouton Authorize de /docs)",
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def token(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """
    Variante standard OAuth2 de /auth/login : identifiants transmis en
    `application/x-www-form-urlencoded` (champs `username`/`password`) plutôt
    qu'en JSON. Même logique métier, exposée pour les clients OAuth2 (Swagger
    UI, outils standards) qui s'attendent à ce chemin et ce format précis.
    """
    try:
        user = await asyncio.to_thread(auth.authenticate_user, form_data.username, form_data.password)
    except auth.AuthError:
        logger.warning(f"[Auth] Échec de connexion pour {form_data.username!r} (/token)")
        raise HTTPException(
            status_code=401,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = await asyncio.to_thread(
        auth.issue_token_pair, user["id"], user["username"], user.get("role", "user")
    )
    return TokenResponse(**tokens)


@app.post(
    "/auth/refresh",
    response_model=TokenResponse,
    tags=["Auth"],
    summary="Rafraîchit un access token à partir d'un refresh token (rotation à usage unique)",
)
async def refresh(request: RefreshRequest) -> TokenResponse:
    try:
        identity = await asyncio.to_thread(auth.validate_and_rotate_refresh_token, request.refresh_token)
    except auth.AuthError as e:
        logger.warning(f"[Auth] Refresh token invalide/révoqué présenté ({e})")
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"})

    tokens = await asyncio.to_thread(
        auth.issue_token_pair, identity["user_id"], identity["username"], identity.get("role", "user")
    )
    return TokenResponse(**tokens)


@app.get(
    "/health",
    tags=["Health"]
)
async def health_check():
    """
    Vérification de santé.
    """

    return {
        "status": "ok",
        "message": "HorRAGor BOT API is running"
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Requête invalide"
        },
        401: {
            "model": ErrorResponse,
            "description": "Authentification manquante, invalide ou expirée"
        },
        500: {
            "model": ErrorResponse,
            "description": "Erreur serveur"
        }
    },
    tags=["Chat"],
    summary="Génération de réponse (authentification requise)"
)
async def chat(request: ChatRequest, _identity: dict = Depends(require_auth)) -> ChatResponse:
    """
    Reçoit une question et la fait traverser le graphe multi-agent
    (Agent RAG → routeur → [Agent Scraper] → Agent de Narration).
    """

    try:
        logger.info(
            f"Question reçue : {request.question[:100]}"
        )

        history_messages = [
            AIMessage(content=m["content"]) if m.get("role") == "assistant"
            else HumanMessage(content=m["content"])
            for m in request.history
        ]

        initial_state = {
            "messages": [*history_messages, HumanMessage(content=request.question)],
            "user_query": request.question,
            "retry_count": 0,
            "tools_used": [],
        }

        invoke_config = {"callbacks": [_langfuse_handler]} if _langfuse_handler else {}
        result = await asyncio.to_thread(agent_graph.invoke, initial_state, invoke_config)

        logger.info(
            f"Réponse générée ({len(result['final_answer'])} caractères) "
            f"— agents : {result['tools_used']}"
        )

        conversation_id = (
            request.conversation_id
            or f"conv_{request.user_id or 'anonymous'}"
        )

        raw_verdict = result.get("judge_verdict")
        verdict = JudgeVerdict(
            is_valid=raw_verdict.get("is_valid", True),
            confidence=raw_verdict.get("confidence", 0.75),
            reasoning=raw_verdict.get("reasoning", "")
        ) if raw_verdict else None

        return ChatResponse(
            answer=result["final_answer"],
            tools_used=result["tools_used"],
            judge_verdict=verdict,
            conversation_id=conversation_id
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Erreur inattendue")

        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la génération : {str(e)}"
        )


@app.post(
    "/admin/reload-index",
    response_model=ReloadIndexResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentification manquante, invalide ou expirée"},
        403: {"model": ErrorResponse, "description": "Rôle admin requis"},
    },
    tags=["Admin"],
    summary="Recharge l'index FAISS depuis le disque (réservé au rôle admin)",
)
async def admin_reload_index(_identity: dict = Depends(require_admin)) -> ReloadIndexResponse:
    """
    Recharge l'index FAISS + id_map depuis `data/faiss_index/` sans redémarrer
    l'API — utile après un ré-enrichissement du catalogue de films.
    """
    vector_count = await asyncio.to_thread(reload_index)
    return ReloadIndexResponse(vector_count=vector_count)


@app.get(
    "/info",
    tags=["Info"],
    summary="Informations système"
)
async def get_info():
    """
    Informations sur le service.
    """
    return {
        "agent": "HorRAGor BOT",
        "version": "3.0.0",
        "architecture": "multi-agent (LangGraph)",
        "llm": {
            "provider": "Groq",
            "model": config.GROQ_MODEL,
            "status": "connected" if config.GROQ_API_KEY else "not_configured"
        },
        "agents": [
            "rag_agent (Le Chercheur Local)",
            "scraper_agent (L'Enquêteur du Web) — conditionnel",
            "narration_agent (L'Écrivain Gothique)",
            "judge_agent (Le Juge) — boucle de retry si réponse rejetée"
        ],
        "models": {
            "request": "ChatRequest",
            "response": "ChatResponse",
            "judge_verdict": "JudgeVerdict"
        }
    }


# ============================================================================
# LANCEMENT LOCAL
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )