"""
Crée (ou met à jour le mot de passe de) les deux comptes de démonstration
utilisés pour valider la couche sécurité (projet final) : un `user` standard
et un `admin`.

Génère un mot de passe aléatoire fort par compte et l'affiche UNE SEULE FOIS
en clair : à copier immédiatement si besoin (tests manuels, Postman...).

Usage : uv run python migrations/seed_demo_users.py
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src import auth  # noqa: E402

DEMO_ACCOUNTS = [
    ("demo-user", "user"),
    ("demo-admin", "admin"),
]


def seed_demo_users() -> None:
    conn = auth.get_conn()
    try:
        for username, role in DEMO_ACCOUNTS:
            password = secrets.token_urlsafe(24)
            password_hash = auth.hash_password(password)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username) DO UPDATE
                        SET password_hash = EXCLUDED.password_hash,
                            role = EXCLUDED.role
                    """,
                    (username, password_hash, role),
                )
            conn.commit()
            print(f"{username!r} (role={role}) : {password}")
    finally:
        conn.close()


if __name__ == "__main__":
    seed_demo_users()
