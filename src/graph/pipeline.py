"""
pipeline.py — L'Ingénieur Système (Le Câblage)

Assemble les ouvriers (nodes.py) et les aiguilleurs (router.py) autour du
State commun (models/state.py) puis compile le graphe. C'est ce module qui
matérialise la topologie exacte du réseau multi-agent HorRAGor :

    START → rag ─┬─(complet)──────────────→ narration → judge ─┬─(rejeté, retries restants)─┐
                  └─(incomplet)→ scraper ──────────────┘        │                             │
                                                                 └─(satisfaisant / épuisé)→ END │
                                                                                    ↑___________┘
"""
from langgraph.graph import END, START, StateGraph

from src.graph.nodes import judge_node, narration_node, rag_node, scraper_node
from src.graph.router import should_retry_or_end, should_scrape_or_narrate
from src.models.state import AgentState

workflow = StateGraph(AgentState)

workflow.add_node("rag", rag_node)
workflow.add_node("scraper", scraper_node)
workflow.add_node("narration", narration_node)
workflow.add_node("judge", judge_node)

workflow.add_edge(START, "rag")
workflow.add_conditional_edges(
    "rag",
    should_scrape_or_narrate,
    {"scraper": "scraper", "narration": "narration"},
)
workflow.add_edge("scraper", "narration")
workflow.add_edge("narration", "judge")
workflow.add_conditional_edges(
    "judge",
    should_retry_or_end,
    {"retry": "narration", "end": END},
)

app = workflow.compile()
