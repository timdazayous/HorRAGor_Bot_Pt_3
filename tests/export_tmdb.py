import json
import os
import sys

# Ajouter le chemin racine au PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config.config import settings
from app.services.tmdb_api import TMDBService
from app.utils.logger import logger


def export_horror_movies(max_pages: int = 5):
    tmdb = TMDBService()
    all_movies = []
    
    logger.info(f"Début de l'export TMDB ({max_pages} pages)")
    
    for page in range(1, max_pages + 1):
        logger.info(f"Traitement de la page {page}...")
        data = tmdb.discover_horror_movies(page=page)
        
        if not data or "results" not in data:
            break
            
        for result in data["results"]:
            movie = {
                "tmdb_id": result["id"],
                "title": result["title"],
                "release_date": result.get("release_date"),
                "popularity": result.get("popularity"),
                "vote_average": result.get("vote_average")
            }
            all_movies.append(movie)
            
    # Sauvegarde dans data/output
    output_path = os.path.join(settings.DATA_OUTPUT_DIR, "tmdb_horror_raw.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_movies, f, indent=4, ensure_ascii=False)
        
    logger.info(f"Export terminé : {len(all_movies)} films sauvegardés dans {output_path}")

if __name__ == "__main__":
    # On commence par 3 pages pour le test
    export_horror_movies(max_pages=3)
