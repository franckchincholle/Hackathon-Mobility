# Modèle de potentiel v2 : résultats

Pour le coéquipier du modèle et pour le jury. Chiffres d'une exécution du 20/10/2026 du code de
`modele/potentiel_v2.Notebook`, sur le Lakehouse `Mobilite`. Le modèle actuel ne change pas.

## Ce qui change par rapport au modèle actuel

| | Actuel (`scores_potentiel_msc3`) | v2 (`scores_potentiel_v2`) |
| --- | --- | --- |
| Apprend sur | Toulouse (98 carreaux avec station) | les 14 autres réseaux Citiz (70 039 carreaux, 1 326 avec station) |
| Toulouse | notée par le modèle qui l'a apprise | jamais vue : test à l'aveugle |
| Validation | plis par commune | un réseau entier de côté à chaque pli |
| Négatifs | tout carreau sans station | sans les carreaux à moins de 400 m d'une station |
| Variables | 24 | 36, dont emplois (Sirene), population à 400 m et 1 km, logements d'avant 1945 |
| Algorithme | régression logistique pondérée | gradient boosting peu profond (LightGBM) |
| Échelle | non calibrée : score moyen 0,23 | calibrée (Platt) : probabilité qu'un carreau porte une station |
| Explication | aucune | 3 raisons par carreau, en 8 critères proches de ceux de Citiz |
| Usage | aucun | occupation prévue, apprise sur les relevés des 15 réseaux |

Pourquoi : un modèle noté sur ses propres données d'entraînement ne dit pas ce qu'il vaut
ailleurs, et le site multiplie le score par la population. Avec un score moyen de 0,23 alors
que 1,5 % des carreaux portent une station, l'actuel gonfle tout d'un facteur 16.

## Métriques

Test à l'aveugle, Toulouse Métropole : 7 070 carreaux, 103 avec une station (taux de base 1,46 %).

| | v2, aveugle | actuel, appris sur Toulouse | 24 variables actuelles, méthode v2 |
| --- | --- | --- | --- |
| ROC-AUC | 0,895 (IC 95 % : 0,862-0,922) | 0,918 | 0,891 |
| Précision moyenne (AP) | 0,192 | 0,142 | 0,163 |
| Stations dans les 10 % de carreaux les mieux notés | 67 % | 71 % | 67 % |
| Stations dans les 20 % les mieux notés | 82 % (IC 95 % : 74-89 %) | 86 % | 79 % |
| Score de Brier (plus bas = mieux) | 0,0132 | 0,1196 | - |

- Sans la couronne de 400 m dans les négatifs : AUC 0,928, AP 0,47, 78 % et 86 % des stations
  dans les 10 % et 20 % premiers (actuel : 0,953, 0,43, 86 %, 92 %).
- Validation, un réseau de côté sur 14 : AUC 0,930, AP 0,198 (taux de base 1,9 %), 77 % et 90 %
  des stations dans les 10 % et 20 % premiers ; logistique : AUC 0,904. Réseau le plus difficile :
  « developpement » (villes moyennes), AUC 0,76 ; les 13 autres entre 0,91 et 0,98.
- Calibration sur Toulouse : Brier 0,0132, contre 0,0144 pour un taux constant et 0,0200 sans
  calibration. La somme des scores annonce 139 carreaux avec station pour 103 réels ; celle de
  l'actuel en annonce 1 632.
- Usage : occupation des voitures sur les heures facturées, 1 487 stations, 30 heures de
  relevés (19/10 14 h 43 au 20/10 21 h 10 UTC). Régression ridge, un réseau de côté : Spearman
  0,14 (IC 95 % : 0,09-0,19), erreur moyenne 0,240 contre 0,244 avec la moyenne des autres réseaux.
- Présence contre usage, 102 stations toulousaines : Spearman 0,16 (IC 95 % : -0,05 à 0,37)
  pour v2, 0,25 (0,04 à 0,44) pour l'actuel.
- Poids des critères sur Toulouse : mixité habitat-emplois-commerces (1,70), loin devant
  l'habitat collectif ancien (0,51), le profil des ménages (0,35), le stationnement privé
  (0,29), les revenus (0,19), la densité (0,18), la motorisation (0,14) et la gare (0,08).

La table `scores_potentiel_v2` : `score_potentiel` (probabilité calibrée, que le site multiplie
par la population), `rang_centile` de 0 à 100, `classe` de A (20 % les mieux notés, 84 des 103
carreaux avec station) à E, `raison_1` à `raison_3`, `occupation_prevue` (indicative).

## Limites assumées

- La cible est l'endroit où Citiz s'est déjà installé : le modèle apprend les choix passés de
  la coopérative, pas la demande.
- Transports : seule la présence d'une gare est connue partout en France ; les lignes Tisséo
  n'entrent pas dans un modèle national, d'où le faible poids de ce critère.
- Entre réseaux, la calibration ne bat pas un taux constant (Brier 0,0236 contre 0,0186), car la
  densité de stations varie d'un réseau à l'autre : l'échelle est un ordre de grandeur, le rang est solide.
- Sur 30 heures, les variables du carreau n'expliquent presque rien de l'usage :
  `occupation_prevue` ne doit pas servir à classer. À refaire sur plusieurs semaines.
- Motorisation mesurée à l'IRIS ; 11 stations sur 1 615 n'ont pas de carreau habité à 300 m.

## Trois phrases pour l'oral

1. « Nous avons caché Toulouse au modèle : appris sur les 14 autres réseaux Citiz, il place 82 %
   des stations toulousaines actuelles dans les 20 % de carreaux qu'il juge les meilleurs. »
2. « Notre score est une probabilité honnête : il annonce 139 carreaux avec station à Toulouse
   pour 103 réels, quand l'ancien en annonçait 1 632 ; les gains que le site calcule ne sont
   donc pas gonflés. »
3. « Chaque carreau dit pourquoi : d'abord la mixité entre logements, emplois et commerces,
   puis l'habitat collectif ancien et les petits ménages, ce qui recoupe les critères de Citiz. »

Reproduire : importer `modele/potentiel_v2.Notebook` dans Fabric et l'exécuter ; les tables ne
s'écrivent qu'avec `ECRIRE_RESULTATS = True`, et jamais par-dessus une table existante.
