"""
Pousse les secrets actuellement en clair dans .env vers Vault (KV v2), sur
3 chemins logiques repris ensuite par vault/secrets.env.tpl (Vault Agent) :

  secret/horragor/api         JWT_SECRET_KEY, GROQ_API_KEY, SUPABASE_DB_URL
  secret/horragor/langfuse    SALT, ENCRYPTION_KEY, NEXTAUTH_SECRET,
                               CLICKHOUSE_PASSWORD, REDIS_AUTH, MINIO_ROOT_PASSWORD
  secret/horragor/monitoring  GRAFANA_ADMIN_PASSWORD

Idempotent (écrase la version existante à chaque exécution). N'affiche
jamais les valeurs poussées, seulement les noms de variables — ce script
tourne dans les logs Docker du service one-shot `vault-seed`.

Usage (normalement via docker-compose, service `vault-seed`) :
  VAULT_ADDR=http://vault:8200 VAULT_TOKEN=... uv run python migrations/vault_seed.py
"""
import os
import sys

import hvac
from dotenv import load_dotenv

load_dotenv()

_PATHS: dict[str, dict[str, str]] = {
    "horragor/api": {
        "jwt_secret_key": "JWT_SECRET_KEY",
        "groq_api_key": "GROQ_API_KEY",
        "supabase_db_url": "SUPABASE_DB_URL",
    },
    "horragor/langfuse": {
        "salt": "LANGFUSE_SALT",
        "encryption_key": "LANGFUSE_ENCRYPTION_KEY",
        "nextauth_secret": "NEXTAUTH_SECRET",
        "clickhouse_password": "CLICKHOUSE_PASSWORD",
        "redis_auth": "REDIS_AUTH",
        "minio_root_password": "MINIO_ROOT_PASSWORD",
    },
    "horragor/monitoring": {
        "grafana_admin_password": "GRAFANA_ADMIN_PASSWORD",
    },
}

# Replis pour les secrets de la stack Langfuse/monitoring : reprend
# exactement les valeurs `${VAR:-default}` qui vivaient auparavant dans
# docker-compose.yml, pour que la stack démarre encore sans rien avoir à
# personnaliser dans .env (comme avant). JWT_SECRET_KEY/GROQ_API_KEY/
# SUPABASE_DB_URL n'ont volontairement pas de repli : ce sont des identifiants
# propres à chaque déploiement, pas des secrets internes au stack Docker.
_DEFAULTS: dict[str, str] = {
    "LANGFUSE_SALT": "mysalt",
    "LANGFUSE_ENCRYPTION_KEY": "0" * 64,
    "NEXTAUTH_SECRET": "mysecret",
    "CLICKHOUSE_PASSWORD": "clickhouse",
    "REDIS_AUTH": "myredissecret",
    "MINIO_ROOT_PASSWORD": "miniosecret",
    "GRAFANA_ADMIN_PASSWORD": "admin",
}


def vault_seed() -> None:
    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_addr or not vault_token:
        print("VAULT_ADDR et VAULT_TOKEN sont requis.", file=sys.stderr)
        sys.exit(1)

    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        print("Échec d'authentification à Vault (VAULT_TOKEN invalide ?).", file=sys.stderr)
        sys.exit(1)

    for kv_path, env_by_key in _PATHS.items():
        secret = {
            key: os.environ.get(env_var, _DEFAULTS.get(env_var, ""))
            for key, env_var in env_by_key.items()
        }
        client.secrets.kv.v2.create_or_update_secret(path=kv_path, secret=secret)
        print(f"secret/{kv_path} <- {', '.join(env_by_key.values())}")

    print("Secrets poussés dans Vault.")


if __name__ == "__main__":
    vault_seed()
