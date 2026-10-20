# Contrat d'interface : ce que l'optimisation (MSc 4) lit chez l'équipe

L'optimisation **s'adapte aux tables déjà livrées** plutôt que d'imposer un format. Elle suit les choix de
MSc 1 :

- coordonnées en **EPSG:3035** (`x_3035`, `y_3035`, en mètres) ;
- clé **`idcar_200m`** ;
- zone d'étude **Toulouse Métropole** (`zone_communes`, 37 communes).

Les règles des décisions du kit s'appliquent telles quelles : 400 m autour du centre du carreau (décision 4)
et une option = une ligne distincte ou une station (décision 3).

Pour vérifier les données et voir ce qui est encore provisoire, depuis `optimisation/` :

```bash
python scripts/verifier_contrat.py
```

## 1. MSc 1 : livré, lu tel quel

Ces tables sont lues **en direct** dans le Lakehouse. La dernière lecture est gardée dans `data/reel/msc1/`
comme secours.

| Table du Lakehouse | Colonnes utilisées |
| --- | --- |
| `carreaux` | `idcar_200m`, `codes_communes`, `x_3035`, `y_3035`, `lat`, `lon`, `population` |
| `zone_communes` | `code_commune`, `nom` |
| `arrets` | `arret_id`, `modes`, `x_3035`, `y_3035`, `lat`, `lon` |
| `arrets_lignes` | `arret_id`, `ligne_id`, `mode` |
| `stations_partagees` | `station_id`, `operateur` (`Citiz`, `VélôToulouse`), `x_3035`, `y_3035`, `lat`, `lon` |
| `carreaux` (critères au choix, facultatif) | `menages`, `niveau_vie_moyen`, `part_menages_pauvres`, `logements_sociaux`, `menages_1_personne`, `menages_logement_collectif`, `age_25_39` |
| `carreaux_variables`, `iris` | `idcar_200m`, `code_iris`, `part_menages_sans_voiture`, `voitures_par_menage`, `commerces_alimentaires_5min`, `sante_5min`, `enseignement_5min`, `services_5min`, `gares_5min` ; `code_iris`, `nom_iris`, `type_iris` |
| `Files/brut/gtfs/<jour>/tisseo.zip` | `routes.txt`, `trips.txt`, `shapes.txt` : tracés des lignes de bus (`route_type` 3) |

Les scooters YEGO (`vehicules_libres`) ne sont pas lus : ils ne comptent pas comme option (décision 3,
notebook `03_stations`).

## 2. MSc 2 : attendu, calcul provisoire en attendant

**Table `accessibilite`**, une ligne par carreau de `carreaux` :

| Colonne | Type | Définition |
| --- | --- | --- |
| `idcar_200m` | texte | clé de `carreaux` |
| `nb_options` | entier ≥ 0 | options à 5 min (décision 3) : lignes distinctes qui s'arrêtent à 400 m ou moins, plus les stations vélo et Citiz à 400 m ou moins |
| `sous_seuil` | booléen | carreau sous le seuil de population (décision 5), grisé |
| `iris` | texte, facultatif | code IRIS, pour la liste priorisée |
| `options_pour_1000` | réel, facultatif | l'indicateur de la décision 5, pour afficher **sa carte de chaleur** (objectif 1) comme calque |

**Table `population_servie`**, facultative : elle sert à afficher **sa carte de l'objectif 2** comme calque.

| Colonne | Type | Définition |
| --- | --- | --- |
| `station_id` | texte | `arret_id` de `arrets`, ou `station_id` de `stations_partagees` |
| `population_servie` | réel ≥ 0 | habitants à 5 min de la station (décision 6 : compté pour chaque station) |

**En attendant**, `optim_mobilite/preparation.py` calcule `nb_options` avec la même règle, à partir de
`arrets`, `arrets_lignes` et `stations_partagees`. Le seuil provisoire est de **10 habitants**, la plus basse
valeur à tester d'après le kit. L'écran affiche « accessibilité provisoire ».

Les calques « carte de chaleur » et « population servie » restent **désactivés** tant que MSc 2 n'a pas livré :
on ne les recalcule pas. Dès que ses tables existent, elles remplacent le provisoire et activent les calques,
sans changer le code.

Ce qui reste à MSc 4 dans tous les cas : savoir si un carreau a **déjà une station du même type** à 400 m.
Cela sert à définir les candidats et la population nouvellement desservie.

## 3. MSc 3 : livré

La table **`scores_potentiel_msc3`** du Lakehouse a les colonnes `idcar_200m`, `score_potentiel` (0 à 1), puis
`candidat_citiz`, `citiz_present` et d'autres. Les 7 070 carreaux y sont, sans valeur vide.

Elle est lue en direct. Comme elle a été écrite par Spark avec des « deletion vectors », c'est DuckDB qui la
lit. Le score est appliqué à l'**emplacement** (décision 7) : valeur = population nouvellement desservie ×
score de l'emplacement. Une table `scores_potentiel` aux mêmes colonnes serait lue aussi.

## 4. MBA : Citiz livré, vélo et bus en attente

Le MBA a livré **`Coût citiz.xlsx`** (dernière version le 20/10 à 15 h 05, avec la réponse de Citiz sur la
redevance de stationnement) : coût complet d'une station Citiz de 2 voitures, par an, voitures
amorties sur 5 ans, recettes non déduites. Pour l'importer :

```bash
python scripts/importer_couts_mba.py "/chemin/Coût citiz.xlsx"
```

Le script lit la ligne « Coût annuel complet par station (thermique ou hybride) » de l'onglet Calcul, celle
que le classeur désigne « À DONNER À MSc 4 ».

**Table `couts`**, une ligne par type livré, en euros par station et par an :

| Colonne | Définition |
| --- | --- |
| `type` | `citiz`, `velo` ou `bus` |
| `cout_bas`, `cout_defaut`, `cout_haut` | coût complet d'une station et par an : « défaut » pour la démo, bas et haut pour la robustesse |
| `budget` | `citiz` pour Citiz, `collectivite` pour le vélo et le bus |

Les valeurs aujourd'hui :

| Type | Bas | Défaut | Haut | Source |
| --- | ---: | ---: | ---: | --- |
| Citiz | 12 197 € | 20 986 € | 26 664 € | **MBA** (`Coût citiz.xlsx`, version du 20/10) |
| Vélo | 15 000 € | 22 500 € | 30 000 € | MOCK, en attente du MBA |
| Bus | 8 000 € | 14 000 € | 20 000 € | MOCK, en attente du MBA |

Un type absent de la livraison garde sa ligne MOCK, signalée à l'écran. L'ancien format (`cout_install_*`,
`cout_fonct_1an_*`) est encore accepté.

## 5. Arbres (demande de Citiz) : attendu

**Table `arbres`**, une ligne par arbre, avec `lat` et `lon` (WGS84), ou `x_3035` et `y_3035`. Elle viendrait
de la carte fournie par Citiz ou, à défaut, du jeu ouvert « arbres d'alignement » de Toulouse Métropole.

Dès qu'elle existe, le critère « stationnement dégagé (peu d'arbres) » et son calque s'activent. Une colonne
manquante ou des coordonnées absentes ne bloquent rien : le critère reste simplement indisponible.

## Où déposer une livraison

**Dans le Lakehouse `Mobilite`, sous les noms ci-dessus.** L'application les lit en direct : une table
ajoutée ou mise à jour apparaît à la lecture suivante (10 minutes au plus, ou le bouton « Mettre à jour les
données »). Pour les coûts, le classeur Excel peut être déposé tel quel dans `Files/mba/`.

À défaut (hors ligne), les mêmes tables peuvent être déposées dans `data/reel/msc2/`, `data/reel/msc3/` ou
`data/reel/mba/`. C'est là aussi que se trouve la copie de secours de la dernière lecture de Fabric.

## Ce que l'optimisation renvoie

Deux tables reliées par `id_scenario` (voir `POWERBI.md`) :

- `scenarios` : une ligne par (budget, montant, α, fourchette), avec les indicateurs et la phrase-choc ;
- `selections` : la liste priorisée de chaque scénario.

Elles sont préfixées `PROVISOIRE_` tant qu'une brique est provisoire. Rien n'est écrit dans le Lakehouse
avant que les données soient définitives.
