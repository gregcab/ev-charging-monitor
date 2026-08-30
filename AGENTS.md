# Guide agent — EV Charging Monitor

Ce document résume l'architecture, la stack technique et les conventions de développement du projet. Il est destiné aux agents de codage ; le lecteur est supposé ne rien connaître du projet.

## Vue d'ensemble

**EV Charging Monitor** est une application Python légère et auto-hébergeable qui surveille la disponibilité de bornes de recharge choisies par l'utilisateur, partout en France. Elle interroge périodiquement l’API **Chargemap**, stocke l'historique dans une base SQLite et expose un dashboard web local.

Fonctionnalités principales :

- Liste de stations validées (`stations_validated.json`), **vide par défaut** : on démarre sans station et on ajoute les siennes via recherche ou carte. `stations_example.json` conserve l'ancienne liste des 5 stations A8 à titre d'exemple (non utilisé par l'app).
- Collecte automatique de la disponibilité toutes les 5 minutes en moyenne (configurable, relu à chaud par le scheduler). L'intervalle réel varie de ± 20 à 40 % pour éviter un pattern robot détectable par Chargemap.
- Type de connecteur surveillé choisi par station à l'ajout (`connector_type`) ; le défaut vient de `get_effective_settings()`.
- Recherche de station par nom/ville depuis le dashboard (sans slug Chargemap) via l'API Chargemap (`mappy` + `pool-detail`), et recherche autour d'un point sur la carte (`search_nearby`, bbox mappy).
- Organisation des stations par trajet libre (`direction`, texte libre) avec renommage/fusion/suppression depuis `/parametres`.
- Modification d'une station existante et choix de l'ordre d'affichage au sein du trajet (`display_order`).
- Page Paramètres (`/parametres`) : trajets + préférences (nom app, sous-titre, connecteur par défaut, intervalle de collecte) stockées dans la table `settings` avec priorité base > env > défaut.
- Page Carte (`/carte`) : carte Leaflet + tuiles OpenStreetMap, marqueurs colorés par disponibilité.
- Page d'aide intégrée (`/aide`).
- Stockage historique dans SQLite (`ev_monitoring.db`).
- Dashboard web Flask (`http://127.0.0.1:5000`) avec tableau de bord, mini histogrammes 24h, graphiques d'historique détaillés, tableau de fiabilité 7j/30j et heatmap des créneaux de disponibilité.
- Image Docker publiée automatiquement sur GitHub Container Registry (GHCR).
- Suite de tests pytest dans `tests/` pour valider le rendu web, les API et la couche SQLite.
- Script Playwright (`scripts/capture_screenshots.py`) pour générer les captures d’écran du README avec des données factices.

## Stack technique

- **Langage** : Python 3.11
- **Framework web** : Flask 2.3+
- **Planification** : `schedule` 1.2+
- **HTTP** : `requests` 2.31+
- **Fuseaux horaires** : `pytz`
- **Configuration** : `python-dotenv`
- **Base de données** : SQLite 3 (via le module standard `sqlite3`)
- **Tests** : `pytest` + client de test Flask natif (`app.test_client()`)
- **Captures d’écran** : `playwright` (script `scripts/capture_screenshots.py`)
- **Frontend** : Templates Jinja2 + Chart.js et Leaflet/OpenStreetMap (chargés depuis CDN) ; pas de build frontend
- **Conteneurisation** : Docker, Docker Compose / Dockge
- **CI/CD** : GitHub Actions (`.github/workflows/docker-build-push.yml`) pour builder et pousser l'image sur GHCR à chaque push sur `main`

## Structure du projet

```
.
├── .env                            # variables d'environnement optionnelles
├── .env.example                    # modèle de configuration
├── requirements.txt                # dépendances Python
├── requirements-dev.txt            # dépendances de développement (pytest, playwright)
├── run.py                          # point d’entrée principal
├── stations_validated.json         # liste des stations (vide par défaut : installation neuve)
├── stations_example.json           # exemple de liste (stations A8), non utilisé par l'app
├── ev_monitoring.db                # base SQLite générée automatiquement
├── data/                           # volume Docker persistant (DB + stations)
├── compose.yaml                    # stack Docker Compose de production
├── Dockerfile                      # image de production
├── .dockerignore
├── README.md
├── AGENTS.md
├── design-backlog.md
├── docs/screenshots/               # captures d’écran du README
├── scripts/
│   └── capture_screenshots.py      # génération des captures Playwright
├── tests/                          # tests pytest
└── ev_monitor/                     # package Python principal
    ├── __init__.py
    ├── config.py                   # chargement de la configuration/env
    ├── chargemap_client.py         # client API Chargemap (recherche + disponibilité)
    ├── storage.py                  # accès SQLite (stations + logs)
    ├── monitor.py                  # scheduler de collecte périodique
    ├── dashboard.py                # application Flask + routes + templates filters
    └── templates/
        ├── index.html              # tableau de bord principal (recherche + ajout de station)
        ├── station.html            # page de détail d'une station
        ├── logs.html               # page des logs
        ├── carte.html              # carte interactive (Leaflet/OSM + recherche à proximité)
        ├── parametres.html         # page des paramètres (trajets + préférences)
        └── aide.html               # page d'aide utilisateur
```

## Architecture runtime

L'application est monolithique et s'exécute en un seul processus Python :

1. `run.py` initialise la base SQLite (`init_db`), injecte les stations validées (`seed_stations`), puis :
   - démarre un thread daemon qui exécute le scheduler de collecte (`monitor.run_scheduler`) ;
   - lance le serveur Flask (`dashboard.app.run`) sur l'hôte/port configurés.
2. Le scheduler interroge Chargemap pour chaque station selon l'intervalle effectif (`get_effective_settings()["monitor_interval_minutes"]`) et enregistre la disponibilité. L'intervalle est relu à chaque itération : s'il change dans les paramètres, la planification est recréée à chaud.
3. Le dashboard lit la base SQLite à la volée pour afficher les données.

Il n'y a pas de ORM : les requêtes SQL sont écrites à la main dans `storage.py`.

## Configuration

Le fichier `.env` à la racine est optionnel (chargé par `python-dotenv`). Aucune clé API n'est requise. Variables reconnues :

| Variable | Obligatoire | Défaut | Description |
|----------|-------------|--------|-------------|
| `MONITOR_INTERVAL_MINUTES` | Non | `5` | Fréquence de collecte en minutes (repli, surchargeable via `/parametres`) |
| `DASHBOARD_HOST` | Non | `127.0.0.1` | Interface d'écoute Flask |
| `DASHBOARD_PORT` | Non | `5000` | Port d'écoute Flask |
| `DB_PATH` | Non | `ev_monitoring.db` (racine) | Chemin vers la base SQLite |
| `STATIONS_FILE` | Non | `<répertoire de DB_PATH>/stations_validated.json` | Chemin vers la liste des stations |
| `APP_NAME` | Non | `EV Charging Monitor` | Nom affiché de l'application (repli, surchargeable via `/parametres`) |
| `APP_SUBTITLE` | Non | `Disponibilité des bornes de recharge` | Sous-titre affiché (repli, surchargeable via `/parametres`) |
| `DEFAULT_CONNECTOR_TYPE` | Non | `CHADEMO` | Connecteur surveillé par défaut (repli, surchargeable via `/parametres`) |

Les préférences personnalisables (`app_name`, `app_subtitle`, `default_connector_type`, `monitor_interval_minutes`) sont stockées dans la table SQLite `settings` et éditées depuis `/parametres`. La priorité est **valeur en base > variable d'env > défaut embarqué** (voir `get_effective_settings()` dans `storage.py`). Les titres des pages utilisent `{{ app_name }}` / `{{ app_subtitle }}`, injectés dans tous les templates par le context processor `inject_app_identity` (`dashboard.py`).

En production conteneurisée, `DASHBOARD_HOST` doit valoir `0.0.0.0`, `DB_PATH` doit pointer vers le volume persistant (`/app/data/ev_monitoring.db`) et `STATIONS_FILE` doit se trouver dans le même répertoire (`/app/data/stations_validated.json`).

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

Les tests E2E Playwright sont marqués `@pytest.mark.e2e` et lancés séparément :

```bash
source .venv/bin/activate
pytest -m e2e
```

Ils ne sont pas exécutés dans la CI (qui lance `pytest -m "not e2e"`) car ils nécessitent des navigateurs Playwright.

### Docker local

```bash
docker build -t ev-charging-monitor .
mkdir -p data
docker run -d \
  --name ev-charging-monitor \
  -e DASHBOARD_HOST=0.0.0.0 \
  -e DB_PATH=/app/data/ev_monitoring.db \
  -e STATIONS_FILE=/app/data/stations_validated.json \
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

L'historique est conservé dans `./data/ev_monitoring.db` et la liste des stations dans `./data/stations_validated.json` (volume monté). **Ne jamais utiliser `docker compose down -v`** car cela supprimerait le volume, l’historique et la liste des stations.

Pour réinitialiser volontairement la base et la liste des stations :

```bash
docker compose down
rm data/ev_monitoring.db data/stations_validated.json
docker compose up -d
```

## Gestion des stations

La liste des stations surveillées est la source de vérité `stations_validated.json` (vide `[]` par défaut sur une installation neuve ; `stations_example.json` fournit un exemple non utilisé par l'app). En production Docker, ce fichier se trouve dans le volume persistant (`data/stations_validated.json`). Pour la modifier :

1. Éditer `stations_validated.json` (ou `data/stations_validated.json` sous Docker).
2. Supprimer `ev_monitoring.db` (ou `data/ev_monitoring.db` sous Docker) pour réinitialiser la base.
3. Relancer `python run.py` (ou redémarrer le conteneur).

Il est aussi possible d'ajouter ou de modifier une station directement depuis le dashboard via la recherche Chargemap ou la page Carte.

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

- Le schéma SQLite est géré manuellement dans `storage.py`. Les migrations sont gérées par des `ALTER TABLE ... ADD COLUMN` avec `try/except OperationalError` (voir les colonnes `direction`, `connector_type`, `display_order`) et par des `CREATE TABLE IF NOT EXISTS` (voir la table `settings`, créée par `init_db`). La migration depuis la version « A8 » est purement additive : aucune perte d'historique.
- La colonne historique `chademo_total` stocke le total du connecteur choisi par la station (`connector_type` ; le défaut vient de `get_effective_settings()["default_connector_type"]`). Les libellés français des connecteurs sont dans `CONNECTOR_LABELS` (`chargemap_client.py`), exposés aux templates via le filtre `connector_label`.
- La recherche de stations (`search_stations`) combine deux endpoints Chargemap : `mappy/charging_pools.json?city=...&state=2` (couvre les stations d'opérateurs) et `pool-detail/v2/pools?name=...` (pools communautaires, items `DELETED` exclus). Les recherches bbox de `mappy` sont plafonnées côté serveur pour les requêtes anonymes.
- La recherche à proximité (`search_nearby`, utilisée par la page `/carte` via `GET /api/stations/nearby?lat=&lon=&radius=`) interroge la bbox de `mappy` avec les paramètres `NW=<lat>;<lng>&SE=<lat>;<lng>` (format « lat;lng »), puis filtre et trie les résultats par distance réelle (haversine).
- Le tableau du dashboard est trié par trajet (`direction`, alphabétique insensible à la casse, stations sans trajet à la fin), puis par `display_order` croissant (défaut 0), avec la longitude en départage (voir `_sort_stations`). Les trajets sont des textes libres : les formulaires d'ajout/édition utilisent un champ texte + datalist des trajets existants (`get_trajets()`).
- Les trajets se gèrent depuis `/parametres` : `rename_trajet` met à jour toutes les stations concernées dans le JSON (et fusionne si le nouveau nom existe déjà), `delete_trajet` détache les stations (`direction = null`) sans les supprimer. Endpoints : `POST /api/trajets/rename`, `POST /api/trajets/delete`, `POST /api/settings`, `POST /api/settings/reset`.
- `get_all_stations()` filtre les stations en base par rapport à `stations_validated.json` ; une station supprimée du JSON disparaît du dashboard même si elle reste en base.
- Le scheduler utilise `schedule` + `time.sleep(1)` dans une boucle infinie dans un thread daemon. L'intervalle est jitteré (`random.uniform(0.8, 1.4)`) et les requêtes sont espacées de 2 à 5 secondes pour limiter le risque de blocage Chargemap. Après 3 erreurs consécutives sur une station, celle-ci saute un cycle ; après 2 cycles complets en erreur, l'intervalle est temporairement doublé. Il relit l'intervalle effectif à chaque itération et replanifie à chaud si `monitor_interval_minutes` a changé. Ce thread s'arrête brutalement à la fermeture du processus Flask.
- Les templates HTML incluent Chart.js et (pour `/carte`) Leaflet + les tuiles OpenStreetMap depuis des CDN externes. Le dashboard nécessite donc un accès Internet côté client pour les graphiques et la carte.
- Les statistiques de fiabilité (`get_station_stats`, `get_all_stations_stats`) et la heatmap (`get_hourly_heatmap`) sont calculées à la volée depuis `availability_log`. Elles dépendent de `MONITOR_INTERVAL_MINUTES` pour estimer le temps d’indisponibilité.
- Les routes API `/api/stats/<station_id>`, `/api/stations/stats` et `/api/heatmap/<station_id>` alimentent le tableau de fiabilité et la heatmap côté client.
- Le tableau de fiabilité du dashboard (`index.html`) est rempli en JavaScript via deux appels API (7 jours et 30 jours) et fait correspondre les `station_id` avec la liste des stations déjà rendue côté serveur.
- Le script `scripts/capture_screenshots.py` utilise Playwright pour générer les captures du README. Il modifie `storage.DB_PATH` et `storage.STATIONS_FILE` à la volée (imports par valeur) et lance Flask dans un thread daemon. Si le schéma SQLite change, régénérer les captures avec `python scripts/capture_screenshots.py`.
- Les tests du dashboard utilisent `app.test_client()` et une base temporaire. Le rendu visuel réel (CSS, graphiques, responsive) est validé via Playwright dans `scripts/capture_screenshots.py`.

## Backlog design

Les pistes d'amélioration de l'interface et de la lisibilité des données sont documentées dans [`design-backlog.md`](design-backlog.md). Les deux premiers items prioritaires sont :

1. Remplacer la colonne "Disponibles" par des barres de progression colorées.
2. Ajouter un bandeau d'état global permanent avec l'état de la dernière collecte.

Avant de les implémenter, s'assurer que les tests existants dans `tests/test_dashboard_render.py` couvrent toujours le rendu des nouveaux éléments.
