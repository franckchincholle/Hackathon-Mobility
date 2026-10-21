# Hackathon Mobility : où ouvrir les prochaines stations Citiz

Défi Epitech x Citiz x Microsoft Fabric, sur Toulouse Métropole. Le projet aide Citiz, coopérative
d'autopartage, à choisir où ouvrir ses prochaines stations. Pour un budget donné, il propose les
emplacements, chiffre ce qu'ils coûtent et rapportent, et mesure leur impact : habitants desservis,
voitures en moins, CO2 évité.

## Lancer le site 

```bash
./start.sh
```

Le script installe l'environnement Python au premier lancement, ouvre la session Azure si besoin,
copie les tables de Fabric, puis lance le site et affiche son adresse (en général
<http://localhost:8501>). Il faut Python 3.12 ou plus et, sauf hors ligne, Azure CLI (`az`) avec un
compte du tenant Epitech. Relancé, il ne réinstalle rien.

| Option | Effet |
| --- | --- |
| `--hors-ligne` | sans Azure ni copie : le site part de la dernière copie (le choix de l'oral) |
| `--direct` | le site lit Fabric en direct, plus lent au premier affichage |
| `--tests` | lance les tests du site |
| `--aide` | affiche l'aide |

## Structure

| Dossier | Rôle |
| --- | --- |
| `donnees/` | MSc 1 : notebooks Fabric de collecte, bibliothèque de variables, description des Lakehouses |
| `cartes/` | MSc 2 : notebook des cartes d'accessibilité |
| `modele/` | MSc 3 : le modèle prédictif du potentiel (v2) et ses résultats, le modèle sémantique Power BI |
| `optimisation/` | MSc 4 : site d'optimisation des emplacements ([son README](optimisation/README.md)) |
| `docs/` | business plan |
| `presentation/` | support de la soutenance |

## Relancer les données dans Fabric

Dans l'espace Fabric « Hackathon Mobi », exécuter `01_carreaux`, puis `02_arrets`, `03_stations` et
`05_variables_carreaux`, puis `06_projets_transport`, `07_projections_population` et `08_criteres_citiz`.
Le jeu actif de la bibliothèque de variables `parametres_mobilite` choisit la zone (par défaut Toulouse
Métropole dans le Lakehouse `Mobilite`, « occitanie » pour la région dans `MobiliteOccitanie`) et vaut
pour tout l'espace : un territoire à la fois, puis remettre le jeu par défaut. Depuis ce dépôt,
`fab import` puis `fab job run` sur chaque dossier `donnees/*.Notebook`.

## Équipe

| Rôle | Mission | Membre |
| --- | --- | --- |
| MSc 1 | Données : collecte, Lakehouses Fabric | |
| MSc 2 | Cartes et accessibilité | |
| MSc 3 | Modèle prédictif du potentiel | |
| MSc 4 | Optimisation des emplacements, site de démonstration | |
| MBA | Coûts, business plan | |

## Pour aller plus loin

- [SOURCES.md](SOURCES.md) : l'origine de chaque donnée.
- [docs/business_plan.md](docs/business_plan.md) : le business plan.
- [presentation/](presentation/) : le support de la soutenance.
