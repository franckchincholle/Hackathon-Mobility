# Ce qui a changé dans la nuit du 20 au 21 octobre

Branche `finitions`. Chacun doit pouvoir défendre sa partie : voici ce qui a bougé chez vous, et ce qu'il
faut savoir dire.

## Franck (MSc 4, le site)

- Nouveaux modules :
  - `rentabilite.py` : recette, seuil de rentabilité et délai de retour, d'après l'usage réel mesuré ;
  - `impact.py` : voitures en moins, CO2, voirie libérée, ménages modestes et sans voiture ;
  - `criteres_citiz.py` : les 8 critères de Citiz et la place proposée.
- Ce que lisent les tables :
  - `fabric.py` lit les nouvelles tables, et `acces_carreau` d'Anthony avec ses colonnes renommées ;
  - les coûts vélo et bus viennent des classeurs du MBA : 24 495 € et 548 € par an. Les coûts fictifs sont
    retirés, la bannière « provisoire » aussi.
- À l'écran :
  - une deuxième ligne d'en-tête, les onglets « Business plan » et « Impact » ;
  - la fiche d'une station sous la liste, le choix « Les 8 critères de Citiz » ;
  - les calques usage, places et arbres.
- Effet sur tes chiffres :
  - Citiz : 23 stations et 84 840 habitants. Le site n'a plus qu'un modèle, le v2, pris par son rang, à la
    place du score de MSc 3 ;
  - le seuil de 50 habitants de la table de MSc 2 réduit les candidats de 4 686 à 2 929 (151 calculs au lieu de 67 400) ;
  - la collectivité passe à 53 stations (40 vélo, 13 bus). `docs/ORAL.md` est à jour.
- Sur le scénario de la démo, le glouton atteint 99,8 % de l'optimum prouvé (résolution exacte, α = 0, 1 et 3).
  À faire de ton côté : relancer `comparer_exact.py` sur ces données pour mettre à jour ton 99,4 % en moyenne.
  134 tests passent.

## Anthony (MSc 2, les cartes)

- Ta table `acces_carreau` est branchée. La carte de chaleur (objectif 1) s'affiche dans le site, et
  l'optimisation applique le seuil de ta table : 50 habitants. Ton notebook dit 25 : ne le relance pas avant
  l'oral, les zones grises et la liste des stations changeraient. On les aligne après.
- Ta branche `msc2-geoposition` n'est pas fusionnée : `Maps.Notebook` sur `main` en est la version complète.
- À savoir défendre : le choix des 400 m et du seuil de 50. Une limite à assumer : les lignes sans passage le
  jour de référence sont comptées comme des options.

## MSc 3 (le modèle)

- Le site n'a plus qu'un modèle : le v2 (`modele/potentiel_v2`, table `scores_potentiel_v2`), qui reprend
  ta démarche et tes 24 variables.
  - Il ajoute 12 variables (emplois, densité du voisinage), apprend sur les 14 autres réseaux Citiz et a été
    testé à l'aveugle sur Toulouse : AUC 0,895, et 82 % des stations dans les 20 % de carreaux les mieux notés.
  - Le site le prend par son rang : sa probabilité calibrée varie trop d'un carreau à l'autre pour être
    multipliée par les habitants. Il donne aussi une classe et 3 raisons par carreau, dans la fiche station.
  - `modele/RESULTATS.md` compare ton modèle (la v1) et le v2.
- Ton notebook `modele_predictif` n'est plus dans le dépôt, pour n'y laisser qu'une version : il reste dans
  Fabric et dans l'historique git, et ta table n'a pas été touchée. Si tu le relances, passe d'abord
  `ECRIRE_RESULTATS` à False : sinon il réécrit ta table.
- À l'oral, c'est toi qui présentes le modèle : dire qu'il apprend « où Citiz est installé », et non « où
  Citiz fonctionne ».

## Le MBA et la PO

- Tes classeurs de coûts sont dans le dépôt (`docs/couts/`) et branchés dans le site.
- `docs/business_plan.md` donne les chiffres et les phrases pour les slides. `docs/questions_jury.md`
  prépare les questions, et `presentation/` contient les 7 slides du pitch en HTML.
