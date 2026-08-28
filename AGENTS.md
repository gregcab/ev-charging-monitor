# Guide agent — EV Charging Monitor

Ce document résume l'architecture, la stack technique et les conventions de développement du projet. Il est destiné aux agents de codage ; le lecteur est supposé ne rien connaître du projet.

## Vue d'ensemble

**EV Charging Monitor** est une application Python légère qui surveille la disponibilité des bornes de recharge **Chademo** sur l'autoroute **A8** (tronçon Saint-Maximin → Cannes). Elle interroge périodiquement les API Chargemap, stocke l'historique dans une base SQLite et expose un dashboard web local.

Fonctionnalités principales :

- Liste de stations validées (`stations_validated.json`).
- Collecte automatique de la disponibilité toutes les 5 minutes (configurable).
- Type de connecteur surveillé choisi par station à l'ajout (`connector_type`, défaut `CHADEMO`).
- Recherche de station par nom/ville depuis le dashboard (sans slug Chargemap) via l'API Chargemap (`mappy` + `pool-detail`).
- Modification d'une station existante et choix de l'ordre d'affichage dans le sens de circulation (`display_order`).
- Page d'aide intégrée (`/aide`).
- Stockage historique dans SQLite (`ev_monitoring.db`).
- Dashboard web Flask (`http://127.0.0.1:5000`) avec tableau de bord, mini histogrammes 24h et graphiques d'historique détaillés.
- Image Docker publiée automatiquement sur GitHub Container Registry (GHCR).
- Suite de tests pytest dans `tests/` pour valider le rendu web, les API et la couche SQLite.

## Stack technique

- **Langage** : Python 3.11
- **Framework web** : Flask 2.3+
- **Planification** : `schedule` 1.2+
- **HTTP** : `requests` 2.31+
- **Fuseaux horaires** : `pytz`
- **Configuration** : `python-dotenv`
- **Base de données** : SQLite 3 (via le module standard `sqlite3`)
- **Tests** : `pytest` + client de test Flask natif (`app.test_client()`)
- **Frontend** : Templates Jinja2 + Chart.js (chargé depuis CDN) ; pas de build frontend
- **Conteneurisation** : Docker, Docker Compose / Dockge
- **CI/CD** : GitHub Actions (`.github/workflows/docker-build-push.yml`) pour builder et pousser l'image sur GHCR à chaque push sur `main`

## Structure du projet

```
.
├── .env                            # variables d'environnement optionnelles
├── .env.example                    # modèle de configuration
├── requirements.txt                # dépendances Python
├── run.py                          # point d’entrée principal
├── stations_validated.json         # stations surveillées (source de vérité)
├── ev_monitoring.db                # base SQLite générée automatiquement
├── compose.yaml                    # stack Docker Compose de production
├── Dockerfile                      # image de production
├── .dockerignore
├── README.md
├── AGENTS.md
└── ev_monitor/                     # package Python principal
    ├── __init__.py
    ├── config.py                   # chargement de la configuration/env
    ├── chargemap_client.py         # client API Chargemap
    ├── storage.py                  # accès SQLite (stations + logs)
    ├── monitor.py                  # scheduler de collecte périodique
    ├── dashboard.py                # application Flask + routes + templates filters
    └── templates/
        ├── index.html              # tableau de bord principal (recherche + ajout de station)
        ├── station.html            # page de détail d'une station
        ├── logs.html               # page des logs
        └── aide.html               # page d'aide utilisateur
```

## Architecture runtime

L'application est monolithique et s'exécute en un seul processus Python :

1. `run.py` initialise la base SQLite (`init_db`), injecte les stations validées (`seed_stations`), puis :
   - démarre un thread daemon qui exécute le scheduler de collecte (`monitor.run_scheduler`) ;
   - lance le serveur Flask (`dashboard.app.run`) sur l'hôte/port configurés.
2. Le scheduler interroge Chargemap toutes les `MONITOR_INTERVAL_MINUTES` minutes pour chaque station et enregistre la disponibilité.
3. Le dashboard lit la base SQLite à la volée pour afficher les données.

Il n'y a pas de ORM : les requêtes SQL sont écrites à la main dans `storage.py`.

## Configuration

Le fichier `.env` à la racine est optionnel (chargé par `python-dotenv`). Aucune clé API n'est requise. Variables reconnues :

| Variable | Obligatoire | Défaut | Description |
|----------|-------------|--------|-------------|
| `MONITOR_INTERVAL_MINUTES` | Non | `5` | Fréquence de collecte en minutes |
| `DASHBOARD_HOST` | Non | `127.0.0.1` | Interface d'écoute Flask |
| `DASHBOARD_PORT` | Non | `5000` | Port d'écoute Flask |
| `DB_PATH` | Non | `ev_monitoring.db` (racine) | Chemin vers la base SQLite |

En production conteneurisée, `DASHBOARD_HOST` doit valoir `0.0.0.0` et `DB_PATH` doit pointer vers le volume persistant (`/app/data/ev_monitoring.db`).

**Important** : `.env` et `*.db` sont dans `.gitignore`. Ne jamais commiter la base de données.

## Commandes de build et d'exécution

### Environnement local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Lancer l'application :

```bash
source .venv/bin/activate
python run.py
```

Le dashboard est accessible sur http://127.0.0.1:5000.

### Tests

```bash
source .venv/bin/activate
pytest
```

Les tests utilisent une base SQLite temporaire et un `stations_validated.json` temporaire. Ils ne nécessitent aucune clé API ni appel réseau.

### Docker local

```bash
docker build -t ev-charging-monitor .
mkdir -p data
docker run -d \
  --name ev-charging-monitor \
  -e DASHBOARD_HOST=0.0.0.0 \
  -e DB_PATH=/app/data/ev_monitoring.db \
  -v $(pwd)/data:/app/data \
  -p 5000:5000 \
  --restart unless-stopped \
  ev-charging-monitor
```

### Docker Compose (production)

```bash
docker compose pull
docker compose up -d
```

L'historique est conservé dans `./data/ev_monitoring.db` (volume monté). **Ne jamais utiliser `docker compose down -v`** car cela supprimerait le volume et l'historique.

Pour réinitialiser volontairement la base :

```bash
docker compose down
rm data/ev_monitoring.db
docker compose up -d
```

## Gestion des stations

La liste des stations surveillées est la source de vérité `stations_validated.json`. Pour la modifier :

1. Éditer `stations_validated.json`.
2. Supprimer `ev_monitoring.db` pour réinitialiser la base.
3. Relancer `python run.py`.

Il est aussi possible d'ajouter une station directement depuis le dashboard via la recherche Chargemap.

## Style et conventions de code

- **Langue** : les commentaires, docstrings et documentation utilisent le français (convention du projet).
- **Format** : Python standard, pas de formateur obligatoire configuré. Maintenir une indentation de 4 espaces et des lignes raisonnablement courtes.
- **Imports** : imports standards, puis tiers, puis internes (séparés par une ligne blanche).
- **Logging** : utiliser le module `logging` avec `logging.getLogger(__name__)` dans chaque module.
- **Base de données** : utiliser `sqlite3.Row` pour les lectures et s'assurer que les connexions sont fermées dans un bloc `try/finally`.
- **Configuration** : toute valeur configurable doit provenir de `ev_monitor.config` et pouvoir être surchargée par une variable d'environnement.
- **Templates Jinja2** : filtres personnalisés définis dans `dashboard.py` (ex. `fr_datetime`).
- **Tests** : utiliser `pytest`. Les fixtures partagées sont dans `tests/conftest.py`. Préférer les tests sans appel réseau, avec des données factices injectées en base.

## Considérations de sécurité

- Le dashboard Flask est exécuté avec `debug=False` en production. Ne pas activer `use_reloader=True` dans un conteneur.
- Aucune authentification n'est implémentée sur le dashboard. Par défaut il n'écoute que sur `127.0.0.1` ; en Docker il écoute sur `0.0.0.0`.
- L'image Docker n'inclut pas `.env` grâce à `.dockerignore`.

## Points de vigilance pour les modifications

- Le schéma SQLite est géré manuellement dans `storage.py`. Les migrations sont gérées par des `ALTER TABLE ... ADD COLUMN` avec `try/except OperationalError` (voir les colonnes `direction`, `connector_type`, `display_order`).
- La colonne historique `chademo_total` stocke le total du connecteur choisi par la station (`connector_type`, défaut `CHADEMO`). Les libellés français des connecteurs sont dans `CONNECTOR_LABELS` (`chargemap_client.py`), exposés aux templates via le filtre `connector_label`.
- La recherche de stations (`search_stations`) combine deux endpoints Chargemap : `mappy/charging_pools.json?city=...&state=2` (couvre les stations d'opérateurs) et `pool-detail/v2/pools?name=...` (pools communautaires, items `DELETED` exclus). Les recherches bbox de `mappy` sont plafonnées côté serveur pour les requêtes anonymes.
- Le tableau du dashboard est trié par sens de circulation (`direction`) puis par `display_order` croissant (défaut 0), avec la longitude en départage. L'ordre d'affichage est modifiable via l'API `POST /api/stations/<id>/edit` ou le bouton « Modifier » du dashboard.
- `get_all_stations()` filtre les stations en base par rapport à `stations_validated.json` ; une station supprimée du JSON disparaît du dashboard même si elle reste en base.
- Le scheduler utilise `schedule` + `time.sleep(1)` dans une boucle infinie dans un thread daemon. Ce thread s'arrête brutalement à la fermeture du processus Flask.
- Les templates HTML incluent Chart.js depuis un CDN externe (`cdn.jsdelivr.net`). Le dashboard nécessite donc un accès Internet côté client pour les graphiques.
- Les tests du dashboard utilisent `app.test_client()` et une base temporaire. Pour tester le rendu visuel réel (CSS, graphiques, responsive), envisager Playwright en phase 2.

## Backlog design

Les pistes d'amélioration de l'interface et de la lisibilité des données sont documentées dans [`design-backlog.md`](design-backlog.md). Les deux premiers items prioritaires sont :

1. Remplacer la colonne "Disponibles" par des barres de progression colorées.
2. Ajouter un bandeau d'état global permanent avec l'état de la dernière collecte.

Avant de les implémenter, s'assurer que les tests existants dans `tests/test_dashboard_render.py` couvrent toujours le rendu des nouveaux éléments.
