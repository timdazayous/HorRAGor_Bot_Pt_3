"""
Crée (ou met à jour le mot de passe de) le compte de service unique utilisé
par l'IHM Streamlit pour s'authentifier auprès de l'API Intelligence.

Génère un mot de passe aléatoire fort et l'affiche UNE SEULE FOIS en clair :
copie-le immédiatement dans le .env de l'UI (SERVICE_ACCOUNT_PASSWORD).

Usage : uv run python migrations/seed_service_account.py [username]
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src import auth  # noqa: E402

DEFAULT_USERNAME = "streamlit-ui"


def seed_service_account(username: str = DEFAULT_USERNAME) -> None:
    password = secrets.token_urlsafe(24)
    password_hash = auth.hash_password(password)

    conn = auth.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (%s, %s)
                ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash
                """,
                (username, password_hash),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Compte de service {username!r} prêt.")
    print("Copie ces valeurs dans le .env de l'IHM (elles ne seront plus jamais affichées) :")
    print(f"  SERVICE_ACCOUNT_USERNAME={username}")
    print(f"  SERVICE_ACCOUNT_PASSWORD={password}")


if __name__ == "__main__":
    seed_service_account(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME)
