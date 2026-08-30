# API Chargemap — Référence des endpoints utilisés

Ce document décrit les possibilités constatées de l'API publique Chargemap (`map.chargemap.com`) telles qu'elles sont exploitées par EV Charging Monitor. Les observations ci-dessous ont été validées par des appels réels en date du 30/08/2026.

> Aucune clé API n'est requise. Chargemap peut cependant limiter, modifier ou désactiver ces endpoints sans préavis. Ne pas s'appuyer sur des champs non documentés pour une logique critique sans vérification régulière.

---

## 1. Vue d'ensemble des endpoints

| Endpoint | Méthode | Usage dans le projet |
|----------|---------|----------------------|
| `https://map.chargemap.com/pool-detail/v2/pools/{slug}` | GET | Détails, coordonnées, connecteurs et disponibilité d'une station |
| `https://map.chargemap.com/pool-detail/v2/pools` | GET | Recherche textuelle par nom (pools communautaires) |
| `https://map.chargemap.com/mappy/charging_pools.json` | GET | Recherche par ville ou par bounding-box (opérateurs) |

---

## 2. Détails d'un pool : `pool-detail/v2/pools/{slug}`

### Requête

```http
GET https://map.chargemap.com/pool-detail/v2/pools/{slug}?locale=fr-fr
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `slug` | string | oui | Identifiant texte de la station (ex. `ionity-aire-de-cambarette-nord`) |
| `locale` | string | non | Langue de la réponse, ex. `fr-fr` |

### Réponses

#### 200 OK — pool trouvé

`Content-Type: application/json; charset=utf-8`

Retourne un objet JSON contenant les informations statiques et la disponibilité temps réel de la station.

**Champs principaux observés :**

| Champ | Type | Exemple | Description |
|-------|------|---------|-------------|
| `id` | int | `131293` | Identifiant numérique interne |
| `slug` | string | `ionity-aire-de-cambarette-nord` | Identifiant public |
| `name` | string | `IONITY - Brignoles - Aire de Cambarette Nord` | Nom affiché |
| `state` | string | `PUBLISHED` | État du pool : `PUBLISHED`, `DELETED`, `CREATING`... |
| `speed` | string | `FAST` | Vitesse de charge (`FAST`, `NORMAL`...) |
| `network` | object | — | Opérateur (`id`, `name`, `slug`, `logo_url`...) |
| `owner` | object | — | Propriétaire (`type`, `name`, `website`) |
| `street_name` | string | `Aire de Cambarette Nord` | Rue |
| `postal_code` | string | `83170` | Code postal |
| `city` | string | `Brignoles` | Ville |
| `country_code` | string | `FR` | Pays |
| `coordinates` | object | `{ "lat": "43.423878", "lon": "5.990385" }` | Coordonnées (lat/lon en string) |
| `location` | string | `HIGHWAY` | Type d'emplacement |
| `access` | string | `PUBLIC` | Accès (`PUBLIC`, restreint...) |
| `always_open` | bool | `true` | Ouvert 24h/24 |
| `indoor` | bool | `false` | En intérieur |
| `parking_free` | bool | `true` | Parking gratuit |
| `is_free` | bool | `false` | Recharge gratuite |
| `is_tesla` | bool | `false` | Station Tesla |
| `chargemap_pass_compatible` | bool | `true` | Compatible Chargemap Pass |
| `can_remote_start_charge` | bool | `true` | Démarrage à distance possible |
| `can_start_auto_charge` | bool | `false` | Charge automatique possible |
| `can_start_plug_and_charge` | bool | `true` | Plug & Charge possible |
| `description` | string | — | Description et modes de paiement |
| `amenities` | array | `["drinks", "restoration", "restroom"]` | Services à proximité |
| `schedules` | array | `[]` | Horaires d'ouverture |
| `rating` | float | `4.1765` | Note moyenne |
| `rating_count` | int | `34` | Nombre de notes |
| `statistic` | object | — | Statistiques communautaires (check-ins, commentaires...) |
| `stations` | array | — | Liste des bornes physiques (voir ci-dessous) |
| `date_created` | string ISO | `2019-05-27T15:34:03+00:00` | Date de création |
| `date_updated` | string ISO | `2026-05-18T14:48:14+00:00` | Dernière mise à jour |
| `avatar_url` | string URL | — | Logo de la station |
| `cover_url` | string URL | — | Photo de couverture |

#### 404 Not Found — pool inexistant

```json
{
  "success": false,
  "reason": "Pool with slug 'inexistant-slug-test-12345' was not found"
}
```

### Détails des bornes : tableau `stations`

Chaque élément représente une borne physique.

| Champ | Type | Description |
|-------|------|-------------|
| `id` | int | Identifiant de la borne |
| `label` | string | Libellé éventuel |
| `administrative_state` | string | État administratif (`in-service`, ...) |
| `is_free` | bool | Borne en accès gratuit |
| `authentication_methods` | array | Méthodes d'authentification (`RFID`, ...) |
| `highlighted_passes` | array | Badges mis en avant (Chargemap Pass...) |
| `third_party_passes` | array | Autres badges acceptés |
| `connectors` | array | Connecteurs disponibles (voir ci-dessous) |

### Détails des connecteurs : tableau `connectors`

| Champ | Type | Exemple | Description |
|-------|------|---------|-------------|
| `id` | int | `73162159` | Identifiant du connecteur |
| `type` | string | `COMBO_TYPE_2` | Type de connecteur (voir liste ci-dessous) |
| `power` | int | `350` | Puissance en kW |
| `voltage` | int | `920` | Tension en V |
| `intensity` | int | `500` | Intensité en A |
| `current_type` | string | `DC` | Type de courant (`DC`, `AC`) |
| `overall_state` | string | `BUSY` | État général agrégé |
| `realtime_state` | string | `UNAVAILABLE` | État temps réel |
| `is_bookable` | bool | `false` | Réservable |
| `evse_id` | int | `2056049` | Identifiant EVSE |
| `remote_identifier` | string | `"01"` | Identifiant distant |
| `is_compatible` | bool | `true` | Compatible avec le véhicule courant (contexte utilisateur) |
| `is_remote_charge_compatible` | bool | `true` | Démarrage distant compatible |
| `is_auto_charge_compatible` | bool | `false` | Charge auto compatible |
| `is_plug_and_charge_compatible` | bool | `true` | Plug & Charge compatible |

### Types de connecteurs observés

Les valeurs `type` rencontrées dans les réponses :

- `CHADEMO`
- `COMBO_TYPE_2`
- `MENNEKES_TYPE_2`
- `MENNEKES_TYPE_2_CABLE_ATTACHED`
- `DOMESTIC_TYPE_F`
- `TESLA_SUPERCHARGER_EU`
- `TESLA`

### États des connecteurs

Le code mappe les états `realtime_state` (prioritaire) ou `overall_state` vers les catégories suivantes :

| Valeur API | Catégorie projet | Signification |
|------------|------------------|---------------|
| `AVAILABLE` | `available` | Disponible |
| `BUSY` | `occupied` | Occupée |
| `UNAVAILABLE` | `occupied` | Indisponible temporairement |
| `OUT_OF_SERVICE` | `outOfService` | Hors service |
| `OUT_OF_ORDER` | `outOfService` | En panne |
| `UNKNOWN` | `unknown` | État inconnu |

### Exemple de réponse réduite

```json
{
  "slug": "ionity-aire-de-cambarette-nord",
  "name": "IONITY - Brignoles - Aire de Cambarette Nord",
  "state": "PUBLISHED",
  "coordinates": { "lat": "43.423878", "lon": "5.990385" },
  "network": { "name": "IONITY" },
  "stations": [
    {
      "administrative_state": "in-service",
      "connectors": [
        {
          "type": "COMBO_TYPE_2",
          "power": 350,
          "realtime_state": "AVAILABLE",
          "overall_state": "AVAILABLE"
        }
      ]
    }
  ]
}
```

---

## 3. Recherche par nom : `pool-detail/v2/pools`

### Requête

```http
GET https://map.chargemap.com/pool-detail/v2/pools?name={query}&locale=fr-fr
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `name` | string | oui | Terme de recherche (nom, ville, opérateur...) |
| `locale` | string | non | Langue de la réponse |

### Réponse

```json
{
  "items": [
    {
      "id": 131293,
      "slug": "ionity-aire-de-cambarette-nord",
      "name": "IONITY - Brignoles - Aire de Cambarette Nord",
      "state": "PUBLISHED",
      "coordinates": { "lat": "43.423878", "lon": "5.990385" },
      "stations": [ ... ]
    }
  ]
}
```

### Comportements observés

- La recherche est partielle (ex. `Cambarette` retourne les pools contenant ce terme).
- Le résultat inclut des pools en état `DELETED` ou `CREATING` : il faut filtrer côté client (`state == "PUBLISHED"` est recommandé).
- Le nombre de résultats semble plafonné à **20 items**.
- Les champs `stations` et `connectors` sont présents mais moins riches que l'appel direct par `slug`.

### Exemple d'appel

```bash
curl -s "https://map.chargemap.com/pool-detail/v2/pools?name=Cambarette&locale=fr-fr"
```

---

## 4. Recherche `mappy` : `mappy/charging_pools.json`

Cet endpoint couvre principalement les stations des opérateurs. Il accepte deux modes de recherche : par ville ou par bounding box.

### 4.1 Par ville

```http
GET https://map.chargemap.com/mappy/charging_pools.json?city={ville}&state=2&limit=100
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `city` | string | oui | Nom de la ville |
| `state` | int | recommandé | `2` semble correspondre aux pools publiés ; `1` inclut des pools en cours de création |
| `limit` | int | non | Nombre max de résultats (observé fonctionnel jusqu'à au moins `200`) |

### 4.2 Par bounding box

```http
GET https://map.chargemap.com/mappy/charging_pools.json?NW={lat};{lon}&SE={lat};{lon}&state=2&limit=100
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `NW` | string | oui | Coin nord-ouest, format `lat;lon` |
| `SE` | string | oui | Coin sud-est, format `lat;lon` |
| `state` | int | recommandé | Filtre d'état (voir 4.1) |
| `limit` | int | non | Limite de résultats |

### Réponse

```json
{
  "response": {
    "success": true,
    "content": {
      "count": 27,
      "items": [
        {
          "lat": 43.3995780945,
          "lng": 6.074783802,
          "type": "pool",
          "pool": { ... }
        }
      ]
    },
    "self": "mappy/charging_pools.json?city=..."
  }
}
```

### Champs du `pool` mappy

| Champ | Type | Description |
|-------|------|-------------|
| `id` | int | Identifiant interne |
| `slug` | string | Identifiant public |
| `name` | string | Nom |
| `street_name` | string | Rue |
| `postal_code` | string | Code postal |
| `city` | string | Ville |
| `country_code` | string | Pays |
| `gps_coordinates` | object | `{ "lat": ..., "lon": ... }` (flottants) |
| `network` | object | Opérateur (`id`, `name`, `logo_url`...) |
| `speed` | object | Vitesse (`id`, `icon`, `map_icon`) |
| `charging_connectors` | array | Résumé des connecteurs (voir ci-dessous) |
| `evses` | array | Liste des EVSE avec état temps réel (quand disponible) |
| `operational_status` | string | `OPERATIONAL` ou `OUT_OF_ORDER` |
| `availability_status` | string | `AVAILABLE`, `UNAVAILABLE`, `UNKNOWN` |
| `real_time_available` | bool | Indique si des données temps réel sont disponibles |
| `is_always_open` | bool | Ouvert 24h/24 |
| `is_indoor` | bool | En intérieur |
| `is_free` | bool | Recharge gratuite |
| `is_tesla` | bool | Station Tesla |
| `location_type_slug` | string | Type d'emplacement (`person`, `highway`...) |
| `amenities` | array | Services |
| `schedules` | array | Horaires |
| `statistic` | object | Statistiques communautaires |
| `last_used_time` | string ISO | Dernière utilisation |

### Résumé des connecteurs mappy

```json
[
  {
    "count": 1,
    "available_count": 1,
    "type": "DOMESTIC_TYPE_F",
    "connector_type": { "id": 6, "icon": "schuko" },
    "power_max": 3
  }
]
```

| Champ | Description |
|-------|-------------|
| `count` | Nombre total de ce type de connecteur |
| `available_count` | Nombre disponible (si temps réel) |
| `type` | Type de connecteur |
| `power_max` | Puissance max en kW |

### EVSE mappy

```json
[
  {
    "id": 2140174,
    "is_available": false,
    "realtime_state": "UNAVAILABLE"
  }
]
```

### Comportements observés

- La recherche par ville retourne des clusters (`type: "cluster"`) sans `pool.slug` : les ignorer.
- Les résultats peuvent être paginés/plafonnés côté serveur pour les requêtes anonymes ; utiliser une `limit` raisonnable.
- `gps_coordinates` utilise parfois la clé `lng` au lieu de `lon` dans certains contextes ; le code normalise les deux.

---

## 5. Stratégie de recherche combinée dans le projet

`search_stations(query)` combine les deux approches :

1. `_search_by_city(query)` appelle `mappy/charging_pools.json?city=...` pour couvrir les opérateurs.
2. `_search_by_name(query)` appelle `pool-detail/v2/pools?name=...` pour les pools communautaires.
3. Les résultats sont fusionnés par `slug`, `mappy` étant privilégié car plus riche en connecteurs.

`search_nearby(lat, lon, radius_km)` :

1. Calcule une bounding box approximative à partir du rayon.
2. Appelle `mappy/charging_pools.json?NW=...&SE=...`.
3. Filtre les résultats par distance réelle (haversine) et trie par distance.

---

## 6. Limites et points d'attention

- **Pas de documentation officielle** : ces endpoints sont internes à l'application web Chargemap. Leur comportement peut changer.
- **Pas de clé API** mais possibilité de rate-limiting par IP. Ne pas surcharger le service.
- **Champs facultatifs** : beaucoup de champs (`rating`, `schedules`, `description`, `statistic`) peuvent être `null` ou vides.
- **Coordonnées** : dans `pool-detail` elles sont des strings ; dans `mappy` ce sont des flottants.
- **États temps réel** : `realtime_state` est prioritaire sur `overall_state`. Si les deux sont absents, l'état est `unknown`.
- **Stations supprimées** : un pool `DELETED` peut toujours répondre en 200 mais avec `stations: []`.

---

## 7. Exemples d'appels curl

```bash
# Détails d'une station
curl -s "https://map.chargemap.com/pool-detail/v2/pools/ionity-aire-de-cambarette-nord?locale=fr-fr" | jq .

# Recherche par nom
curl -s "https://map.chargemap.com/pool-detail/v2/pools?name=Cambarette&locale=fr-fr" | jq .

# Recherche par ville
curl -s "https://map.chargemap.com/mappy/charging_pools.json?city=Brignoles&state=2&limit=100" | jq .

# Recherche par bounding box (Brignoles, ~10 km)
curl -s "https://map.chargemap.com/mappy/charging_pools.json?NW=43.514;5.883&SE=43.334;6.098&state=2&limit=100" | jq .
```
