-- =========================================================
-- Rôles utilisateur (projet final sécurité — Partie 4 : autorisation)
-- 'user' peut interroger le graphe ; 'admin' accède en plus aux routes
-- d'administration. Défaut 'user' pour ne pas élever silencieusement les
-- comptes déjà existants (ex: le compte de service streamlit-ui).
-- =========================================================

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';
