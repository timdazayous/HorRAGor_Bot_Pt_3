**TVA — TIME VARIANCE AUTHORITY**

**Observabilité avec Grafana, Loki & Prometheus**

Un cas pratique guidé pour apprendre à construire des dashboards, poser des alertes et mener une enquête d'incident sur une stack Grafana / Loki / Prometheus.

**Pitch d’intro**

|  « Agents, nous avons un problème. Notre système de détection des fraudes fait tourner notre modèle de référence, v1.0-sacred : stable, rapide, prédictible. Pour améliorer nos performances, une nouvelle version expérimentale a été déployée en A/B testing : v2.0-variant-loki. Problème : cette variante provoque des Événements Nexus sur le réseau. Des temps de réponse explosent le SLA, et des erreurs critiques HTTP 500 menacent plusieurs branches temporelles. Votre mission : surveiller, détecter, et corriger. Ouvrez vos terminaux, lancez l'environnement et connectez-vous à Grafana. Pour le bien de la Ligne Temporelle Sacrée : à vous de jouer. » |
| :---- |

**Votre mission en un coup d'œil**

* Phase 1 — Construire le panneau de contrôle : des métriques et des dashboards en Prometheus et LogQL pour comparer Sacred et la Variante.

* Phase 1.3 — Automatiser les alarmes : une alerte qui se déclenche dès qu'une accumulation de crashs 500 menace la stabilité.

* Phase 3 — Mener l'enquête de crise : plonger dans les logs bruts pour isoler la branche défaillante et décider du rollback.

* Phase 4 — Clore l'incident : vérifier le correctif et rédiger un post-mortem express.

**Prérequis**

* Docker et Docker Compose installés.

* Les ports 3000 (Grafana), 3100 (Loki), 8080 (cAdvisor) et 9090 (Prometheus) libres sur votre machine.

* Les 4 fichiers fournis dans le même dossier : docker-compose.yml, promtail-config.yml, prometheus.yml, fraudguard_api.py.



# **Phase 0 — Déploiement de l'infrastructure**

Avant d'inspecter les flux temporels, on déploie la stack complète : Loki (logs), Promtail (collecte), Prometheus (métriques), cAdvisor (export des métriques de conteneurs) et Grafana (visualisation), ainsi que l'API de détection des fraudes simulée.

## **0.1 — Démarrage de la stack**

Depuis le dossier contenant les 4 fichiers :

| docker compose up -d |
| :---- |

Vérifiez tout tournent correctement :

| docker compose ps |
| :---- |


| **Attendez un peu avant de commencer** L'API met environ 2 minutes avant que la première anomalie n'apparaisse — le temps de construire vos dashboards sur un système sain en Phase 1. Ne vous étonnez pas si tout est vert au début, c'est voulu. |

## **0.2 — Connexion à Grafana**

* Ouvrez http://localhost:3000

* Identifiants par défaut : admin / admin (cliquez sur « Skip » si Grafana demande de changer le mot de passe).

## **0.3 — Ajouter la source de données Loki**

* Menu latéral → icône d'engrenage / Connections → Data sources.

* Add data source → recherchez Loki.

* URL : http://loki:3100

* Descendez tout en bas → Save & test. Un message vert « Data source is working » doit apparaître.

## **0.4 — Ajouter la source de données Prometheus**

Même procédure, avec Prometheus cette fois :

* Add data source → recherchez Prometheus.

* URL : http://prometheus:9090

* Save & test.

| Pourquoi cAdvisor et pas un exporteur dans l'API ? cAdvisor observe les conteneurs Docker de l'extérieur (CPU, mémoire) sans qu'on ait besoin de modifier une seule ligne de l'API. C'est le moyen le plus simple d'avoir des métriques Prometheus à côté des logs Loki. |
| :---- |

# **Phase 1 — Dashboards & alertes**

On configure le moniteur central pour auditer les flux d'inférence en continu.

## **Exercice 1.0 — Un premier coup d'œil côté métriques**

Créez un panneau Grafana de type Time Series sur la source Prometheus.

* **Objectif :** vérifier que le conteneur de l'API tourne normalement (CPU).

| rate(container_cpu_usage_seconds_total{name=~".*tva-fraudguard.*"}[1m]) |
| :---- |

C'est le même réflexe qu'ouvrir le gestionnaire de tâches : un premier signal chiffré, avant de creuser dans le détail des logs.

## **Exercice 1.1 — Latence par version (SLA)**

Créez un panneau Time Series sur la source Loki.

* **Objectif :** comparer le temps d'inférence moyen entre Sacred et la Variante.

| avg by (model_version) (avg_over_time({container=~".*tva-fraudguard.*"} | json | unwrap inference_time_ms [5m])) |
| :---- |

Résultat attendu : deux lignes apparaissent. v1.0-sacred reste sous les 100 ms ; v2.0-variant-loki produira des pics au-delà de 400 ms une fois l'anomalie démarrée.

| Pour aller plus loin (optionnel) Une moyenne cache les pics — et ce sont justement les pics qui cassent le SLA. Les équipes MLOps regardent plutôt un percentile (p95) : quantile_over_time(0.95, {container=~".*tva-fraudguard.*"} | json | unwrap inference_time_ms [5m]) by (model_version) |
| :---- |

## **Exercice 1.2 — Volume de trafic (RPS)**

Créez un second panneau Time Series.

* **Objectif :** mesurer le taux de requêtes par seconde traitées par chaque version.

| sum by (model_version) (rate({container=~".*tva-fraudguard.*"} | json [1m])) |
| :---- |

## **Exercice 1.3 — Automatiser la détection (alerte)**

Objectif : être notifié automatiquement dès qu'une accumulation de crashs 500 menace la stabilité, sans surveiller le dashboard en continu.

| sum(count_over_time({container=~".*tva-fraudguard.*"} | json | status = 500 [2m])) |
| :---- |

Menu Alerting → Alert Rules → New alert rule, puis :

* **1. Name :** Alerte Nexus - Crashs 500

* **2. Query :** source Loki, la requête ci-dessus. Condition WHEN QUERY A IS ABOVE → remplacez 0 par 3.

* **3. Folder :** + New folder → « TVA ».

* **4. Evaluation :** + New evaluation group → nexus-group, interval 1m, pending period 0s (déclenchement immédiat).

* **5. Notifications :** laissez « empty » par défaut, puis sauvegardez.

# **Phase 2 — Surveillance en routine**

Cette phase ne demande aucune action de votre part : c'est le moment où le système travaille pour vous.

* Promtail capture la sortie de tva-fraudguard-api et l'expédie vers Loki.

* cAdvisor expose les métriques CPU/mémoire des conteneurs ; Prometheus les récupère toutes les 15 secondes.

* Loki et Prometheus réévaluent la règle d'alerte toutes les minutes.

Gardez un œil sur vos dashboards de la Phase 1 : d'ici quelques minutes, la latence de v2.0-variant-loki devrait commencer à grimper.

# **Phase 3 — Enquête de crise**

Une alerte rouge retentit : un Événement Nexus a été détecté. Direction le mode Explore pour diagnostiquer en temps réel.

![][image1]

## **Exercice 3.1 — Filtrage du flux brut d'erreurs**

| {container=~".*tva-fraudguard.*"} |= "500" |
| :---- |

Analyse : confirmation de la présence d'erreurs HTTP 500 dans le flux général.

## **Exercice 3.2 — Identification du modèle défaillant**

| {container=~".*tva-fraudguard.*"} | json | status = 500 |
| :---- |

Analyse : dépliez les lignes dans "Parsed Fields". 100 % des crashs 500 proviennent de model_version = "v2.0-variant-loki".

## **Exercice 3.3 — Localisation de la branche corrompue**

| {container=~".*tva-fraudguard.*"} | json | model_version = "v2.0-variant-loki" and inference_time_ms > 300 |
| :---- |

Diagnostic : les événements Nexus surviennent exclusivement sur la branche "timeline-us-nexus".

## **Exercice 3.4 — Rollback et vérification (nouveau)**

Le diagnostic est posé : on corrige, puis on vérifie que le correctif fonctionne réellement.

* 1. Éditez fraudguard_api.py et retirez la variante défaillante de la liste des modèles :

| MODELS = ["v1.0-sacred"]  # v2.0-variant-loki retiré du trafic |
| :---- |

* 2. Redémarrez uniquement l'API (le fichier est monté en volume, pas besoin de rebuild) :

| docker compose restart tva-fraudguard-api |
| :---- |

* 3. Retournez sur vos dashboards de la Phase 1 : la latence de la Variante disparaît, le RPS ne montre plus qu'une seule version, et l'alerte « Alerte Nexus - Crashs 500 » repasse au vert après 1 à 2 minutes.

# **Phase 4 — Clore l'incident**

Un incident MLOps ne se termine pas au rollback : il se termine quand il est documenté. Rédigez un post-mortem express en 5 lignes, à partir de ce que vous avez observé.

* Cause racine : quelle version, quel comportement ?

* Impact : quelle branche, quelle proportion de requêtes, sur quelle durée ?

* Détection : comment l'alerte a-t-elle été déclenchée ?

* Action corrective : qu'avez-vous fait ?

* Action préventive : que changeriez-vous pour éviter que ça se reproduise (ex : seuil de crash automatique avant d'élargir un A/B test) ?

# **Dépannage**

**La source de données Loki ou Prometheus échoue au test**

Vérifiez que le conteneur correspondant tourne : docker compose ps. Si besoin, docker compose logs loki (ou prometheus).

**Aucun log n'apparaît dans Explore**

Vérifiez que Promtail a bien accès à /var/run/docker.sock — c'est le point de défaillance le plus fréquent. docker compose logs promtail pour voir les erreurs.

**L'alerte ne se déclenche jamais**

Rappel : l'anomalie ne démarre qu'après ~2 minutes (voir Phase 0). Vérifiez aussi que le pending period est bien à 0s et l'evaluation interval à 1m.

# **Nettoyage**

Une fois le tuto terminé, on arrête tout et on nettoie les volumes :

| docker compose down -v |
| :---- |

# **Pour aller plus loin (optionnel)**

Trois pistes si vous voulez creuser après la formation — pas nécessaires pour terminer le tuto.

**Le piège de la cardinalité**

Essayez de transformer fraud_score en label dans promtail-config.yml au lieu de le laisser dans le corps JSON. Redémarrez Promtail, regardez le nombre de flux créés dans Loki. Comme fraud_score est presque toujours différent, chaque valeur crée un nouveau flux — l'index explose. C'est pour ça qu'on ne met en label que des valeurs stables (app, env, container).

**Rendre un dashboard réutilisable**

Plutôt que d'écrire model_version en dur dans chaque requête, créez une variable Grafana ($model_version) et utilisez-la dans vos panneaux. Un dashboard avec des variables se réutilise pour n'importe quelle version future.

**La rétention des logs**

Par défaut Loki garde les logs indéfiniment. En production, on configure une durée de rétention (limits_config.retention_period) pour maîtriser le stockage — cohérent avec l'argument "Loki reste léger et économique".

