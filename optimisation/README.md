# Optimisation des emplacements (MSc 4)

On choisit un budget, l'outil renvoie la carte et la liste priorisée des meilleurs emplacements pour de
nouvelles stations Citiz, ou pour des stations vélo et des arrêts de bus financés par la collectivité, sur
**Toulouse Métropole** (zone de MSc 1).

> **Deux façons de lire les données** : avec `./start.sh`, le site lit la copie locale du Lakehouse Fabric
> `Mobilite`, faite juste avant (affichage immédiat, rien ne dépend du réseau pendant la démo) ; avec
> `./start.sh --direct`, il lit le Lakehouse en direct et le relit toutes les 10 minutes ou avec le bouton
> « Mettre à jour les données ». Si Fabric ou le réseau tombe, le site repart de la copie et le signale.
> Toutes les briques de l'équipe sont livrées : plus rien n'est affiché comme « provisoire ».

## Lancer

Le plus simple : `./start.sh` à la racine du dépôt (voir le [README racine](../README.md)). À la main, depuis
`optimisation/`, avec `az login` fait sur le tenant Epitech :

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # une fois
.venv/bin/python scripts/telecharger_lakehouse.py                        # copie des tables de Fabric
OPTIM_SOURCE=local .venv/bin/streamlit run app/streamlit_app.py           # la démo, sur http://localhost:8501
```

Tests (sans réseau) : `.venv/bin/python -m pytest tests -q` (132 tests), ou `./start.sh --tests`.

**Ce que le dépôt contient** : le site (`app/`, `optim_mobilite/`, `config.toml`, `.streamlit/`), sa documentation
(`docs/`), ses tests (`tests/`) et la copie des tables (`scripts/telecharger_lakehouse.py`). Les coûts des trois
équipements, importés des classeurs du MBA (`../docs/couts/`), sont dans `data/reel/mba/couts.parquet`.

**Ce qui n'y est pas** :

- la comparaison exacte et l'export Power BI, gardés en local ;
- le notebook, publié directement dans Fabric : **`optimisation_fabric`**, dans l'espace « Hackathon Mobi ». Il
  lit le même module, copié dans `Files/optimisation/` du Lakehouse `Mobilite`.

Un scénario s'ouvre aussi par l'URL :
`http://localhost:8501/?budget=collectivite&montant=1000000&alpha=3&fourchette=haut&fond=0`.

## D'où viennent les entrées

Tout est lu dans le Lakehouse `Mobilite`, en lecture seule (`optim_mobilite/fabric.py`).

| Brique | Table ou fichier dans Fabric | Statut |
| --- | --- | --- |
| Carreaux, communes, arrêts, lignes, stations | `carreaux`, `zone_communes`, `arrets`, `arrets_lignes`, `stations_partagees` | livré |
| Tracés des lignes de bus Tisséo | `Files/brut/gtfs/<jour le plus récent>/tisseo.zip` | livré |
| IRIS de chaque carreau | `carreaux_variables`, `iris` | livré |
| Score de potentiel | `scores_potentiel_msc3` | livré |
| Raisons du score (modèle v2) | `scores_potentiel_v2` | livré |
| Accessibilité, seuil, carte de chaleur | `acces_carreau` (MSc 2 ; `accessibilite` si elle existe) | livré |
| Population servie par station | `population_servie` | pas livrée : calque désactivé |
| Coûts | table `couts`, sinon `data/reel/mba/couts.parquet` (classeurs du MBA) | livré |
| 8 critères de Citiz, places proposées, arbres | `criteres_citiz`, `places_candidates`, `arbres` (notebook 08) | livré |
| Usage mesuré des stations Citiz | `usage_stations` (relevés de `citiz_releves`) | livré |

Le détail des colonnes est dans [`docs/CONTRAT.md`](docs/CONTRAT.md).

**Une table écrite par Spark avec des « deletion vectors »** (c'est le cas du score) n'est pas lisible par
`deltalake`. Elle est alors lue par DuckDB : c'est automatique.

## Quand une nouvelle donnée arrive

- **Si elle est dans le Lakehouse**, sous un des noms ci-dessus : rien à faire. Elle apparaît à la prochaine
  lecture (10 minutes au plus, ou le bouton « Mettre à jour les données »).
- **Les classeurs de coûts** : le classeur Citiz déposé dans `Files/mba/` du Lakehouse est lu en direct. Sinon,
  `couts_mba.lire_classeur` et `couts_mba.lire_classeur_collectivite` refont `data/reel/mba/couts.parquet`
  depuis `../docs/couts/`.
- **Avant la démo** : `./start.sh`, pour que la copie soit fraîche.

Dans **Fabric**, le notebook `optimisation_fabric` de l'espace « Hackathon Mobi » lit les mêmes tables.

## La carte à calques

Dans la barre latérale, le menu **Calques de la carte** permet de superposer :

| Groupe | Calques |
| --- | --- |
| Résultat de l'optimisation (MSc 4) | stations proposées, habitants nouvellement desservis, **zones à potentiel**, places proposées, arbres autour des stations proposées |
| Offre existante (MSc 1) | stations Citiz (et leur usage mesuré), VélôToulouse, arrêts de bus, arrêts de métro, tram et train, lignes de bus Tisséo |
| Territoire (MSc 1) | population par carreau, limites des communes |
| Cartes de l'équipe | carte de chaleur et population servie (MSc 2), score de potentiel (MSc 3) |

- Un calque dont la source n'est pas livrée est désactivé, et son infobulle dit qui doit le fournir.
- Le menu **Recadrer sur une commune** zoome sur une commune.
- Les calques se choisissent aussi par l'URL, par exemple `?calques=potentiel,proposees,citiz,communes`.
- Les carreaux sous le seuil restent gris et muets, et les populations sont arrondies à la dizaine.
- Les « zones à potentiel » donnent la valeur de chaque emplacement candidat s'il était posé en premier.
  C'est le gain du premier tour du glouton.

## Zones à potentiel : modèle prédictif ou critères au choix

Dans la barre latérale, la section **« Zones à potentiel : sur quoi se baser ? »** propose trois choix :

- **Modèle prédictif** (par défaut) : le score de potentiel Citiz, appliqué à l'emplacement (décision 7).
- **Les 8 critères de Citiz** : l'indice Citiz, moyenne des 8 critères de « l'emplacement idéal » que Citiz nous
  a donnés (`optim_mobilite/criteres_citiz.py`, notebook `08_criteres_citiz`).
- **Mes critères** : un panneau par groupe, avec pour chaque critère une case, un poids (×1 à ×3) et, quand
  c'est réglable, un sens. Les groupes sont Habitants, Motorisation, Quartier, Services à 5 min, Transport,
  Stationnement et Modèle.

Le score est la moyenne pondérée des rangs des critères cochés (`optim_mobilite/criteres.py`). Il change la
carte des zones à potentiel **et** la liste des stations. Chaque critère est aussi un calque, dans « Calques de
la carte », groupe « Habitants et quartiers ».

Un réglage se partage par l'URL, par exemple :
`?score=criteres&criteres=densite:2,sans_voiture:2,niveau_vie:1:bas`.

## Comment c'est construit

```text
optim_mobilite/          le module, importable aussi depuis un notebook Fabric
  fabric.py              lecture en direct du Lakehouse (deltalake, DuckDB en secours), copie de secours
  couts_mba.py           lecture des classeurs Excel des coûts (Citiz, vélo et bus)
  criteres.py            critères au choix : registre, rang, score pondéré (et calques)
  criteres_citiz.py      les 8 critères de Citiz, la fiche d'un carreau et sa place proposée
  rentabilite.py         recette, résultat et délai de retour d'une station, d'après l'usage mesuré
  impact.py              voitures en moins, CO2, voirie libérée (ADEME), ménages modestes et sans voiture
  contrat.py             chargement (Fabric ou copie locale) et vérification des tables
  preparation.py         assemblage : stations existantes, accessibilité provisoire, tracés de bus Tisséo
  couverture.py          candidats, puis qui couvre qui à 400 m (KDTree, matrice creuse)
  equite.py              poids d'un habitant selon α
  glouton.py             glouton paresseux (avec le score de l'emplacement) et meilleur candidat seul
  exact.py               même problème en programme linéaire (PuLP + HiGHS)
  scenarios.py           liste priorisée, KPI, courbe, comparaison des α, robustesse, phrase-choc
  export.py              grille de scénarios pour Power BI
  mock.py, geo.py        coûts MOCK, projections EPSG:3035 <-> WGS84
app/streamlit_app.py     la démo
app/carte.py             les calques de la carte : sources, disponibilité, couleurs, vie privée
scripts/                 copie des tables du Lakehouse (telecharger_lakehouse.py)
tests/                   tests sur de petits cas faits main
docs/                    contrat, décisions, fiche oral, limites, Power BI
```

### Le chemin d'un scénario

1. **`contrat.charger_donnees`** lit les tables, en vérifie les colonnes, les types et les coordonnées, puis
   **`preparation.assembler`** :
   - repère pour chaque carreau les stations Citiz, vélo et bus existantes à 400 m ;
   - prend l'accessibilité, le score et les coûts de l'équipe, ou leur version provisoire.
2. **`couverture.construire`** est calculé **une fois** par budget :
   - les candidats : carreaux habités, au-dessus du seuil, sans station du type à 400 m (sur une ligne de bus
     Tisséo pour le bus) ;
   - qui couvre qui à 400 m, rangé dans une matrice creuse.
3. **`equite.poids`** donne à chaque habitant pas encore desservi le poids `1 + α / (1 + nombre d'options)`.
4. **`glouton.optimiser`** prend à chaque tour le candidat au meilleur ratio
   *score × poids des habitants gagnés / coût* qui rentre dans le budget, puis retire ces habitants.
5. **`scenarios.resoudre`** en fait la liste priorisée et les indicateurs.

Seuls les étapes 3 à 5 tournent quand on bouge un curseur.

## Documentation pour l'oral

- [`../docs/business_plan.md`](../docs/business_plan.md) : les chiffres du business plan et de l'impact.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) : chaque choix et pourquoi.
- [`docs/ORAL.md`](docs/ORAL.md) : l'algorithme en 3 phrases, la démo, les questions du jury.
- [`docs/LIMITES.md`](docs/LIMITES.md) : les limites assumées.
- [`docs/CONTRAT.md`](docs/CONTRAT.md) : ce que j'attends de chaque rôle.
- [`docs/POWERBI.md`](docs/POWERBI.md) : le rapport Power BI sur la grille précalculée.
