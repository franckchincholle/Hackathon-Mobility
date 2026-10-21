# Décisions et pourquoi (MSc 4)

Chaque choix de l'optimisation, avec la raison et ce qu'on a écarté. Les chiffres viennent des **données
réelles de MSc 1** (Toulouse Métropole, 7 070 carreaux, 739 446 habitants). Depuis la nuit du 20 au 21
octobre, toutes les briques sont livrées : l'accessibilité de MSc 2, le score de MSc 3 et les coûts du MBA pour
Citiz, le vélo et le bus. Les chiffres datés d'avant ces livraisons sont recalculés dans `docs/ORAL.md` ; pour
les recalculer : `comparer_exact.py` (gardé en local par MSc 4) et l'application.

## 0. On suit les choix déjà faits par l'équipe

| Choix | Origine | Ce que fait l'optimisation |
| --- | --- | --- |
| Toulouse Métropole | décision 1, `zone_communes` de MSc 1 | elle travaille sur les 7 070 carreaux de la zone |
| EPSG:3035, `idcar_200m` | notebooks de MSc 1 | elle calcule toutes ses distances en EPSG:3035 |
| 400 m autour du centre du carreau | décision 4, `RAYON_M` de MSc 1 | même rayon, frontière comprise |
| Une option = une ligne distincte ou une station vélo / Citiz | décision 3, `arrets_lignes` de MSc 1 | `nb_options` de MSc 2 (`acces_carreau`) ; le calcul provisoire reste en repli |
| Valeur = population nouvellement desservie × score | décision 7 | score de l'**emplacement**, appliqué au gain du candidat |
| Habitants retirés après chaque choix | décisions 6 et 9 | chaque habitant ne compte qu'une fois |

## 1. Un algorithme glouton pour la version 1

**Décision** : on pose les stations une par une. À chaque étape, on prend celle qui apporte le plus de
valeur nouvelle **par euro** et qui rentre dans le budget restant. C'est la tâche « commencer simple
(algorithme glouton) » du kit.

**Pourquoi** :

- Il est **rapide** : une fraction de seconde par scénario. Les curseurs recalculent donc en direct.
- Il est **explicable** : l'ordre de la liste *est* l'ordre de priorité.
- Il est **garanti** : notre problème est une couverture maximale sous budget, à rendements décroissants
  (*sous-modulaire*). Pour ce type de problème, le glouton est l'algorithme de référence.
- Il est **proche de l'optimum** : sur Toulouse Métropole, la résolution exacte (décision 9) donne
  **99,4 % de l'optimum en moyenne, 98,3 % au pire**, sur 18 scénarios.

**Écarté** :

- La programmation linéaire en direct : 3 à 53 s par scénario.
- Les métaheuristiques : aucune garantie, et difficiles à expliquer.

## 2. La variante paresseuse (lazy greedy)

**Décision** : on garde les gains de chaque candidat dans un tas et on ne recalcule que le candidat en tête.

**Pourquoi** : poser une station ne peut que faire baisser le gain des autres. Un gain ancien est donc un
majorant (Minoux, 1978 ; Leskovec et al., 2007, « CELF »).

**Effet** (Citiz, 500 k€ par an, coûts par défaut) : **139 recalculs** au lieu de près de **108 000** (4 686 candidats × 23 étapes).

**Vérifié** : même choix que le glouton naïf sur 30 instances aléatoires, avec et sans score.

## 3. Comparaison avec le meilleur candidat seul

**Décision** : on renvoie le meilleur des deux, le glouton ou la meilleure station seule qui rentre dans le
budget.

**Pourquoi** : le glouton au ratio peut se faire piéger par une petite station très rentable qui bloque une
grosse. Prendre le meilleur des deux garantit au moins ½ (1 − 1/e) ≈ 32 % de l'optimum dans le pire cas
théorique (Khuller, Moss et Naor, 1999). En pratique, on mesure 98 à 100 %.

## 4. Le ratio gain / coût

**Décision** : on classe par valeur **par euro**.

**Pourquoi** : le budget est la contrainte. Pour la collectivité, un arrêt de bus et une station vélo ne
coûtent pas la même chose, et le ratio les met en concurrence équitable. Pour Citiz, toutes les stations ont
le même coût, donc le ratio revient à classer par valeur, ce qui rend la recommandation robuste aux coûts
(décision 10).

## 5. Le curseur équité, en version continue

```text
poids d'un habitant = 1 + α × bonus      bonus = 1 / (1 + nombre d'options à 5 min)      α de 0 à 3
```

**Pourquoi une formule continue plutôt qu'un bonus binaire** :

- pas d'effet de seuil : un carreau avec une seule ligne compte encore un peu plus qu'un carreau à cinq ;
- elle se dit en une phrase : sans transport ×(1+α), avec une option ×(1+α/2) ;
- les deux formules coïncident pour les zones sans aucun transport, celles que vise la décision 9.

**Pourquoi α max = 3** : un habitant sans transport pèse alors 4 fois plus. Au-delà, on poserait des stations
pour quelques habitants isolés.

**Effet mesuré**, de α = 0 à α = 3 :

| | Citiz, 500 k€ par an (avec le score de MSc 3) | Collectivité, 1 M€ par an (sans score) |
| --- | --- | --- |
| Habitants desservis | −310 (−0,4 %) | −5 800 (−7 %) |
| Habitants sans aucun transport gagnés | 77 dans les deux cas (+0) | de 7 240 à 16 900 (+9 660) |
| Carreaux sans transport gagnés | 1 dans les deux cas | de 55 à 170 |

Ces chiffres sont calculés avec les coûts par défaut.

**Constat important pour Citiz** : avec le score de MSc 3, le curseur ne change presque rien. Le modèle donne
un score très faible aux zones sans transport : il a appris où Citiz s'est installé, c'est-à-dire en zone
dense et déjà desservie (limite assumée de la décision 7). Le score de l'emplacement l'emporte donc sur le
bonus d'équité. Pour la collectivité, sans score, le curseur joue pleinement.

C'est un résultat à présenter tel quel. Si l'équipe veut que l'équité pèse aussi pour Citiz, il y a deux
pistes, à décider ensemble :

- monter α au-delà de 3 ;
- appliquer le score aux habitants plutôt qu'à l'emplacement, ce qui reviendrait sur la décision 7.

Le décideur arbitre ; l'onglet Équité montre toute la courbe.

## 6. Le score de potentiel est celui de l'emplacement (décision 7)

**Décision** : la valeur d'un candidat i est `score_i × Σ poids des habitants qu'il gagne`. C'est la
décision 7 telle qu'elle est écrite. MSc 3 livre un score pour « chaque carreau sans station » : c'est le
score de l'emplacement candidat.

**Conséquences** :

- Le gain d'un candidat ne peut toujours que baisser, donc le glouton paresseux et le meilleur seul restent
  valides.
- La version exacte rattache chaque habitant à une seule station posée, et il vaut le score de cette station
  (décision 9).
- MSc 3 a livré le 20/10 (`scores_potentiel_msc3`, 7 070 carreaux). Le site le lit en direct dans Fabric.
  Sans score, il vaudrait 1, et l'écran l'indiquerait.

## 7. Population nouvellement desservie : par type d'équipement

**Décision** (choix de MSc 4 du 20/10, **à valider en équipe**) : une station Citiz gagne les habitants qui
n'ont pas de Citiz à 5 min, même s'ils ont un bus.

**Pourquoi** :

- C'est la seule lecture qui donne un sens au curseur équité (décision 9 : « plus de poids aux zones sans
  aucun transport »). Si l'on ne comptait que les habitants sans aucune option, tous seraient déjà dans
  ces zones.
- Pour la collectivité, le vélo et le bus sont comptés à part. Les indicateurs affichent aussi les
  **habitants distincts**, que personne ne compte deux fois.

**À noter** : le vocabulaire du kit dit « qui n'avaient aucune option à 5 min ». Il faut trancher au prochain
point d'équipe.

## 8. Les candidats (tâche MSc 4 du kit)

**Décision** : un candidat est un carreau habité, au-dessus du seuil, sans station du même type à 400 m.
Pour le bus, il doit en plus être traversé par une **ligne de bus Tisséo** (tracés `shapes.txt` du GTFS
brut de MSc 1, `route_type` 3).

**Pourquoi** :

- Décision 8 : « arrêts de bus uniquement sur lignes existantes ».
- On a écarté les cars régionaux liO : ajouter un arrêt urbain sur un car régional n'a guère de sens.
- On a gardé les tracés réels plutôt qu'une ligne droite entre arrêts.

**Résultat** : 4 686 candidats Citiz, 3 661 vélo et 40 bus. 91 % des habitants ont déjà un bus à 5 min.

## 9. La version exacte : PuLP et HiGHS

**Décision** : on écrit le même problème en programme linéaire en nombres entiers. Avec un score de 1, c'est
le « Maximal Covering Location Problem » (Church et ReVelle, 1974) avec un budget. Avec des scores
différents, chaque habitant est rattaché à une seule station posée. On le résout sur **toute** Toulouse
Métropole.

**Pourquoi** :

- C'est le seul moyen d'affirmer, chiffres à l'appui, que le glouton est proche de l'optimum.
- HiGHS est libre et rapide.
- On garde PuLP en 2.x, l'API classique de toute la documentation (la 4.x l'a remplacée).

**Résultat** : les 18 scénarios sont résolus à l'optimum prouvé, en 3 à 53 s, avec le score de MSc 3 et les coûts
par défaut du MBA. Le glouton atteint **99,4 % de l'optimum en moyenne, 98,3 % au pire**.

## 10. La robustesse aux coûts

**Décision** : chaque scénario est calculé avec les trois niveaux de coûts du MBA. La phrase-choc donne la
valeur par défaut, et la fourchette entre parenthèses.

**Constat** : 100 % des stations retenues en coûts hauts le sont aussi en coûts bas.

| Budget | Coûts bas | Coûts par défaut | Coûts hauts |
| --- | ---: | ---: | ---: |
| Citiz, 500 k€ par an | 40 stations | 23 stations | 18 stations |
| Collectivité, 1 M€ par an | 68 stations | 45 stations | 34 stations |

Les coûts hauts gardent le début de la même liste.

## 11. Vie privée

- Les carreaux sous le seuil comptent dans les totaux, mais ne sont **jamais montrés seuls** : ils sont gris
  sur la carte, sans infobulle.
- Toutes les populations affichées ou exportées sont **arrondies à la dizaine**.

## 12. Outil de démo : Streamlit pour le direct, Power BI en grille

**Statut** : la décision 10 du kit est « à confirmer ». MSc 4 propose Streamlit pour la démo en direct, et
une grille précalculée (588 scénarios) pour Power BI.

**Pourquoi** :

- Streamlit fait tourner le vrai algorithme à chaque mouvement de curseur.
- Power BI ne peut que filtrer des scénarios déjà calculés.
- Plan B : un mode sans fond de carte.

## 13. Vélo et bus : sans modèle dédié (décision 11)

Leur score vaut 1 : leur valeur est la population nouvellement desservie, pondérée par l'équité. La décision
11 prévoit une version simplifiée, sans modèle dédié.

## 14. Travail en local, rien dans Fabric pour l'instant

**Décision** :

- On lit le Lakehouse (copie locale en lecture seule).
- Le notebook Fabric est prêt, mais ni déployé ni lancé.
- Rien n'est écrit dans le Lakehouse ni poussé sur Git avant que toutes les données soient définitives.

## 15. Les coûts du MBA : coût annuel complet, trois niveaux

**Décision** : on utilise la ligne que le classeur du MBA (`Coût citiz.xlsx`) désigne pour MSc 4 : le
« coût annuel complet par station (thermique ou hybride) ». Une station compte 2 voitures, amorties sur 5 ans.

| Niveau | Coût par station et par an | Usage |
| --- | ---: | --- |
| Bas | 12 197 € | robustesse |
| Défaut | 20 986 € | démo |
| Haut | 26 664 € | robustesse |

Ce sont les valeurs de la version du 20/10 à 15 h 05, qui intègre la réponse de Citiz : redevance de
stationnement de 0 à 1 500 € par place et par an, aménagement parfois pris en charge par la collectivité.

Le budget devient donc un **budget annuel**.

**Pourquoi** :

- Les coûts sont le rôle du MBA. Son choix remplace la proposition « installation + 1 an » de la décision 8,
  qui était encore « en attente ».
- Le coût annualisé compare équitablement Citiz et les vélos (même horizon).
- Le classeur vérifie son chiffre avec des repères indépendants. Le coût par défaut est de 10 373 € par voiture
  et par an, dans le seuil de rentabilité indiqué par Citiz lui-même : 8 400 à 10 800 € par voiture et par an.

**Ce qui reste MOCK** : plus rien depuis la livraison du classeur vélo et bus du MBA (548 € par an pour un
arrêt de bus, 24 495 € pour une station de 10 vélos) ; les lignes MOCK ne servent qu'en repli.

**Import** : `couts_mba.py` lit la ligne par son libellé, pas par son numéro, pour qu'une ligne
ajoutée au classeur ne casse rien.

## 16. Lecture en direct sur Fabric

**Décision** : le site lit les tables du Lakehouse `Mobilite` à chaque chargement, puis toutes les 10 minutes,
ou à la demande avec le bouton « Mettre à jour les données ». Rien n'est jamais écrit dans Fabric.

**Pourquoi** : une table mise à jour par l'équipe apparaît sans relancer quoi que ce soit.

**Garde-fous** :

- Chaque lecture réussie est gardée dans `data/reel/`. Si Fabric ou le réseau tombe, le site repart de cette
  copie et l'affiche.
- Chaque calcul mis en cache porte la version des données, pour ne jamais mélanger deux versions.
- Une table écrite par Spark avec des « deletion vectors » (le score) est lue par DuckDB, car `deltalake` ne
  sait pas encore les lire.

## 17. Zones à potentiel selon des critères choisis

**Décision** : un interrupteur « Modèle prédictif / Mes critères » choisit le score qui multiplie la population
nouvellement desservie. Il s'applique à la fois à la carte des zones à potentiel et à la liste des stations.

- **Par défaut, c'est le modèle prédictif** (décision 7).
- **« Mes critères »** : le décideur coche ses critères (densité, niveau de vie, motorisation, type de quartier,
  services à 5 min, communes, peu de transport, arbres, le modèle lui-même…). Il leur donne un poids de 1 à 3
  et, quand un critère joue dans les deux sens, il en choisit le sens.

**Calcul** : `score = Σ poids × rang / Σ poids`, entre 0 et 1 (`optim_mobilite/criteres.py`).

- Le **rang** est la place d'un carreau parmi les carreaux habités au-dessus du seuil.
- Un quartier inconnu reçoit 0,5, c'est-à-dire neutre.
- Le type de quartier vaut 1 pour l'habitat, 0,5 pour une commune non découpée, 0 pour l'activité. Les
  communes choisies valent 1.

**Pourquoi le rang** : il met sur la même échelle des euros, des parts et des comptages, et une valeur extrême
n'écrase pas les autres. Un critère « au-dessus de 80 % des carreaux » se dit simplement.

**Pourquoi une moyenne pondérée** : c'est la méthode multicritère la plus lisible, et le décideur voit
directement l'effet de chaque poids. Elle ne cherche pas à « prédire » : c'est un outil d'exploration des
hypothèses. Le modèle prédictif reste la référence évaluée.

**Stationnement dégagé (demande de Citiz)** : une place sans arbre est plus visible, et la voiture n'est ni salie
ni abîmée.

- Le critère compte les arbres de chaque carreau (KDTree), rapportés au km².
- Il s'active dès qu'une table `arbres` (`lat`/`lon` ou `x_3035`/`y_3035`) existe dans le Lakehouse. Elle
  viendrait de la carte de Citiz ou, à défaut, du jeu « arbres d'alignement » de Toulouse Métropole.
- À 200 m près, il décrit le secteur, pas la place exacte.

**Chaque critère est aussi un calque**, en 5 classes de même taille. La motorisation et les services sont des
valeurs **de quartier** (IRIS), attribuées à chacun de ses carreaux, et l'infobulle le précise.
