# Backlog design — EV Charging Monitor

Ce fichier regroupe les pistes d'amélioration du dashboard et de la lisibilité des données. Les items sont classés par impact décroissant. Les deux premiers sont prioritaires et seront implémentés en premier.

## 1. Remplacer la colonne "Disponibles" par des barres de progression colorées

**Problème :** la colonne affiche un simple texte "2 / 4" avec une couleur de texte. Le ratio n'est pas scannable d'un coup d'œil.

**Piste :**
- Afficher une barre de progression horizontale derrière ou à la place du texte.
- Couleur : verte si dispo > 0, orange si dispo = 0 mais occupied > 0, rouge si tout est hors service / inconnu.
- Conserver le texte "2 / 4" centré dans ou à côté de la barre.
- Ajouter un tooltip au survol indiquant le détail (disponible, occupé, hors service, inconnu).

**Fichiers concernés :** `ev_monitor/templates/index.html`

## 2. Ajouter un bandeau d'état global permanent

**Problème :** l'état de la dernière collecte n'est visible que s'il y a une erreur. L'utilisateur ne sait pas si les données sont fraîches sans scruter le tableau.

**Piste :**
- Ajouter sous l'en-tête une ligne fine avec :
  - une pastille verte/orange/rouge,
  - le statut du dernier cycle ("OK", "partiel", "erreur"),
  - le nombre de stations en erreur le cas échéant,
  - l'heure du dernier check ("il y a 3 min").
- Griser ou marquer d'un icône ⚠️ les stations sans donnée depuis plus de 2 cycles.

**Fichiers concernés :** `ev_monitor/templates/index.html`, `ev_monitor/dashboard.py` (données `last_run` déjà disponibles).

## 3. Améliorer les mini-graphiques 24h

**Problème :** les graphiques empilés en barres sont petits et peu lisibles sur mobile.

**Piste :**
- Tester des sparklines en courbe lissée avec une aire colorée sous la courbe.
- Ou remplacer le graphique permanent par un indicateur tendanciel simple (flèche + évolution) avec le graphique détaillé en tooltip.

**Fichiers concernés :** `ev_monitor/templates/index.html`

## 4. Hiérarchiser le tableau principal

**Problème :** 8 colonnes de même importance créent un mur de texte.

**Piste :**
- Élargir la colonne "Station".
- Regrouper "Total / Disponibles / Dernière indispo / Dernier check" dans un bloc visuel cohérent.
- Fixer l'en-tête du tableau au défilement (`position: sticky`).

**Fichiers concernés :** `ev_monitor/templates/index.html`

## 5. Améliorer l'affichage du sens de circulation

**Problème :** les badges textuels "Aix → Nice" / "Nice → Aix" sont corrects mais peu scannables.

**Piste :**
- Ajouter une icône de flèche dans le badge.
- Ou regrouper les stations par sens avec un sous-titre de section plutôt qu'une colonne de badge.

**Fichiers concernés :** `ev_monitor/templates/index.html`

## 6. Optimiser le responsive

**Problème :** le tableau a un `min-width: 1100px`, ce qui force le défilement horizontal sur tablette.

**Piste :**
- Sur tablette et mobile, passer en cartes de station empilées verticalement.
- Chaque carte affiche : nom, opérateur, statut, barre de dispo, bouton détail.

**Fichiers concernés :** `ev_monitor/templates/index.html`

## 7. Améliorer la page de détail (`station.html`)

**Problème :** les informations sont empilées verticalement sans hiérarchie forte.

**Piste :**
- Mettre le taux de disponibilité moyen en grand en haut.
- Fusionner les cartes "Informations" et "Disponibilité moyenne".
- Ajouter une légende explicite sur le graphique principal.

**Fichiers concernés :** `ev_monitor/templates/station.html`

## 8. Uniformiser les couleurs sémantiques

**Problème :** les nuances vert/orange/rouge ne sont pas toujours identiques entre tableau, graphiques et alertes.

**Piste :**
- Définir des tokens CSS : `--color-success`, `--color-warning`, `--color-danger`, `--color-muted`.
- Utiliser ces tokens partout (badges, textes, barres, graphiques).

**Fichiers concernés :** `ev_monitor/templates/*.html`

## 9. Ajouter des indices visuels sur les opérateurs

**Problème :** l'opérateur n'apparaît pas clairement dans le tableau principal.

**Piste :**
- Afficher l'opérateur sous le nom de la station avec un badge discret.
- Éventuellement ajouter un logo opérateur si les droits le permettent.

**Fichiers concernés :** `ev_monitor/templates/index.html`

## 10. Améliorer la page Logs

**Problème :** la page est un tableau classique sans tendance temporelle.

**Piste :**
- Ajouter un mini-graphique d'évolution des erreurs/warnings sur 24h.
- Tronquer les détails techniques et les afficher au clic.

**Fichiers concernés :** `ev_monitor/templates/logs.html`
