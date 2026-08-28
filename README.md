# Surveillance bornes Chademo — Autoroute A8

Monitoring de la disponibilité des bornes de recharge **Chademo** sur les stations d’autoroute entre **Saint-Maximin** et **Cannes**, via les API Chargemap.

## Fonctionnalités

- Liste statique de stations validées (`stations_validated.json`).
- Collecte automatique de la disponibilité toutes les 5 minutes.
- Choix du type de connecteur surveillé par station (Chademo par défaut, ou Combo CCS, Type 2…).
- Ajout de station depuis le dashboard : recherche par nom ou ville (sans avoir à connaître le slug Chargemap).
- Modification d'une station existante depuis le dashboard (nom, opérateur, adresse, sens, connecteur, ordre d'affichage).
- Tri du tableau par sens de circulation et ordre d'affichage personnalisable.
- Page d'aide intégrée (`/aide`).
- Stockage historique dans SQLite (`ev_monitoring.db`).
- Dashboard web local (`http://127.0.0.1:5000`) avec tableau de bord, mini histogrammes de disponibilité sur 24h par station, et graphiques d’historique détaillés.

## Stations surveillées

| Opérateur | Adresse | Chademo |
|-----------|---------|---------|
| IONITY | A8, Aire de Cambarette Nord, 83170 Brignoles | 1 |
| TotalEnergies | La Provençale, 83170 Brignoles | 2 |
| IONITY | La Provençale, 83550 Vidauban | 1 |
| TotalEnergies | A8 - Nice/Aix, 83550 Vidauban | 2 |
| TotalEnergies | 1211 Chemin du Ferrandou, 06250 Mougins | 2 |
| IONITY | A8, Aire de Bréguières Nord, 06250 Mougins | 1 |

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Aucune clé API n'est requise pour l'application principale. Les variables ci-dessous sont optionnelles.

Créer un fichier `.env` à la racine si besoin :

```env
MONITOR_INTERVAL_MINUTES=5
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=5000
```

### Ajuster la fréquence de collecte

Par défaut : toutes les 5 minutes. Pour changer, ajouter dans `.env` :

```env
MONITOR_INTERVAL_MINUTES=10
```

## Lancer le monitoring

```bash
source .venv/bin/activate
python run.py
```

Puis ouvrir : http://127.0.0.1:5000

## Déploiement avec Docker / Dockge

Une image Docker est publiée automatiquement sur GitHub Container Registry (GHCR).

### Avec Dockge

1. Dans Dockge, cliquer sur **+ Compose** et nommer la stack `ev-charging-monitor`.
2. Coller le contenu de [`compose.yaml`](compose.yaml).
3. Déployer la stack.
4. Accéder au dashboard : `http://<ip-du-thinkcentre>:5000`.

> L’historique est stocké dans le dossier `data/` (`ev_monitoring.db`) ainsi que la liste des stations (`stations_validated.json`). Ce dossier est monté en volume dans le conteneur.

### Avec Docker CLI

```bash
# Authentification GHCR (une fois)
docker login ghcr.io -u <github-username> -p <token-read-packages>

# Lancement
mkdir -p data
docker run -d \
  --name ev-charging-monitor \
  -e DASHBOARD_HOST=0.0.0.0 \
  -e DB_PATH=/app/data/ev_monitoring.db \
  -v $(pwd)/data:/app/data \
  -p 5000:5000 \
  --restart unless-stopped \
  ghcr.io/<github-username>/ev-charging-monitor:latest
```

### Builder l’image localement

```bash
docker build -t ev-charging-monitor .
docker run -d \
  --name ev-charging-monitor \
  -v $(pwd)/data:/app/data \
  -p 5000:5000 \
  ev-charging-monitor
```

### Mettre à jour l’image sans perdre l’historique

L’historique est conservé dans `data/ev_monitoring.db` et la liste des stations dans `data/stations_validated.json`, tous deux montés en volume persistant via `data/`. Pour mettre à jour vers la dernière image :

```bash
docker compose pull
docker compose up -d
```

⚠️ **Ne jamais utiliser `docker compose down -v`** : le `-v` supprimerait le volume et donc toute l’historique ainsi que la liste des stations.

Pour réinitialiser volontairement la base et la liste des stations :

```bash
docker compose down
rm data/ev_monitoring.db data/stations_validated.json
docker compose up -d
```

## Modifier la liste des stations

La liste des stations surveillées est la source de vérité `stations_validated.json`. Pour la modifier :

1. Éditer `stations_validated.json` (ou `data/stations_validated.json` sous Docker).
2. Supprimer `ev_monitoring.db` (ou `data/ev_monitoring.db` sous Docker) pour réinitialiser la base.
3. Relancer `python run.py` (ou redémarrer le conteneur).

Il est aussi possible d'ajouter ou de modifier une station directement depuis le dashboard via la recherche Chargemap.

## Structure

```
.
├── .env                            # variables d'environnement optionnelles
├── .env.example
├── requirements.txt
├── run.py                          # point d’entrée
├── stations_validated.json         # liste des stations par défaut (embarquée dans l'image Docker)
├── ev_monitoring.db                # base SQLite (générée)
├── data/                           # volume Docker persistant (DB + stations)
├── compose.yaml                    # stack Docker Compose de production
├── Dockerfile                      # image de production
├── .dockerignore
├── README.md
├── AGENTS.md
├── design-backlog.md
└── ev_monitor/                     # package Python principal
    ├── __init__.py
    ├── config.py                   # chargement de la configuration/env
    ├── chargemap_client.py         # client API Chargemap
    ├── storage.py                  # accès SQLite (stations + logs)
    ├── monitor.py                  # scheduler de collecte périodique
    ├── dashboard.py                # application Flask + routes + templates filters
    └── templates/
        ├── index.html              # tableau de bord principal
        ├── station.html            # page de détail d'une station
        ├── logs.html               # page des logs
        └── aide.html               # page d'aide utilisateur
```

## Tests

Une suite de tests pytest est disponible dans le répertoire `tests/`.

```bash
source .venv/bin/activate
pytest
```

Les tests vérifient le rendu HTML des pages, les réponses JSON des API, les filtres Jinja2 et la couche SQLite. Ils utilisent une base temporaire et n'effectuent aucun appel réseau.

## Consommation API

Avec 6 stations et un cycle toutes les 5 minutes :

- 6 appels / cycle à l'API Chargemap
- 72 appels / heure
- ~1 728 appels / jour

L'API Chargemap est utilisée sans clé API pour les endpoints `mappy` et `pool-detail` ; reste raisonnable sur la fréquence pour éviter d'être limité.
