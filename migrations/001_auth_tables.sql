-- =========================================================
-- Authentification — Refresh Tokens (Partie 3, semaine sécurité)
-- Verrouille les échanges IHM (Streamlit) <-> API Intelligence.
-- =========================================================

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt, jamais le mot de passe en clair
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- On ne stocke jamais le refresh token en clair : uniquement son hash SHA-256,
-- pour pouvoir le révoquer/vérifier sans exposer un secret exploitable en cas de fuite DB.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,        -- SHA-256 hex digest (64 caractères)
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked    BOOLEAN NOT NULL DEFAULT FALSE,     -- passe à TRUE lors de la rotation ou d'un logout
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id    ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
