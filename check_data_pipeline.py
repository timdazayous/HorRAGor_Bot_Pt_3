"""
Script de diagnostic manuel du pipeline d'ingestion HorRAGor (Partie 1).
Ce n'est pas une suite pytest : chaque fonction affiche un rapport lisible et
enchaîne ses résultats à la suivante (voir le bloc __main__).
Lance depuis la racine du projet : python check_data_pipeline.py
"""
import json
from pathlib import Path

# =========================================================
# TEST 1 : TMDB
# =========================================================
def test_tmdb():
    print("\n" + "="*50)
    print("TEST 1 : TMDB API")
    print("="*50)
    try:
        from app.services.tmdb_api import TMDBService
        tmdb = TMDBService()

        # Découverte page 1
        data = tmdb.discover_horror_movies(page=1)
        if not data or "results" not in data:
            print("❌ TMDB : pas de réponse")
            return []

        results = data["results"]
        print(f"✅ TMDB : {len(results)} films trouvés (page 1/{data.get('total_pages', '?')})")

        # Détail du premier film
        first = results[0]
        details = tmdb.get_movie_details(first["id"])
        print(f"   Exemple : {first['title']} ({first.get('release_date', '?')[:4]})")
        print(f"   IMDB ID : {details.get('imdb_id') if details else 'N/A'}")
        print(f"   Vote    : {first.get('vote_average')}/10")

        from app.models.schema import MovieGold
        movies = []
        for r in results:
            d = tmdb.get_movie_details(r["id"])
            movies.append(MovieGold(
                tmdb_id=r["id"],
                imdb_id=d.get("imdb_id") if d else None,
                title=r["title"],
                original_title=r.get("original_title"),
                release_date=r.get("release_date"),
                overview=r.get("overview"),
                vote_average=r.get("vote_average"),
                popularity=r.get("popularity"),
                genres=[g["name"] for g in d.get("genres", [])] if d else ["Horror"],
                source_system="HorRAGor-Pipeline/TMDB",
            ))
        print(f"✅ TMDB : {len(movies)} MovieGold créés")
        return movies

    except Exception as e:
        print(f"❌ TMDB erreur : {e}")
        return []


# =========================================================
# TEST 2 : KAGGLE CSV (Polars)
# =========================================================
def test_kaggle():
    print("\n" + "="*50)
    print("TEST 2 : KAGGLE CSV (Polars)")
    print("="*50)
    try:
        from app.services.kaggle_service import KaggleService
        kaggle = KaggleService()

        print(f"   horror_movies.csv  → {kaggle.horror_csv}")
        print(f"   IMDB Horror CSV    → {kaggle.imdb_csv}")
        print(f"   horror existe ?    → {kaggle.horror_csv.exists()}")
        print(f"   imdb existe ?      → {kaggle.imdb_csv.exists()}")

        movies = kaggle.get_all_movies()
        print(f"✅ Kaggle : {len(movies)} films chargés")

        if movies:
            m = movies[0]
            print(f"   Exemple : {m.title} | date={m.release_date} | genres={m.genres}")

        return movies

    except Exception as e:
        print(f"❌ Kaggle erreur : {e}")
        import traceback; traceback.print_exc()
        return []


# =========================================================
# TEST 3 : IMDB SQLite
# =========================================================
def test_imdb():
    print("\n" + "="*50)
    print("TEST 3 : IMDB SQLite")
    print("="*50)
    try:
        from app.services.imdb_service import IMDBService
        imdb = IMDBService()
        print(f"   DB path : {imdb.db_path}")
        print(f"   DB existe ? {imdb.db_path.exists()}")

        if not imdb.db_path.exists():
            print("⚠️  Base SQLite absente — skippe ce test")
            print("   → Télécharge title.basics.tsv.gz + title.ratings.tsv.gz")
            print("     depuis https://datasets.imdbws.com/")
            print("     puis lance : IMDBService.build_sqlite_from_tsv(...)")
            return []

        movies = imdb.get_horror_movies()
        print(f"✅ IMDB : {len(movies)} films chargés")
        if movies:
            m = movies[0]
            print(f"   Exemple : {m.title} | imdb={m.imdb_id} | vote={m.vote_average}")
        return movies

    except Exception as e:
        print(f"❌ IMDB erreur : {e}")
        import traceback; traceback.print_exc()
        return []


# =========================================================
# TEST 4 : ROTTEN TOMATOES (1 seul film)
# =========================================================
def test_rotten_tomatoes():
    print("\n" + "="*50)
    print("TEST 4 : ROTTEN TOMATOES (1 film)")
    print("="*50)
    try:
        from app.scrapers.rotten_tomatoes import RottenTomatoesScraper
        with RottenTomatoesScraper() as rt:
            result = rt.scrape_movie("The Shining", year=1980)

        if result:
            print(f"✅ RT : The Shining")
            print(f"   Tomatometer  : {result.tomatometer_score}%")
            print(f"   Audience     : {result.audience_score}%")
            print(f"   Consensus    : {result.critics_consensus[:80] if result.critics_consensus else 'N/A'}...")
            print(f"   URL          : {result.source_url}")
        else:
            print("⚠️  RT : film non trouvé (vérifier les sélecteurs CSS)")

        return result

    except Exception as e:
        print(f"❌ RT erreur : {e}")
        import traceback; traceback.print_exc()
        return None


# =========================================================
# TEST 5 : FUSION MDM
# =========================================================
def test_fusion(tmdb_movies, kaggle_movies):
    print("\n" + "="*50)
    print("TEST 5 : FUSION MDM")
    print("="*50)
    if not tmdb_movies and not kaggle_movies:
        print("⚠️  Pas de données à fusionner")
        return []

    try:
        from main_api import merge_movies
        merged = merge_movies([tmdb_movies, kaggle_movies])
        print(f"✅ Fusion : {len(tmdb_movies)} TMDB + {len(kaggle_movies)} Kaggle → {len(merged)} uniques")

        # Stats rapides
        with_imdb = sum(1 for m in merged if m.imdb_id)
        with_overview = sum(1 for m in merged if m.overview)
        print(f"   Avec imdb_id  : {with_imdb}/{len(merged)}")
        print(f"   Avec overview : {with_overview}/{len(merged)}")

        return merged

    except Exception as e:
        print(f"❌ Fusion erreur : {e}")
        import traceback; traceback.print_exc()
        return []


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    print("🎬 HorRAGor - Tests du pipeline d'ingestion")

    tmdb_movies  = test_tmdb()
    kaggle_movies = test_kaggle()
    imdb_movies  = test_imdb()
    rt_result  = test_rotten_tomatoes()  # ← décommenter pour tester RT

    merged = test_fusion(tmdb_movies, kaggle_movies)

    print("\n" + "="*50)
    print("RÉSUMÉ")
    print("="*50)
    print(f"  TMDB      : {len(tmdb_movies)} films")
    print(f"  Kaggle    : {len(kaggle_movies)} films")
    print(f"  IMDB      : {len(imdb_movies)} films")
    print(f"  Fusionnés : {len(merged)} films uniques")
    print("\nProchaine étape : lancer main.py pour le Gold Layer complet")