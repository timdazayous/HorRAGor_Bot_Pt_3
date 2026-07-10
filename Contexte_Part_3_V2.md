Dans le cadre de cette mise en situation professionnelle, vous allez rompre avec l'architecture monolithique du prototype précédent pour faire basculer HorRAGor dans l'ère de l'industrialisation multi-agent.
Votre travail consistera à segmenter les responsabilités de l'application en concevant un réseau d'agents spécialisés et autonomes (Fouille locale FAISS, Enquête Web, et Narration Gothique) qui collaborent de manière étanche via un graphe LangGraph. Vous implémenterez des stratégies avancées de routage conditionnel et d'élagage de contexte (Context Trimming) pour éliminer le bruit technique et garantir la stabilité d'un LLM local (Qwen) en production. Toute la stack MLOPS habituel devra être mise en place.
Référentiels
[2023] Certification RNCP Développeur.se en intelligence artificielle
Ressources
[Brief_partie_3](HorRAGor BOT Partie 3 V2.pdf)
Contexte du projet
🎬 Contexte du projet

Le prototype de l'agent HorRAGor V2 que vous avez déployé le mois dernier a fait sensation auprès de la direction de GoreStream. Capable d'interroger son index vectoriel local FAISS et d'aller chercher des informations fraîches sur le Web, l'agent a prouvé la valeur ajoutée d'un système RAG appliqué au cinéma d'épouvante. Fort de ce succès, le top management a donné son feu vert pour intégrer ce "moteur de connaissances" sur l'application mobile de la plateforme, ouvrant la phase de bêta-test auprès de 500 utilisateurs passionnés.

Cependant, après quelques jours d'utilisation intensive, les équipes de la QA (Assurance Qualité) et les administrateurs système ont tiré la sonnette d'alarme. Deux problèmes critiques bloquent actuellement le passage à l'échelle globale :

L'effondrement de l'immersion narrative : Au cours d'une conversation prolongée, l'agent monolithique ReAct s'emmêle les pinceaux. Plus l'historique se remplit de structures de données (les morceaux de lore extraits de FAISS et les textes bruts renvoyés par le scraper Web), plus le LLM local devient "fainéant". Il oublie sa consigne de jeu de rôle gothique, commence ses phrases par des artefacts de formatage (deux-points, sauts de lignes injustifiés), et finit par recracher des données brutes froides au lieu de générer un récit terrifiant et captivant.
L'opacité totale des performances (Boîte Noire) : En analysant les logs de la console du serveur FastAPI, l'équipe DevOps est incapable de profiler l'application. Lorsqu'une requête met 8 secondes à répondre, impossible de savoir si la faute incombe à une lenteur de l'index vectoriel FAISS, à un temps de réponse désastreux de l'API de scraping, ou à la phase de génération du LLM sous Ollama. De plus, aucun outil ne permet de mesurer la consommation de tokens par utilisateur, rendant toute estimation de coût d'infrastructure impossible.
Face à ce constat, le Lead Data Scientist et le Responsable MLOps ont validé un plan d'action immédiat. Vous êtes chargé de mener la refactorisation de l'application vers une architecture distribuée Multi-Agent sous LangGraph, adossée à une stack d'observabilité industrielle utilisant Langfuse et Docker. Votre mission est de compartimenter l'intelligence de HorRAGor pour restaurer sa plume horrifique tout en ouvrant une visibilité totale sur les entrailles de son système d'orchestration.

Vous adopterez une posture d'ingénieur MLOps en déployant une infrastructure d'observabilité complète avec Langfuse, prometheus, grafana et uptime kuma sous Docker Compose. Une documentation sphinx vous sera demandé pour décrire votre UI et votre backend, les tests automatiques seront mise en place ainsi que le CI/CD pour les 3 parties (BDD, Modèle, BDD). La communication entre service devra être sécurisé avec des refresh tokens lié au compte utilisateur.

Vous instrumenterez vos routes FastAPI et votre interface Streamlit existantes pour profiler graphiquement la latence, traquer les appels d'outils et monitorer la consommation réelle de tokens de votre architecture distribuée.

Modalités pédagogiques
Le travail se finalisera en individuel même si vous pouvez travailler en groupe.

Il est important que chacun mène ses briques MLOPS et de sécurité seul.

Le projet s'étalera sur cette semaine et la semaine lié à la sécurité.

Modalités d'évaluation
Pour valider cette Partie 3, les apprenants devront se plier aux exigences d'une mise en production industrielle. L'évaluation ne portera pas uniquement sur le fait que "l'application fonctionne", mais sur la propreté de l'architecture, l'optimisation des tokens et la maîtrise des outils d'observabilité.
Livrables
Le code source refactorisé : L'arborescence cible (src/graph/nodes.py, router.py, pipeline.py) respectée à la lettre, sans code mort ni variables globales cachées. Le code est testé à au moins 80%
L'infrastructure Docker : Le fichier docker-compose.yml fonctionnel permettant de monter l'instance locale de Langfuse, prometheus, grafana, utime kuma et des api en une seule commande.
L'environnement virtuel : Un fichier pyproject.toml à jour, incluant les dépendances.
La documentation : Généré avec sphinx elle décrit les deux API, le schéma de BDD et le multiagent
Critères de performance
Séparation des responsabilités (SoC) : Le code ne contient aucun "agent à tout faire". Les logiques de recherche locale, d'extraction web et de génération de texte sont strictement cloisonnées dans leurs fonctions dédiées (nodes.py).
Intégrité de l'État (State) : Le dictionnaire global (ou la classe TypedDict / Pydantic) est mis à jour de manière asynchrone sans écraser les données précédentes, garantissant une mémoire de session fiable.
Déterminisme du Routage : Le graphe ne boucle jamais à l'infini. Les transitions conditionnelles (router.py) s'exécutent de manière prévisible selon la présence ou l'absence d'informations dans le State.
Traçabilité totale : 100 % des requêtes HTTP reçues par FastAPI génèrent une trace exploitable dans le tableau de bord Langfuse.
Reproductibilité : La commande docker compose up -d lève l'infrastructure de monitoring locale (Langfuse + base de données associée) sans erreur.