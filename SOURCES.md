# Sources des données

Cette liste donne l'origine de chaque donnée utilisée par le projet, comme le demande le kit du hackathon. Les sources ont été consultées en octobre 2026, et les données collectées sont chargées dans le Lakehouse `Mobilite` de l'espace Fabric « Hackathon Mobi ». La colonne « Utilisé par » donne la table du Lakehouse ou le fichier du dépôt qui s'en sert.

## Transports

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| transport.data.gouv.fr | Catalogue national des données de transport (API), qui donne les GTFS et les GBFS de la zone | <https://transport.data.gouv.fr/api/datasets> | consulté en octobre 2026 | Licence Ouverte Etalab 2.0 | `reseaux`, `stations_partagees` |
| Réseaux qui desservent la zone (Tisséo, liO Occitanie et autres) | GTFS de chaque réseau, sans les réseaux que le catalogue classe seulement scolaires | adresse de chaque fichier lue dans le catalogue | horaires du mardi de référence, le plus chargé des 8 semaines qui suivent le chargement (octobre 2026) | selon le producteur (voir transport.data.gouv.fr) | `arrets`, `arrets_lignes`, `reseaux` |
| SNCF | GTFS national (TGV, Intercités, TER), réduit aux TER, trains et cars | <https://www.data.gouv.fr/api/1/datasets/r/9ae758ec-cd7a-40cd-a890-bb3963224942> | même mardi de référence | selon le producteur (voir transport.data.gouv.fr) | `arrets`, `arrets_lignes`, `reseaux` |
| Opérateurs de véhicules partagés (VélôToulouse, YEGO, Clem, Dott et autres) | GBFS des systèmes de la zone et des systèmes déclarés pour toute la France | adresse de chaque flux lue dans le catalogue | état relevé au chargement, octobre 2026 | selon le producteur (voir transport.data.gouv.fr) | `stations_partagees`, `vehicules_libres` |

## Population

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| INSEE | Filosofi 2021, carreaux de 200 m : population, ménages, revenus, âges, logements | <https://www.insee.fr/fr/statistiques/8735162> ; fichier <https://www.insee.fr/fr/statistiques/fichier/8735162/Filosofi2021_carreaux_200m_csv.zip> | 2021 | Licence Ouverte Etalab 2.0 | `carreaux`, `carreaux_france` |
| geo.api.gouv.fr | Communes de la zone avec leur intercommunalité, leur département, leur région et leur contour ; liste des départements | <https://geo.api.gouv.fr> ; <https://geo.api.gouv.fr/departements> | consulté en octobre 2026 | Licence Ouverte Etalab 2.0 | `zone_communes`, `projections_population` |
| INSEE | Recensement 2023, logements par IRIS : ménages, voitures, stationnement réservé | <https://www.insee.fr/fr/statistiques/9061333> ; fichier <https://api.insee.fr/melodi/file/DS_RP_LOGEMENT_PRINC_IRIS_2023/PARQUET> | recensement 2023, publié le 20/10/2026, géographie au 1er janvier 2025 | Licence Ouverte Etalab 2.0 | `iris`, `carreaux_variables`, `carreaux_france_variables` |
| IGN | Contours des IRIS (couche `STATISTICALUNITS.IRIS:contours_iris`, service WFS) | <https://data.geopf.fr/wfs/ows> | version en ligne au chargement, millésime non précisé | Licence Ouverte Etalab 2.0 | `iris` |
| INSEE | Projections de population Omphale 2022, scénario central, totaux par département | <https://www.insee.fr/fr/statistiques/6652134> ; fichier <https://www.insee.fr/fr/statistiques/fichier/6652134/projections_scenario_central.xlsx> | Omphale 2022, années 2018 à 2070, hypothèses de 2021 | Licence Ouverte Etalab 2.0 | `projections_population` |
| INSEE | Même projection, détail par tranche d'âge | <https://www.insee.fr/fr/statistiques/7747107> ; fichier <https://www.insee.fr/fr/statistiques/fichier/7747107/donnees_det_Central.xlsx> | Omphale 2022, années 2018 à 2070, hypothèses de 2021 | Licence Ouverte Etalab 2.0 | `projections_population` |

## Équipements et emplois

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| INSEE | Base permanente des équipements (BPE) : commerces, services, santé, enseignement, sport... | <https://www.insee.fr/fr/statistiques/8217525> ; fichier <https://www.insee.fr/fr/statistiques/fichier/8217525/BPE25.parquet> | 2025 | Licence Ouverte Etalab 2.0 | `equipements`, `carreaux_variables`, `carreaux_france_variables` |
| INSEE, sur data.gouv.fr | Répertoire Sirene, stock des établissements : établissements employeurs actifs et leur tranche d'effectif salarié | <https://www.data.gouv.fr/api/1/datasets/r/a29c1297-1f92-4e2a-8f6b-8c902ce96c5f> | fichier du mois au chargement (mise à jour mensuelle), effectifs au 31/12/2024 | Licence Ouverte Etalab 2.0 | `carreaux_variables`, `carreaux_france_variables` |
| INSEE, sur data.gouv.fr | Géolocalisation des établissements du répertoire Sirene | <https://www.data.gouv.fr/api/1/datasets/r/672007af-0146-491f-835c-8314d63fa44e> | fichier du mois au chargement (mise à jour mensuelle) | Licence Ouverte Etalab 2.0 | `carreaux_variables`, `carreaux_france_variables` |

## Projets

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| Wikidata | Stations de la ligne C du métro (Q110876443), nouvelles stations du prolongement de la ligne B jusqu'à Labège (Q56309372 et Q56309366), autres stations marquées « en construction » (P5817) | <https://query.wikidata.org/sparql> | consulté en octobre 2026 | CC0 | `projets_arrets`, `projets_lignes` |
| Ville de Toulouse | Annonces des projets : ligne C (27 km, 21 stations, mise en service fin 2028), prolongement de la ligne B (2,7 km jusqu'à Labège) | non précisé | non précisé | non précisé | `projets_lignes` (colonne `source`) |

## Citiz

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| Citiz, 15 réseaux régionaux publiés sur transport.data.gouv.fr | GBFS : toutes les stations Citiz de France | Citiz Occitanie : <https://www.data.gouv.fr/api/1/datasets/r/a73a8d89-a43e-4d9b-883d-854b5864a4bf> ; les 14 autres adresses sont dans `FLUX_CITIZ` (notebooks `03_stations` et `04_collecte_citiz`) | état relevé au chargement, octobre 2026 | selon le producteur (voir transport.data.gouv.fr) | `citiz_stations` |
| Citiz, mêmes 15 réseaux | GBFS, flux `vehicle_status` relevé toutes les 10 minutes : état de chaque voiture | mêmes adresses | relevés jusqu'au 21/10/2026 au soir | selon le producteur (voir transport.data.gouv.fr) | `citiz_releves`, et l'occupation qui en est tirée dans `usage_stations` ; JSON brut dans `Files/brut/citiz/vehicle_status/` |

## Coûts

Les hypothèses viennent des onglets « Hypothèses » des deux classeurs du MBA, rangés dans `docs/couts/` (voir Fichiers de travail). Leurs coûts annuels d'une station Citiz, d'un arrêt de bus et d'une station vélo alimentent la table `couts` (`optimisation/data/reel/mba/couts.parquet`). Les références entre parenthèses (P1, B1, V1...) sont celles des classeurs.

Coût d'une station Citiz (`docs/couts/Cout_citiz.xlsx`) :

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| Genevois français | Convention de déploiement de l'autopartage avec Citiz, annexe 1 : 2 voitures par station (P1), boîtier 4 000 € HT (P3), frais fixes de Citiz de 250 € par mois et par voiture (R4) | <https://genevoisfrancais.org/wp-content/uploads/CS2023_03.2-MAJ-CONVENTION-DEPLOIMENT-AUTOPARTAGE_annexe-1.pdf> | valable jusqu'au 31/10/2024 | non précisé | `couts` |
| Genevois français | Convention d'utilisation de l'autopartage, annexe : voiture Citiz facturée 750 € TTC par mois (R2) | <https://genevoisfrancais.org/wp-content/uploads/CS2021_23.3-AUTOPARTAGE_ConventionUtilisation_Annexe.pdf> | 2021 | non précisé | `couts` (repère de vérification) |
| Genevois français | Dossier de presse du lancement de Citiz, 11 octobre 2016 : aménagement de la place 1 200 € (P2), voiture à 710 € par mois (R3) | <https://v1.genevoisfrancais.org/sites/arc/files/fichiers/espace-presse/13-CommuniquesPresse2016/dossier-presse-arc_11octobre2016.pdf> | 2016 | non précisé | `couts` |
| Cerema | Atelier covoiturage et autopartage : voiture de 12 000 à 20 000 € (P4 bas), amortie sur environ 5 ans (P5) | <https://www.cerema.fr/system/files/documents/2020/12/ensemble_vers_la_competence_mobilite_-_atelier_covoiturage-autopartage.pdf> | 2020 | non précisé | `couts` |
| Euromotor | Toyota Yaris 2026, prix et fiche technique : 24 490 € (P4 défaut), 4,1 à 4,5 L/100 km (P11) | <https://euromotor.fr/blog/toyota-yaris-2026-prix-fiche-technique-avis/> | 2026 | non précisé | `couts` |
| L'argus | Prix du neuf de la Toyota Yaris Affaires : 26 500 € (P4 haut) | <https://www.largus.fr/prix-du-neuf/toyota/yaris-affaires.html> | non précisé | non précisé | `couts` |
| MoneyVox | Primes d'assurance auto tous risques : 610, 1 102 et 2 237 € par an (P7) | <https://www.moneyvox.fr/assurance/actualites/104708/assurance-auto-payez-vous-plus-que-la-moyenne-en-2025> | 2025 | non précisé | `couts` |
| Fiches-auto | Budget auto en chiffres : entretien de 44 € par mois (P8) | <https://www.fiches-auto.fr/articles-auto/chiffres-de-l-auto/s-983-budget-auto-en-chiffres.php> | 2025 | non précisé | `couts` |
| Région wallonne (CeMathèque) | Guide sur l'autopartage : rentabilité autour de 20 000 à 24 000 km par an (P10) | <https://mobilite.wallonie.be/files/cematheque/cematheque_0053.pdf> | 2022 | non précisé | `couts` |
| prix-carburant.eu | Prix moyen national du SP95-E10 : 2,147 € par litre (P12) | <https://prix-carburant.eu/article/prix-carburants-2026-10-12> | 12/10/2026 | non précisé | `couts` |
| Citiz Occitanie | Réponse de Citiz à l'équipe : aménagement parfois pris en charge par la collectivité (P2 bas), redevance de stationnement de 0 à 1 500 € par an (P13), voiture rentable entre 700 et 900 € de recettes par mois (R5) | sans adresse (échange avec l'équipe) | 20/10/2026 | non précisé (échange privé) | `couts` |
| La Gazette du Midi | Article sur les 15 ans de Citiz Occitanie : 2 M€ de chiffre d'affaires pour 200 voitures (R1) | <https://gazette-du-midi.fr/au-sommaire/entreprises/citiz-occitanie-15-ans-apres-l-autopartage-continue-de-seduire-les-toulousains> | 2024 | non précisé | `couts` (repère de vérification) |
| Beev | Coût d'une borne de recharge en entreprise : borne 22 kW de 3 300 à 4 000 € HT (P14), installation de 2 500 à 5 000 € (P15) | <https://www.beev.co/blog/borne-de-recharge/cout-installation-borne-entreprise/> | 2024 | non précisé | classeur seulement (option station électrique, absente de `couts`) |
| Niort Agglo | Délibération : bornes des stations Citiz à la charge de la collectivité (P15) | <https://www.niortagglo.fr/deliberations-agglo/CA_131123/C33-11-2023-19.pdf> | 2023 | non précisé | classeur seulement (option station électrique) |

Coût d'un arrêt de bus et d'une station vélo (`docs/couts/Cout_bus_velo.xlsx`) :

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| Commune belge (Fléron selon le classeur, document publié sur beyne-heusay.be) | Tableau de bord, chiffrage de voirie : quai bus 5 500 € HT (B1), arrêt accessible 8 750 € HT (B2), abribus 2 200 € (B3) | <https://beyne-heusay.be/sites/default/files/documents/news/Tableau-de-bord%20.pdf> | 2023 | non précisé | `couts` (bus) |
| Made in Marseille | Mise en accessibilité du réseau RTM : 83,5 M€ sur 10 ans (B4), environ 2 650 arrêts (B5) | <https://madeinmarseille.net/urbanisme-marseille/transport-2/12045-rtm-transport-acces-mobilite-reduite/> | 2016 | non précisé | `couts` (bus) |
| Commune de Lesparre-Médoc | Durée des amortissements en nomenclature M57 : installations de voirie sur 20 ans (B6) | <https://www.medias.lesparre-medoc.fr/335-Duree-des-amortissements-en-M57.pdf> | 2023 | non précisé | `couts` (bus) |
| Annemasse Agglo | Acte BC_2025_0020 : 2 quais accessibles avec abribus pour 13 518 € HT (B7, contrôle) | <https://www.annemasse-agglo.fr/sites/default/files/actes-administratifs/BC_2025_0020.pdf> | 2025 | non précisé | `couts` (bus) |
| France Bleu | Marché VélôToulouse renouvelé à JCDecaux : 97 M€ sur 12 ans (V1) | <https://www.francebleu.fr/infos/transports/velotoulouse-le-marche-renouvele-a-jc-decaux-une-flotte-de-velos-electriques-bientot-deployee-9168605> | 2023 | non précisé | `couts` (vélo) |
| JCDecaux | Communiqué sur le contrat VélôToulouse : 12 ans (V2), extension possible à 3 825 vélos et 475 stations (V4) | <https://www.jcdecaux.com/press-releases/jcdecaux-wins-contract-city-toulouses-self-service-bikes-12-years-renewing-its> | 2023 | non précisé | `couts` (vélo) |
| JCDecaux | Communiqué sur le déploiement avec Tisséo Collectivités et Toulouse Métropole : 3 300 vélos (V3), 400 stations (V5) | <https://www.jcdecaux.fr/communiques-de-presse/en-collaboration-avec-tisseo-collectivites-et-toulouse-metropole-jcdecaux> | 2024 | non précisé | `couts` (vélo) |
| Banque des Territoires (enquête du GART) | Vélos en libre-service : 2 000 à 3 000 € par vélo et par an (V6) | <https://www.banquedesterritoires.fr/velos-en-libre-service-un-bilan-coutsavantages-juge-globalement-equilibre> | 2010 | non précisé | `couts` (vélo) |
| Élus Verts de Toulouse (archives EELV) | Réponse de Philippe Goirand au vœu sur les vélos en libre-service : 2 000 € par vélo et par an pour l'ancien contrat (V8) | <https://archives.eelv.fr/elusverts.fr/www.toulouse.elusverts.fr/IMG/pdf/Reponse_Philippe_Goirand_Voeu_VLS.pdf> | vers 2013 | non précisé | `couts` (vélo, repère) |
| m2a (Mulhouse) | Délibération 2366B : station neuve de 10 vélos entre 40 000 et 50 000 € (V9) | <https://www.m2a.fr/wp-content/uploads/2024/07/2366B.pdf> | 2024 | non précisé | `couts` (vélo, repère) |

Hypothèses de l'équipe, sans source : P6 (boîtier et aménagement amortis sur 5 ans), P9 (coefficient d'usure de 1,5), V7 (10 vélos par station).

## Business et impact

Ces chiffres servent à `docs/business_plan.md`. Les pages en ligne ont été lues le 20/10/2026.

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| Citiz Occitanie | Fiche tarifs des particuliers : abonnement, prix à l'heure, au jour et au kilomètre | <https://occitanie.citiz.coop/uploads/sites/10/2026/10/2611_OCCITANIE-B2C-fiche_tarifs-A5-IMPRESSION.pdf> | en vigueur au 01/11/2026 | non précisé | `docs/business_plan.md` |
| Citiz Occitanie | Offres combinées : Pass Tisséo + Citiz à 63,10 € par mois | <https://occitanie.citiz.coop/tarifs/les-offres-combinees-facilitent-votre-mobilite/> | lu le 20/10/2026 | non précisé | `docs/business_plan.md` |
| Citiz Occitanie | Contrat professionnel : part sociale de 750 €, 15 parts financent un véhicule | <https://occitanie.citiz.coop/uploads/sites/10/2026/07/2026_1-CITIZ-OCC_Contrat-Professionnel-1.pdf> | 2026 | non précisé | `docs/business_plan.md` |
| Citiz Occitanie | Page « Citiz en Occitanie » : plus de 220 véhicules, près de 6 500 conducteurs | <https://occitanie.citiz.coop/citiz-en-occitanie/> | lu le 20/10/2026 | non précisé | `docs/business_plan.md` |
| Citiz (réseau national) | Livre blanc 2026 : aide de Toulouse Métropole aux usages (p. 18), flotte à 8 % électrique et 41 % hybride (p. 10) | <https://www.citiz.coop/uploads/2026/02/2026-CITIZ-livre_blanc.pdf> | 2026 | non précisé | `docs/business_plan.md` |
| Citiz (réseau national) | Site du réseau : près de 2 800 voitures, 280 villes, près de 130 000 conducteurs | <https://www.citiz.coop/> | lu le 20/10/2026 | non précisé | `docs/business_plan.md` |
| recherche-entreprises.api.gouv.fr | Fiche de Mobilib', SCIC qui porte Citiz Occitanie (SIREN 503182792) : chiffre d'affaires et résultat net | <https://recherche-entreprises.api.gouv.fr/search?q=503182792> | exercice 2025 | non précisé | `docs/business_plan.md` |
| Xerfi | Fiche de Mobilib' : chiffre d'affaires de 2022 à 2024 | <https://www.xerfi.com/etudes-par-entreprise/mobilib_503182792> | 2022 à 2024 | non précisé | `docs/business_plan.md` |
| Toulouse Métropole | Magazine TIM n° 33, infographie sur l'autopartage : 86 stations et 170 véhicules, objectif 2030 de 143 stations et 400 véhicules | <https://documents.toulouse.fr/TIM/33/version_accessible/linfographie/autopartage-mode-demploi.html> | hiver 2025 | non précisé | `docs/business_plan.md` |
| La Gazette du Midi | Article sur le maillage de Citiz Occitanie : 180 voitures, 400 visées en 2030, près de 8 000 inscrits | <https://gazette-du-midi.fr/au-sommaire/entreprises/autopartage-citiz-occitanie-poursuit-son-maillage-en-creant-trois-nouvelles> | 03/03/2026 | non précisé | `docs/business_plan.md` |
| ADEME et 6t | Enquête nationale sur l'autopartage, rapport et synthèse : voitures remplacées, kilomètres évités, places libérées, profil des usagers | rapport <https://librairie.ademe.fr/index.php?controller=attachment&id_attachment=4922> ; synthèse <https://librairie.ademe.fr/index.php?controller=attachment&id_attachment=6712> | 2022 | non précisé | `docs/business_plan.md` |
| ADEME | Base Empreinte : 256 g CO2e par km pour la voiture moyenne du parc, cycle de vie (identifiant 43791) | <https://data.ademe.fr/datasets/base-carboner> | non précisé | non précisé | `docs/business_plan.md` |
| Impact CO2 | 142 g CO2e par km pour un diesel moyen (valeur alternative) | non précisé | non précisé | non précisé | `docs/business_plan.md` |
| SDES | Kilométrage moyen d'une voiture particulière : 11 600 km en 2025 | non précisé | 10/07/2026 | non précisé | `docs/business_plan.md` |
| Forum Vies Mobiles | Coût d'une voiture pour ses usagers : 5 900 € par an | non précisé | 2025 | non précisé | `docs/business_plan.md` |
| INSEE | Insee Première n° 1855 : 11 % du revenu disponible consacré à la voiture | non précisé | 2021 | Licence Ouverte Etalab 2.0 | `docs/business_plan.md` |
| Cerema | Voiture particulière à l'arrêt 95 % du temps (repris dans la présentation de Citiz) | non précisé | 2021 | non précisé | `docs/business_plan.md` |
| Banque des Territoires (étude Adetec) | Stationnement : 10 m² par place en voirie, 25 m² en parking, environ 169 € par an de coût public pour une place gratuite en voirie | non précisé | 2023 | non précisé | `docs/business_plan.md` |
| Banque des Territoires | Objectif national de 70 000 véhicules en autopartage d'ici 2031, contre moins de 14 000 en 2025 | <https://www.banquedesterritoires.fr/autopartage-le-gouvernement-vise-un-objectif-de-70000-vehicules-dici-2031> | 04/12/2025 | non précisé | `docs/business_plan.md` |
| France 3 Occitanie | Ligne C : 21 stations, mise en service repoussée au-delà de 2028 | non précisé | 13/10/2026 | non précisé | `docs/business_plan.md` |
| Tisséo Ingénierie | Prolongement de la ligne B jusqu'à Labège : mise en service en septembre 2027 | non précisé | non précisé | non précisé | `docs/business_plan.md` |
| INSEE | Population de Toulouse Métropole : 841 524 habitants en 2023, 11 732 de plus par an en moyenne de 2017 à 2023 | non précisé | 2023 | Licence Ouverte Etalab 2.0 | `docs/business_plan.md` |

## Arbres et voirie

| Organisme | Jeu de données | URL | Date ou millésime | Licence | Utilisé par |
| --- | --- | --- | --- | --- | --- |
| Toulouse Métropole | Arbres urbains (jeu « arbres-urbains ») : un point par arbre, avec son espèce, son stade de développement et sa commune | export complet : <https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/arbres-urbains/exports/parquet> | fichier du 20/10/2026 | ODbL, à confirmer (page de licence du portail : <https://data.toulouse-metropole.fr/page/licence/>) | `arbres` (notebook `08_criteres_citiz`) |
| OpenStreetMap | Arbres, parkings et routes principales, extraits par l'API Overpass | <https://overpass-api.de/api/interpreter> | base du 20/10/2026 | ODbL, © contributeurs OpenStreetMap | `arbres` (en complément), `parkings_osm`, `routes_osm`, `places_candidates`, `criteres_citiz` (notebook `08_criteres_citiz`) |
| IGN (Géoplateforme) | Géocodage inverse de la Base adresse nationale : l'adresse de chaque place candidate | <https://data.geopf.fr/geocodage/reverse/csv> | consulté le 20/10/2026 | Licence Ouverte Etalab 2.0 | `places_candidates` |
| Carto | Fond de plan des rues de l'application, tiré d'OpenStreetMap | non précisé | non précisé | ODbL pour les données OpenStreetMap ; conditions des tuiles non précisées | `optimisation/app/streamlit_app.py` |
| Esri | Fond de carte World Street Map (tuiles) | `https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}` | non précisé | non précisé (attribution « Esri » dans le notebook) | `cartes/Maps.Notebook` |

## Fichiers de travail

Les deux classeurs du MBA sont dans le dépôt, dans `docs/couts/` ; la présentation de Citiz reste hors dépôt, dans les notes de l'équipe.

- `docs/couts/Cout_citiz.xlsx` (copie de `Coût citiz (2).xlsx`) : classeur du MBA sur le coût d'une station Citiz (onglets Synthèse, Justification, Hypothèses, Calcul). Sa ligne « Coût annuel complet par station (thermique ou hybride) » est importée dans `couts.parquet`.
- `docs/couts/Cout_bus_velo.xlsx` : classeur du MBA sur le coût d'un arrêt de bus et d'une station vélo (onglets Justification, Hypothèses, Calcul). Ses lignes « Coût annuel d'un arrêt (investissement amorti) » et « Coût annuel complet d'une station de 10 vélos » sont importées dans `couts.parquet`.
- `20261019 Presentation Citiz Epitech vF.pdf` : présentation de Citiz à l'équipe, le 19 octobre 2026.
