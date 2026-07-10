"""
Applique tous les fichiers .sql de ce dossier, dans l'ordre alphabétique,
sur la base Supabase configurée (SUPABASE_DB_URL ou DATABASE_URL).
Idempotent : les migrations utilisent IF NOT EXISTS, relancer ce script
plusieurs fois est sans danger.

Usage : uv run python migrations/apply_migrations.py
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent


def get_conn():
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL ou DATABASE_URL non configurée.")
    return psycopg2.connect(db_url)


def apply_migrations() -> None:
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print("Aucune migration trouvée.")
        return

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for path in sql_files:
                print(f"Application de {path.name}...")
                cur.execute(path.read_text(encoding="utf-8"))
        conn.commit()
        print(f"{len(sql_files)} migration(s) appliquée(s) avec succès.")
    finally:
        conn.close()


if __name__ == "__main__":
    apply_migrations()
