"""
Exporte le schéma OpenAPI de l'API Intelligence (src/main.py) en JSON, pour
que sphinxcontrib-openapi puisse en générer la documentation automatique.

Usage : uv run python docs/generate_openapi.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.main import app  # noqa: E402

OUTPUT_PATH = Path(__file__).parent / "source" / "_static" / "openapi.json"

if __name__ == "__main__":
    OUTPUT_PATH.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Spec OpenAPI régénérée : {OUTPUT_PATH}")
