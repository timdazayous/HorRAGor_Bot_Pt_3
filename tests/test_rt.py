import os
import sys

import pytest

# Ajouter le chemin racine au PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.scrapers.rotten_tomatoes import RottenTomatoesScraper


@pytest.mark.skip(
    reason="Test d'intégration réel (navigateur Selenium + scraping live de "
           "Rotten Tomatoes) — lent et flaky en CI, à lancer manuellement."
)
def test_rt():
    print("\n--- TEST ROTTEN TOMATOES SCRAPER ---")

    # Test avec un film d'horreur qui a des scores
    title = "Smile"
    year = "2022"
    print(f"Scraping de : {title} ({year})")

    with RottenTomatoesScraper() as scraper:
        data = scraper.scrape_movie(title, year)

    if data:
        print("Succès !")
        print(f"Tomatometer : {data.tomatometer_score}%")
        print(f"Audience Score : {data.audience_score}%")
        print(f"Consensus : {data.critics_consensus}")
    else:
        print("Échec du scraping (film peut-être pas encore sur RT ou URL incorrecte).")


if __name__ == "__main__":
    test_rt()
