# Surveillance bornes Chademo — Autoroute A8

Monitoring de la disponibilité des bornes de recharge **Chademo** sur les stations d’autoroute entre **Saint-Maximin** et **Cannes**, via les API TomTom.

## Fonctionnalités

- Liste statique de stations validées (`stations_validated.json`).
- Collecte automatique de la disponibilité Chademo toutes les 5 minutes.
- Stockage historique dans SQLite (`ev_monitoring.db`).
- Dashboard web local (`http://127.0.0.1:5000`) avec tableau de bord et graphiques d’historique.

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

Créer un fichier `.env` à la racine :

```env
TOMTOM_API_KEY=ta_clef_api
```

> Ne jamais commiter ce fichier.

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
2. Coller le contenu de [`compose.yaml`](compose.yaml) en remplaçant `OWNER` par ton nom d’utilisateur GitHub.
3. Renseigner la variable `TOMTOM_API_KEY`.
4. Déployer la stack.
5. Accéder au dashboard : `http://<ip-du-thinkcentre>:5000`.

### Avec Docker CLI

```bash
# Authentification GHCR (une fois)
docker login ghcr.io -u <github-username> -p <token-read-packages>

# Lancement
mkdir -p data
docker run -d \
  --name ev-charging-monitor \
  -e TOMTOM_API_KEY=ta_clef_api \
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
  -e TOMTOM_API_KEY=ta_clef_api \
  -v $(pwd)/data:/app/data \
  -p 5000:5000 \
  ev-charging-monitor
```

## Modifier la liste des stations

1. Éditer `stations_validated.json`.
2. Supprimer `ev_monitoring.db` pour réinitialiser la base.
3. Relancer `python run.py`.

Pour générer une nouvelle liste depuis TomTom :

```bash
python discover_candidates.py   # génère stations_candidates.json
python validate_candidates.py   # génère stations_validated.json
```

Puis valider/modifier `stations_validated.json` avant de relancer le monitoring.

## Structure

```
.
├── .env                            # clé API (non versionnée)
├── .env.example
├── requirements.txt
├── run.py                          # point d’entrée
├── stations_validated.json         # liste des stations surveillées
├── discover_candidates.py          # script de découverte
├── validate_candidates.py          # validation Chademo
├── ev_monitoring.db                # base SQLite (générée)
├── ev_monitor/
│   ├── config.py
│   ├── tomtom_client.py
│   ├── storage.py
│   ├── monitor.py
│   ├── dashboard.py
│   └── templates/
│       ├── index.html
│       └── station.html
└── README.md
```

## Consommation API

Avec 6 stations et un cycle toutes les 5 minutes :

- 6 appels / cycle
- 72 appels / heure
- ~1 728 appels / jour

Vérifie les quotas de ton plan TomTom et ajuste `MONITOR_INTERVAL_MINUTES` si besoin.
