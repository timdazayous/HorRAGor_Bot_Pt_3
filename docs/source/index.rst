HorRAGor BOT — Documentation technique
=======================================

Agent conversationnel spécialisé dans l'univers de l'horreur, refactorisé en
architecture **multi-agent distribuée** sous LangGraph (Partie 3), adossée à
une stack d'observabilité Langfuse + Prometheus + Grafana + Uptime Kuma.

Cette documentation couvre les trois piliers demandés par le cahier des
charges MLOps :

- la **doc automatique de l'API** (Couche Intelligence — le graphe multi-agent) ;
- le **schéma relationnel de la base de données** (Couche Données, Partie 1) ;
- la **cartographie complète du graphe multi-agent** (générée depuis le code
  réel via ``langgraph``, jamais obsolète).

.. note::
   La **Couche Données** (base de données encapsulée derrière sa propre API
   dédiée, dans un réseau Docker privé étanche) est prévue pour la semaine
   sécurité de la Partie 3. Cette documentation décrit donc pour l'instant
   une seule API — l'**Intelligence** (``src/main.py``) — et sera complétée
   dès que la seconde API existera.

.. toctree::
   :maxdepth: 2
   :caption: Sommaire

   architecture
   database
   api
   modules
