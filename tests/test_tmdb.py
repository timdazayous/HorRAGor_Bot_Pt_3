import os
import sys

# Ajouter le chemin racine au PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.tmdb_api import TMDBService


def test_tmdb():
    tmdb = TMDBService()
    
    print("\n--- TEST TMDB API ---")
    query = "Smile"
    print(f"Recherche de : {query}")
    
    movies = tmdb.search_horror_movies(query, "2022")
    
    if movies:
        for movie in movies:
            print(f"Succès ! Trouvé : {movie.title}")
            print(f"ID TMDB : {movie.tmdb_id}")
            print(f"ID IMDB : {movie.imdb_id}")
            print(f"Popularité : {movie.popularity}")
            print(f"Genres : {movie.genres}")
    else:
        print("Aucun résultat ou erreur API.")

if __name__ == "__main__":
    test_tmdb()
