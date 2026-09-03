# Vault Agent — rendu unique (pas un démon) des secrets de la stack HorRAGor
# en un fichier .env consommé ensuite par les autres conteneurs via
# `env_file:` (docker-compose.yml). `exit_after_auth = true` : l'agent
# s'authentifie, rend le template une fois, puis quitte — pas besoin d'un
# processus qui tourne en continu pour ce cas d'usage local.
#
# Auth : token_file (le token dev de Vault, déposé par le conteneur
# vault-agent lui-même avant de lancer cette commande — voir docker-compose.yml).
# Une AppRole serait le choix "production" (identité propre à l'agent plutôt
# qu'un token partagé), volontairement laissée de côté ici pour rester simple.

exit_after_auth = true
pid_file        = "/tmp/agent.pid"

vault {
  address = "http://vault:8200"
}

auto_auth {
  method "token_file" {
    config = {
      token_file_path = "/vault/rendered/.token"
    }
  }
}

template {
  source      = "/vault/config/secrets.env.tpl"
  destination = "/vault/rendered/secrets.env"
}
