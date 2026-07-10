# Schéma de la base de données

La base de données (PostgreSQL / Supabase) persiste le *Gold Layer* produit
par le pipeline d'ingestion de la Partie 1. Modélisation **Merise**
(MCD → MLD → MPD), approche **Hub & Spoke** : `FILM` est le hub central,
`EVALUATION`, `ANALYSE_SPARK` et `SOURCE` sont des spokes qui l'enrichissent
sans jamais dupliquer l'information.

```{note}
Le détail complet (MCD, cardinalités, exemples d'enregistrements, principes
RGPD appliqués) est maintenu dans `Merise.md` à la racine du projet —
reproduit ici pour que la doc Sphinx reste autonome.
```

## Diagramme entité-relation (MLD)

```{mermaid}
erDiagram
    FILM {
        int     id           PK
        int     tmdb_id      UK "NOT NULL — clé de référence MDM"
        varchar imdb_id      UK "nullable — enrichi par IMDB"
        varchar title        "NOT NULL"
        varchar original_title
        date    release_date
        text    overview
        float   popularity
        varchar source_system "NOT NULL"
        timestamp last_updated
    }

    GENRE {
        int     id   PK
        varchar name UK "NOT NULL"
    }

    FILM_GENRE {
        int film_id  FK
        int genre_id FK
    }

    EVALUATION {
        int       id          PK
        int       film_id     FK "NOT NULL"
        varchar   source_name "NOT NULL — TMDB, IMDB, Rotten Tomatoes"
        varchar   score_type  "NOT NULL — Critic, Audience, User"
        float     score_value "NOT NULL"
        float     score_scale "NOT NULL — 10 ou 100"
        int       num_votes
        text      review_text "critics_consensus RT"
        varchar   source_url
        timestamp evaluated_at
    }

    ANALYSE_SPARK {
        int       id                  PK
        int       film_id             FK UK "UNIQUE — 1 analyse par film"
        varchar   detected_language   "en, fr, other"
        int       overview_word_count
        jsonb     horror_keywords     "liste de mots-clés détectés"
        int       richness_score      "0-100"
        timestamp analysed_at
    }

    SOURCE {
        int       id                PK
        int       film_id           FK "NOT NULL"
        varchar   source_name       "NOT NULL"
        jsonb     contributed_fields "liste des champs fournis"
        timestamp ingested_at
    }

    FILM        ||--o{ FILM_GENRE   : "appartient à"
    GENRE       ||--o{ FILM_GENRE   : "caractérise"
    FILM        ||--o{ EVALUATION   : "reçoit"
    FILM        ||--o| ANALYSE_SPARK : "possède"
    FILM        ||--o{ SOURCE       : "tracé par"
```

## Relations (MLD)

- **FILM** (<u>id_film</u>, tmdb_id\*, imdb_id, title, original_title, release_date, overview, popularity, source_system, last_updated)
- **GENRE** (<u>id_genre</u>, name\*)
- **FILM_GENRE** (<u>#id_film</u>, <u>#id_genre</u>) — table de liaison N-N
- **EVALUATION** (<u>id_eval</u>, source_name, score_type, score_value, score_scale, num_votes, review_text, source_url, evaluated_at, *#id_film*)
- **ANALYSE_SPARK** (<u>id_analyse</u>, detected_language, overview_word_count, horror_keywords, richness_score, analysed_at, *#id_film*°) — contrainte UNIQUE sur id_film
- **SOURCE** (<u>id_source</u>, source_name, contributed_fields, ingested_at, *#id_film*)

> Légende : <u>souligné</u> = clé primaire | `#`clé_étrangère | `*` = NOT NULL | `°` = UNIQUE

## Principes RGPD appliqués

| Principe | Application |
|---|---|
| Minimisation des données | Seules les données nécessaires au RAG sont stockées. Aucune donnée personnelle utilisateur collectée. |
| Données publiques uniquement | Toutes les sources sont publiques (API officielles, bases ouvertes). |
| Traçabilité | La table `SOURCE` enregistre la provenance de chaque champ (principe d'*accountability*). |
| Suppression en cascade | `ON DELETE CASCADE` sur toutes les clés étrangères. |
| Pas de données personnelles | Aucune donnée d'acteur/réalisateur/utilisateur ; `review_text` contient uniquement le consensus éditorial Rotten Tomatoes. |

```{note}
Conformément au cahier des charges de la semaine sécurité, cette base sera
encapsulée derrière sa propre API dédiée et isolée dans un réseau Docker privé
étanche (inaccessible depuis l'extérieur du cluster) — ce module de
documentation sera alors complété par la doc auto de cette API Données.
```
