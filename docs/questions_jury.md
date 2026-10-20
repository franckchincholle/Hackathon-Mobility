# Questions probables du jury

Quatre questions par juré, chacune avec une réponse de deux ou trois phrases. Les chiffres viennent de
[business_plan.md](business_plan.md) et de [SOURCES.md](../SOURCES.md). Règle : si on ne sait pas, on le dit,
et on dit comment on le saurait.

## Le juré du pitch

**1. En une phrase, que proposez-vous à Citiz ?**
Un outil déjà branché sur vos données, qui dit où mettre les 200 voitures qui vous manquent pour 2030, ce
qu'elles rapporteront, et qui surveille chaque mois les stations qui décrochent.

**2. Pourquoi vous, plutôt qu'un cabinet de conseil ?**
Parce que l'outil tourne déjà : la collecte de votre flux toutes les 10 minutes, vos 8 critères mesurés sur
toute la métropole, le modèle et l'optimisation sont dans Microsoft Fabric. La plus petite capacité Fabric
(F2) suffit : environ 260 $ par mois au tarif public de Microsoft.

**3. Quelle est la prochaine étape concrète ?**
Un mois de mesure pour confirmer les stations qui dorment et celles qui saturent, puis un pilote de 5
stations de la liste, mesurées dès leur ouverture. Le site se relance chaque année sur les nouvelles données.

**4. Qu'est-ce qui pourrait faire échouer le plan ?**
Trois choses, et chacune a sa parade :

- un usage mesuré sur 30 heures de semaine : la collecte continue ;
- des places de stationnement à obtenir de la ville : on en propose une précise, avec son adresse ;
- des coûts estimés : on les teste en fourchette basse et haute, et la liste reste la même.

## La jurée impact, inclusion et écologie

**5. L'autopartage, c'est surtout pour les cadres. Vous allez où ?**
C'est vrai aujourd'hui : 65 % des usagers sont cadres (ADEME 2022). Notre liste va ailleurs : 82 % des
habitants qu'elle gagne vivent dans la moitié la plus modeste de la métropole, contre 48 % pour les stations
actuelles, et 10 980 ménages sans voiture y gagnent une Citiz à 5 minutes. La Métropole rembourse déjà la
moitié de leurs trajets.

**6. Quel impact carbone, concrètement ?**
Pour les 46 voitures du plan : 212 à 363 voitures personnelles en moins, 460 000 à 874 000 km évités et 118 à
224 tonnes de CO2 par an. Ce sont les moyennes de l'enquête nationale de l'ADEME (2022), appliquées à
Toulouse : un ordre de grandeur, donné en fourchette.

**7. Ne risquez-vous pas de stigmatiser des quartiers ?**
Nous parlons de « zones à potentiel », jamais de « quartiers mal desservis ». Les carreaux peu peuplés ne
sont jamais affichés seuls, et toutes les populations sont arrondies à la dizaine.

**8. Et les arbres, la ville verte ?**
On ne coupe rien : chaque place proposée est un parking existant, à plus de 10 m d'un arbre. Et chaque
voiture partagée libère 0,9 à 3 places : jusqu'à 1 380 m² de voirie rendus à la ville, à végétaliser.

## Le juré de Citiz

**9. D'où sortent vos 10 000 € de recette par voiture ?**
De vos chiffres publics : 2 M€ pour 200 voitures (repère utilisé par le MBA), recoupé par le chiffre
d'affaires 2025 de Mobilib', 2,38 M€ pour 220 à 255 voitures. C'est dans le seuil de rentabilité que vous
nous avez donné : 700 à 900 € par voiture et par mois.

**10. Vos coûts sont-ils réalistes ?**
Chaque poste du classeur du MBA est sourcé : voiture, boîtier, assurance, entretien, carburant, redevance.
Le total, 10 373 € par voiture et par an, tombe dans votre propre seuil. On teste aussi les fourchettes
basse et haute.

**11. Combien ça rapporte, et quand ?**
À notre usage moyen mesuré, 29 %, les 23 stations rapportent 468 k€ par an, à 3 % de leur coût complet. À 35 %,
elles dégagent 82 k€ par an et sont remboursées en 3,8 ans. Le premier gain est ailleurs : une station qui
dort coûte 17 500 € par an, et l'outil évite d'en ouvrir.

**12. Trente heures de mesure, c'est solide ?**
Pour prédire l'usage station par station, non, et nous le disons : la corrélation n'est que de 0,14. Pour
l'ordre de grandeur, oui : 29 % d'usage, c'est cohérent avec 10 000 € par voiture. La collecte continue :
dans un mois, le modèle d'usage apprendra sur des données stables.

## En réserve, si le jury est technique

**Comment savez-vous que le modèle marche ?**
Nous avons caché Toulouse au modèle. Appris sur les 14 autres réseaux Citiz, il place 82 % de vos stations
toulousaines dans les 20 % de carreaux qu'il juge les meilleurs (AUC 0,895). Détails dans
[RESULTATS.md](../modele/RESULTATS.md).

**Pourquoi un algorithme glouton plutôt qu'une optimisation exacte ?**
Il répond en une fraction de seconde et atteint 99,4 % de l'optimum en moyenne, mesuré contre une
résolution exacte. Franck le détaille dans [ORAL.md](../optimisation/docs/ORAL.md).
