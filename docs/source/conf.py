"""Configuration Sphinx — documentation technique HorRAGor BOT (Partie 3)."""
import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

project = "HorRAGor BOT"
copyright = "2026, HorRAGor Team"
author = "HorRAGor Team"
release = "3.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinxcontrib.openapi",
    "sphinxcontrib.mermaid",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "HorRAGor BOT — Documentation technique"

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"
