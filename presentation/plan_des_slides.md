# Pitch Citiz Toulouse 2030 : plan des slides

Fichier à ouvrir : `presentation/index.html` (double-clic, Chrome ou Edge, sans réseau).
7 slides, 5 min 05 de discours prévu, puis 10 captures de l'outil en plan B.

Raccourcis : flèches, espace, Page suivante et Page précédente pour naviguer ; clic pour avancer ;
F plein écran ; N notes sous la slide ; P fenêtre présentateur (slide en cours, suivante, notes,
chronomètre) ; B écran noir ; 1 à 9 pour sauter à une slide (8 : plan B) ; H aide.
PDF : Ctrl+P, « Enregistrer au format PDF », une slide par page (pages 1 à 7 pour le pitch seul).

## 1. Accroche (25 s)

Affiché :

- Titre sur deux lignes : « Il vous manque 200 voitures. » puis, dans un bandeau turquoise légèrement incliné, « On sait où les mettre. »
- Visuel : 400 pastilles (une par voiture) ; les 204 voitures d'aujourd'hui en turquoise, les 196 qui manquent en anneau gris.
- Bandeau turquoise : « 400 voitures visées en 2030 sur la métropole, 204 aujourd'hui ».
- Pied : « Citiz Toulouse 2030 · Hackathon Mobility · Epitech x Citiz x Microsoft ».

Notes (à dire) :

> Bonjour. Nous sommes l'équipe data de Citiz Occitanie.
>
> La Métropole vise 400 voitures en autopartage en 2030. Aujourd'hui, vous en avez 204 sur la métropole. Il en manque 200.
>
> Notre outil dit où les mettre, ce qu'elles rapportent, et ce qu'elles changent pour la ville.

## 2. Vos voitures servent six fois plus (45 s)

Affiché :

- Bandeau de titre : « Vos voitures servent six fois plus qu'une voiture particulière. »
- À gauche, deux chiffres géants : 29 % (turquoise) « vos voitures, en location » ; 5 % (gris) « une voiture particulière, à l'arrêt 95 % du temps ».
- À droite, l'histogramme des 106 stations par tranche d'occupation : moins de 5 % (gris) 27, 5 à 25 % 25, 25 à 50 % 23, 50 à 70 % 24 (turquoise), plus de 70 % (rouge) 7.
- Sous le graphique : « 27 stations dorment : moins de 5 % du temps » (27 en gris) ; « 7 stations saturent : plus de 70 % » (7 en rouge).
- Source en petit : « Source : flux GBFS Citiz relevé toutes les 10 minutes, 184 relevés en semaine. »

Notes (à dire) :

> Une voiture particulière reste à l'arrêt 95 % du temps. Vos voitures sont en location 29 % du temps : elles servent six fois plus.
>
> Le kit du hackathon disait qu'il n'existe aucune donnée d'usage. Nous l'avons construite. Depuis lundi, un notebook Microsoft Fabric relève votre flux GBFS toutes les 10 minutes.
>
> Résultat : 27 stations dorment, moins de 5 % du temps. 7 stations saturent, plus de 70 %.
>
> Une station qui dort coûte 17 500 € par an. Une station bien placée en rapporte 14 100. L'emplacement, c'est la marge.

Pour les questions :

- Si on vous demande : la mesure couvre 30 heures en semaine, du lundi 19 au mardi 20 octobre, 184 relevés. Il manque le week-end. Le collecteur continue, la mesure s'allonge seule. 29 % est la moyenne pondérée par voiture (32 % de 7 h à 23 h).
- 17 500 € : station de 2 voitures à 5 % d'usage. 14 100 € : la même à 50 %. Même investissement de 58 180 €.

## 3. Vos 8 critères (40 s)

Affiché :

- Bandeau de titre : « Vos 8 critères, mesurés sur 7 070 pâtés de maisons. »
- À gauche, 8 tuiles : Transports collectifs, Densité urbaine, Mixité habitat/activité, Accessibilité/circulation, Simple pour stationner, Taux de motorisation faible, Visible, Arbres à distance.
- À droite : « Indice Citiz » 74/100 (turquoise, géant) « là où vous êtes déjà », 50 (gris) « ailleurs ».
- En bas, deux preuves : 82 % « Modèle testé à l'aveugle : vos stations toulousaines retrouvées sans les avoir vues » ; 10 m « Chaque station proposée a sa place de parking, à plus de 10 m d'un arbre, avec son adresse ».

Notes (à dire) :

> Vous nous avez donné vos 8 critères dans votre présentation. Nous les avons mesurés partout, sur 7 070 carreaux de 200 mètres : INSEE, transports, OpenStreetMap, 150 000 arbres.
>
> Notre indice Citiz vaut 74 sur 100 là où vous êtes déjà, 50 ailleurs. Il colle à vos stations actuelles.
>
> Le modèle a été testé à l'aveugle : il retrouve 82 % de vos stations toulousaines sans les avoir vues.
>
> Pour les arbres, la règle se joue à la place près. La station n° 1 tombe sur un carreau très arboré, note arbres de 4 sur 100. Pourtant, la place proposée est à 36 mètres du premier arbre. Chaque station a sa place de parking, à plus de 10 mètres d'un arbre, avec son adresse.

Pour les questions :

- Si on vous demande : le modèle a appris sur les 14 autres réseaux Citiz, sans voir Toulouse ; il place 82 % de vos stations toulousaines dans les 20 % de carreaux qu'il juge les meilleurs. AUC 0,905 pour l'indice.

## 4. Démo (90 s)

Affiché :

- Bandeau de titre : « Démo. »
- À gauche, le parcours dans un bloc turquoise : 1 Budget, 2 Stations, 3 Fiche station, 4 Business plan.
- À droite, en grand : la capture réelle de l'outil (captures/1_scenario_citiz_500k.png), en-tête chiffré et carte des 23 stations.
- Plan B : les 10 captures de l'outil suivent la slide 7 (touche 8).

Notes (à dire) :

> Passons à l'outil. [Basculer sur l'application.]
>
> Budget : 500 000 € par an. L'outil choisit 23 stations, et 83 090 habitants de plus ont une Citiz à 5 minutes à pied.
>
> Je bascule sur « Les 8 critères de Citiz » : la carte se lit avec votre propre grille.
>
> J'ouvre la fiche de la station n° 1 : 20 rue d'Avranches, une place de parking, l'arbre le plus proche à 36 mètres, et ses 8 notes.
>
> Onglet Business plan : je déplace le curseur d'usage de 29 % à 40 %. Le résultat du plan passe de -15 000 € à +163 000 € par an.
>
> Onglet Impact : habitants touchés, ménages sans voiture, CO2 évité.

Pour les questions :

- Repère : avec la grille des 8 critères, l'en-tête de l'outil passe à 85 610 habitants, dont 1 130 sans aucun transport. Ne pas être surpris.
- Plan B si le réseau tombe : les captures de l'outil suivent la slide 7, dans l'ordre du parcours. Touche 8 pour y aller, flèches pour avancer, touche 4 pour revenir ici.

## 5. Rentable au-dessus de 30 % d'usage (45 s)

Affiché :

- Bandeau de titre : « Rentable au-dessus de 30 % d'usage. »
- Trois chiffres : 23 stations, 46 voitures, 1,34 M€ d'investissement.
- À gauche, la trésorerie cumulée sur 8 ans (images/05_tresorerie.png) : trois droites à 29 % (gris), 35 % (turquoise), 40 % (prune), ligne du zéro, points de remboursement.
- À droite, la légende chiffrée : 29 % « À notre usage moyen (29 %) : 468 k€ de recette par an, à 3 % de leur coût complet » ; 35 % « +82 k€ par an, remboursé en 3,8 ans » ; 40 % « +163 k€ par an, remboursé en 3,1 ans ».
- En bas, trois étapes numérotées : Rééquilibrer d'abord (déplacer les voitures qui dorment) ; Ouvrir les 23 premières stations (la liste de l'outil) ; +20 % de stations par an (jusqu'aux 400 voitures).

Notes (à dire) :

> Une station de 2 voitures coûte 20 986 € par an, tout compris. Une station couvre son coût complet au-dessus de 30 % d'usage ; nos voitures sont à 29 % ; c'est l'emplacement qui fait la marge.
>
> Les 23 stations, c'est 46 voitures et 1,34 million d'investissement. À notre usage moyen, 29 %, elles rapportent 468 000 € par an : à 3 % de leur coût complet. À 35 %, il dégage 82 000 € par an, remboursé en 3,8 ans. À 40 %, 163 000 € par an, remboursé en 3,1 ans.
>
> Chaque point d'usage vaut 351 € par voiture et par an.
>
> L'ordre : rééquilibrer d'abord, puis ouvrir les 23 stations, puis 20 % de stations en plus chaque année jusqu'aux 400 voitures. Le financement vient de nos sociétaires : 15 parts sociales financent une voiture.

Pour les questions :

- Si on vous demande : coûts du classeur du MBA, voitures achetées et amorties sur 5 ans ; recette moyenne 10 000 € par voiture et par an (2 M€ pour 200 voitures en 2024). Une part sociale vaut 750 €.

## 6. Là où vivent ceux qui en ont besoin (40 s)

Affiché :

- Bandeau de titre : « Là où vivent ceux qui en ont besoin. »
- Deux barres : « Habitants touchés qui vivent dans la moitié la plus modeste de la métropole » ; les 23 stations proposées 82 % (turquoise) ; vos stations actuelles 48 % (gris).
- Quatre chiffres (prune) : 10 980 ménages sans voiture gagnent une Citiz à 5 minutes ; 212 à 363 voitures personnelles en moins ; 118 à 224 t de CO2 évitées par an ; jusqu'à 1 380 m² de voirie rendus à la ville.
- Bandeau prune : « La Métropole rembourse déjà la moitié des trajets Citiz des ménages modestes. On met les stations là où ils vivent. »

Notes (à dire) :

> 82 % des nouveaux habitants touchés vivent dans la moitié la plus modeste de la métropole. Pour nos stations actuelles, c'est 48 %.
>
> 10 980 ménages sans voiture gagnent une Citiz à 5 minutes. Entre 212 et 363 voitures personnelles en moins. 118 à 224 tonnes de CO2 évitées par an. Jusqu'à 1 380 m² de voirie rendus à la ville.
>
> La Métropole rembourse déjà la moitié des trajets Citiz des ménages modestes. Nous mettons les stations là où ils vivent.

Pour les questions :

- Sources : ADEME, enquête nationale sur l'autopartage 2022, et INSEE (Filosofi 2021, recensement). Dire « zones à potentiel », jamais « quartiers mal desservis ». Vie privée : un carreau peu peuplé n'est jamais affiché seul.

## 7. Prêt à déployer (20 s)

Affiché :

- Bandeau de titre : « Prêt à déployer. »
- Trois cartes : Fabric « tout y tourne déjà » (Microsoft Fabric : collecte toutes les 10 minutes, 8 critères, modèle, optimisation) ; 1 commande « pour lancer l'outil » (elle installe, copie les tables de Fabric et lance le site) ; 5 stations « un pilote, un mois de mesure » (la prochaine étape).
- Bandeau turquoise incliné : « Les voitures qui changent la ville, au bon endroit. »
- Pied : « Citiz Toulouse 2030 · Hackathon Mobility · Epitech x Citiz x Microsoft ».

Notes (à dire) :

> Tout tourne déjà dans Microsoft Fabric : la collecte toutes les 10 minutes, les 8 critères, le modèle, l'optimisation. L'outil se lance en une commande.
>
> Prochaine étape : un pilote de 5 stations et un mois de mesure.
>
> Les voitures qui changent la ville, au bon endroit. Merci. Place à vos questions.

## Plan B : captures de l'outil (après la slide 7)

1. `captures/1_scenario_citiz_500k.png` : Scénario Citiz, 500 k€ par an : 23 stations
2. `captures/5_les_8_criteres_de_citiz.png` : Les 8 critères de Citiz
3. `captures/2_liste_des_stations.png` : La liste des stations proposées
4. `captures/2b_fiche_station.png` : Fiche de la station n° 1, 20 rue d'Avranches
5. `captures/3_business_plan.png` : Business plan, vue 1
6. `captures/3b_business_plan.png` : Business plan, vue 2
7. `captures/3c_business_plan.png` : Business plan, vue 3
8. `captures/3d_business_plan.png` : Business plan, vue 4
9. `captures/4_impact.png` : Impact
10. `captures/6_collectivite_velo_bus.png` : Budget collectivité : vélo et bus

## Visuels

- `images/02_occupation_stations.png` : histogramme d'occupation (slide 2).
- `images/04_carte_23_stations.png` : carte des 23 stations proposées et des stations actuelles (non utilisée dans la page, la capture réelle la remplace ; disponible pour le PowerPoint du coéquipier).
- `images/05_tresorerie.png` : trésorerie cumulée à 29, 35 et 40 % (slide 5).
- La grille des 400 voitures (slide 1) et les barres 82 % / 48 % (slide 6) sont dessinées dans la page.
