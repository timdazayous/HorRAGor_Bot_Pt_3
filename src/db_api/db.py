"""Connexion psycopg2 — point d'accès unique à Supabase pour db-api (Couche Données)."""
import os

import psycopg2


def get_conn() -> psycopg2.extensions.connection:
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL ou DATABASE_URL non configurée.")
    return psycopg2.connect(db_url)
