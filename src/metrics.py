"""
Métriques Prometheus du graphe multi-agent.

Complète les métriques HTTP standards (prometheus-fastapi-instrumentator, câblées
dans main.py) avec une vue par agent : latence d'exécution, nombre d'appels et
tokens consommés — la boîte noire que dénonçait la QA devient inspectable.
"""
from functools import wraps

from prometheus_client import Counter, Histogram

AGENT_CALLS = Counter(
    "horragor_agent_calls_total",
    "Nombre d'invocations par agent du graphe",
    ["agent"],
)

AGENT_LATENCY = Histogram(
    "horragor_agent_latency_seconds",
    "Latence d'exécution par agent (nœud du graphe LangGraph)",
    ["agent"],
)

AGENT_TOKENS = Counter(
    "horragor_agent_tokens_total",
    "Tokens Groq consommés par agent",
    ["agent", "direction"],  # direction: input | output
)


def track_node(agent_name: str):
    """Décorateur : chronomètre un nœud du graphe et compte ses invocations."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(state):
            AGENT_CALLS.labels(agent=agent_name).inc()
            with AGENT_LATENCY.labels(agent=agent_name).time():
                return fn(state)
        return wrapper
    return decorator


def record_llm_usage(agent_name: str, response) -> None:
    """Enregistre les tokens d'un appel LLM (response.usage_metadata de LangChain)."""
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return
    AGENT_TOKENS.labels(agent=agent_name, direction="input").inc(usage.get("input_tokens", 0))
    AGENT_TOKENS.labels(agent=agent_name, direction="output").inc(usage.get("output_tokens", 0))
