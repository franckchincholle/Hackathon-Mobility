Défi Hackathon Mobility Cityz/Microsoft

## Données

- Transports : GTFS des réseaux qui desservent la zone, trouvés dans le catalogue de transport.data.gouv.fr, et TER du GTFS SNCF, dans les tables `arrets` (arrêts dédoublonnés) et `arrets_lignes`.
- Stations partagées : GBFS des systèmes de la zone, trouvés dans le même catalogue, et des 15 réseaux Citiz, dans les tables `stations_partagees`, `citiz_stations` et `vehicules_libres`.
- Population : carreaux de 200 m de l'INSEE (Filosofi 2021, insee.fr/fr/statistiques/8735162) et communes de geo.api.gouv.fr, dans les tables `carreaux` (zone d'étude), `carreaux_france` et `zone_communes` ; motorisation des ménages par IRIS (recensement 2022, insee.fr/fr/statistiques/8647012, contours IGN) dans les tables `iris`, `carreaux_variables` et `carreaux_france_variables`.
- Équipements : base permanente des équipements 2025 de l'INSEE (insee.fr/fr/statistiques/8217525), comptés par famille dans chaque carreau et à 5 minutes à pied dans `carreaux_variables` et `carreaux_france_variables`, et placés sur la carte dans `equipements`.
- Projets : stations de la ligne C du métro et du prolongement de la ligne B jusqu'à Labège, tirées de Wikidata, dans les tables `projets_arrets` et `projets_lignes`.
- Usage Citiz : le notebook `04_collecte_citiz` relève le flux `vehicle_status` toutes les 10 minutes dans la table `citiz_releves` du Lakehouse `Mobilite`, jusqu'au 21 octobre au soir.
- Relancer : dans l'espace Fabric « Hackathon Mobi », exécuter `01_carreaux`, puis `02_arrets`, `03_stations` et `05_variables_carreaux`, puis `06_projets_transport` ; le jeu actif de la bibliothèque de variables `parametres_mobilite` choisit la zone (par défaut Toulouse Métropole dans le Lakehouse `Mobilite`, « occitanie » pour la région dans `MobiliteOccitanie`) ; depuis ce dépôt, `fab import` puis `fab job run` sur chaque dossier `donnees/*.Notebook`.
