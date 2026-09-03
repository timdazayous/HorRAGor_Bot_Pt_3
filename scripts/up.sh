#!/usr/bin/env bash
# Démarre la stack Docker complète (API + Vault + Traefik + Langfuse +
# Prometheus/Grafana + Uptime Kuma).
#
# Pourquoi pas un simple `docker compose up -d` ? Docker Compose résout le
# contenu d'un `env_file:` UNE SEULE FOIS, au moment où il construit la
# configuration pour l'ensemble des services de l'invocation — pas au moment
# où chaque conteneur démarre réellement (même avec `depends_on: condition:
# service_completed_successfully`). Si `api`/`langfuse-*`/`grafana` sont
# lancés dans la MÊME invocation que `vault-agent`, le fichier
# vault/rendered/secrets.env n'existe pas encore quand Compose construit leur
# config : ils démarrent avec des secrets vides. Deux invocations séparées
# évitent le problème — la seconde voit le fichier déjà écrit par la première.
#
# Usage : bash scripts/up.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/2] Vault -> vault-seed -> vault-agent (rend vault/rendered/secrets.env)..."
docker compose up vault-agent

echo "[2/2] Démarrage du reste de la stack..."
docker compose up -d

echo "Stack démarrée. Voir http://traefik.horragor.localhost (ou :8080) pour la carte du routing."
