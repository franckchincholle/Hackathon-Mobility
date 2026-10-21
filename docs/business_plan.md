# Citiz Toulouse 2030 : 200 voitures de plus, au bon endroit

Plan de développement écrit comme l'équipe data de Citiz Occitanie. « Mesuré » : calculé par nous
sur les données ouvertes ; les autres chiffres renvoient à leur source ([SOURCES.md](../SOURCES.md)).

## L'essentiel en 10 chiffres

| Chiffre | Ce qu'il dit | D'où il vient |
| --- | --- | --- |
| 29 % | Nos 204 voitures de la métropole sont en location 29 % du temps (32 % de 7 h à 23 h). Une voiture particulière est inutilisée 95 % du temps : les nôtres servent six fois plus. | Mesuré : flux GBFS Citiz relevé toutes les 10 minutes, 184 relevés sur 30 h en semaine ; Cerema 2021 |
| 10 000 € | Recette annuelle moyenne d'une voiture Citiz en Occitanie. | 2 M€ pour 200 voitures (2024) ; recoupé par le chiffre d'affaires 2025 de Mobilib' (2 376 658 € pour 220 à 255 voitures) |
| 351 € | Ce que rapporte chaque point d'occupation, par voiture et par an. | 10 000 € pour 28,5 % d'occupation mesurée sur le réseau occitan |
| 30 % | Occupation à partir de laquelle une station de 2 voitures couvre son coût complet (20 986 € par an). Nos voitures sont à 29 % : une station moyenne s'autofinance tout juste, c'est l'emplacement qui fait la marge. | Coût du MBA, dans le seuil de rentabilité donné par Citiz (700 à 900 € par voiture et par mois) |
| 31 600 € | Écart de résultat annuel entre une station qui dort (5 % : -17 500 €) et une station bien placée (50 % : +14 100 €), pour le même investissement de 58 180 €. | Calcul `optim_mobilite/rentabilite.py` |
| 27 sur 106 | Stations qui ont servi moins de 5 % du temps pendant la mesure (54 voitures). 7 stations ont dépassé 70 % (11 voitures). | Mesuré, à confirmer sur un mois |
| 400 | Voitures visées sur la métropole en 2030, contre 204 relevées aujourd'hui : il en manque environ 200. | Toulouse Métropole, magazine TIM n° 33 ; La Gazette du Midi, mars 2026 |
| 83 090 | Habitants qui gagnent une Citiz à 5 minutes à pied avec 23 nouvelles stations (500 k€ par an de coût complet), dont 10 980 ménages sans voiture. | Outil d'optimisation ; INSEE Filosofi 2021 et recensement 2023 |
| 82 % | Part de ces nouveaux habitants qui vivent dans la moitié la plus modeste de la métropole. Pour les habitants qui ont déjà une Citiz à 5 minutes : 48 %. | Niveau de vie Filosofi 2021, médiane des habitants (25 657 €) |
| 118 à 224 t | CO2 évité chaque année par ces 46 voitures, avec 212 à 363 voitures personnelles en moins et 414 à 1 380 m² de voirie libérés. | ADEME, enquête nationale autopartage 2022 ; Base Empreinte |

## Cinq phrases pour l'oral

1. « Une voiture particulière est inutilisée 95 % du temps. Les nôtres sont en location 29 % du temps : six fois plus. »
2. « Le même investissement de 58 000 € perd 17 500 € par an ou dégage 14 100 € de bénéfice. La différence, c'est l'emplacement. »
3. « Il nous manque 200 voitures pour 2030. L'outil dit où les mettre, station par station, et nous prévient quand une station décroche. »
4. « 82 % des habitants que nous gagnons vivent dans la moitié la plus modeste de la métropole, où la Métropole rembourse déjà la moitié de nos trajets. »
5. « Chaque voiture Citiz retire 5 à 8 voitures de la rue : nos 46 nouvelles voitures rendent jusqu'à 1 380 m² à la ville. »

## Pourquoi se fier à la liste

- Elle suit les 8 critères de Citiz : l'indice Citiz vaut 74 sur 100 là où nous avons déjà une
  station, contre 50 ailleurs (AUC 0,905 sur 7 070 carreaux).
- Le modèle a été testé à l'aveugle : appris sur les 14 autres réseaux Citiz, sans voir Toulouse, il
  place 82 % de nos stations toulousaines dans les 20 % de carreaux qu'il juge les meilleurs.
- L'optimisation atteint 99,4 % de l'optimum mathématique en moyenne, en une fraction de seconde.
- 18 stations sur 23 ont déjà leur place : un parking public à plus de 10 m de tout arbre recensé, avec son
  adresse. Pour les 5 autres, aucun parking public n'est recensé à moins de 300 m : la place se discute avec
  la commune.

## Le compte d'une station de 2 voitures

| Occupation | Recette par an | Résultat par an | Délai de retour de l'investissement |
| --- | --- | --- | --- |
| 5 % (station qui dort) | 3 509 € | -17 477 € | jamais |
| 29 % (notre moyenne) | 20 351 € | -635 € | 5,3 ans |
| 30 % (équilibre) | 20 986 € | 0 € | 5 ans |
| 40 % | 28 070 € | +7 084 € | 3,1 ans |
| 50 % | 35 088 € | +14 102 € | 2,3 ans |

Recette = 351 € par point d'occupation et par voiture. Résultat = recette moins le coût complet du
MBA (20 986 € par an, amortissements compris). Délai = investissement d'ouverture (58 180 €) divisé
par ce que la station dégage avant amortissements.

## Le plan 2027-2030

1. **Rééquilibrer d'abord, sans rien construire.** Si la mesure se confirme sur un mois, déplacer
   des voitures des stations qui dorment vers les stations saturées : une station qui dort coûte
   environ 17 500 € par an de plus qu'elle ne rapporte. Le collecteur tourne déjà dans Microsoft
   Fabric : la mesure s'allonge toute seule.
2. **Ouvrir les 23 premières stations de la liste** (46 voitures, 500 k€ par an de coût complet,
   1,34 M€ d'investissement si les voitures sont achetées). À notre usage actuel (29 %), elles
   encaissent 468 k€ de recette par an pour 483 k€ de coûts : le plan est à l'équilibre, à 15 k€
   près, et ajoute 20 % au chiffre d'affaires de Citiz Occitanie (2,38 M€ en 2025). Le bénéfice
   commence au-dessus de 30 % d'usage : 82 k€ par an à 35 %, avec un investissement remboursé en
   3,8 ans ; 163 k€ par an à 40 %, remboursé en 3,1 ans.
3. **Continuer au rythme de +20 % de stations par an**, celui que vise la Métropole, jusqu'aux 400
   voitures de 2030. L'outil se relance chaque année sur les nouvelles données.
4. **Financer avec nos sociétaires** : 15 parts sociales de 750 € financent une voiture ; une
   station, c'est 30 sociétaires du quartier.

## Méthode et limites

- L'usage est mesuré sur 30 heures en semaine (du lundi 19 octobre à 16 h 43 au mardi 20 à 23 h 10).
  Il manque le week-end, où l'autopartage sert le plus. « En location » compte aussi une réservation
  qui n'a pas encore commencé. Le collecteur continue : la mesure s'affine chaque jour.
- Une nouvelle station compte avec l'usage moyen mesuré. Sur 30 heures, aucune variable ne prévoit
  encore l'usage station par station (corrélation de 0,14) : le site montre ce que rapporte le plan
  selon l'usage atteint, avec un curseur, plutôt qu'une prévision fragile.
- La recette d'une voiture est supposée proportionnelle à son occupation. Le prix au kilomètre et
  les forfaits à la journée sont lissés dans la moyenne.
- Les coûts sont ceux du classeur du MBA : coût complet, voitures achetées et amorties sur 5 ans.
- Les effets sur l'environnement sont des moyennes nationales (ADEME 2022), appliquées à Toulouse.
