"""
Régénère docs/source/_static/graph.mmd à partir de la topologie RÉELLE du
graphe compilé (src/graph/pipeline.py) — à relancer après toute modification
du câblage du graphe, pour que la documentation ne devienne jamais obsolète.

Usage : uv run python docs/generate_graph_diagram.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.graph.pipeline import app  # noqa: E402

OUTPUT_PATH = Path(__file__).parent / "source" / "_static" / "graph.mmd"

if __name__ == "__main__":
    OUTPUT_PATH.write_text(app.get_graph().draw_mermaid(), encoding="utf-8")
    print(f"Diagramme régénéré : {OUTPUT_PATH}")
