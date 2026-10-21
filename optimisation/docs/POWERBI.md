# Utiliser les résultats dans Power BI

Power BI ne recalcule rien : il filtre une grille de scénarios déjà optimisés.

## Les données

Elles viennent de deux sources possibles :

- en local, avec `precalculer_powerbi.py` (gardé en local par MSc 4), qui écrit dans `sorties/powerbi/` (en
  CSV UTF-8 et en Parquet) ;
- dans Fabric, **plus tard**, avec la dernière cellule du notebook `optimisation_fabric` de l'espace
  (`ECRIRE = True`), qui écrit les tables Delta `optim_scenarios` et `optim_selections`. Rien ne sera écrit
  avant que les données soient définitives. Tant qu'une brique est provisoire, les fichiers locaux sont
  préfixés `PROVISOIRE_`.

| Table | Grain | Colonnes clés |
| --- | --- | --- |
| `scenarios` | 1 ligne par (budget_type, budget, alpha, fourchette bas / defaut / haut) : 882 lignes | `id_scenario`, `nb_stations`, `cout_total`, `habitants_nouveaux`, `habitants_sans_transport_nouveaux`, `carreaux_sans_transport_gagnes`, `part_stations_robustes`, `phrase` |
| `selections` | 1 ligne par station proposée dans un scénario | `id_scenario`, `rang`, `equipement`, `commune`, `iris`, `lon`, `lat`, `cout`, `population_nouvelle`, `cout_cumule`, `population_cumulee`, `retenue_bas_et_haut` |

## Le modèle

- Relation `scenarios[id_scenario]` (1) → `selections[id_scenario]` (plusieurs), filtrage simple.
- Segments, tous sur `scenarios` et en **sélection unique** : `budget_type`, `budget`, `alpha`, `fourchette`.

## Les visuels

1. Une **carte** (Azure Maps ou carte de base) : latitude `selections[lat]`, longitude
   `selections[lon]`, légende `equipement`, infobulle `rang` et `population_nouvelle`.
2. Des **cartes de KPI** : `nb_stations`, `cout_total`, `habitants_nouveaux`,
   `habitants_sans_transport_nouveaux`.
3. Une **zone de texte dynamique** : la mesure `Phrase = SELECTEDVALUE(scenarios[phrase])`.
4. Une **table** : `rang`, `equipement`, `commune`, `iris`, `cout`, `population_nouvelle`,
   `cout_cumule`, `population_cumulee`, triée par `rang`.
5. Une **courbe budget → habitants** : axe X `scenarios[budget]`, axe Y `habitants_nouveaux`. Le segment
   `budget` doit être désactivé pour ce visuel (Modifier les interactions).
