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
  - Citiz : inchangé (23 stations, 83 090 habitants) ;
  - le seuil de 25 habitants de MSc 2 réduit les candidats de 4 686 à 2 929 (138 calculs au lieu de 67 400) ;
  - la collectivité passe à 53 stations (40 vélo, 13 bus). `docs/ORAL.md` est à jour.
- À faire de ton côté : relancer `comparer_exact.py` sur ces données pour confirmer le 99,4 %. 132 tests passent.

## Anthony (MSc 2, les cartes)

- Ta table `acces_carreau` est branchée. La carte de chaleur (objectif 1) s'affiche dans le site, et ton seuil
  de 25 habitants est celui que l'optimisation applique.
- Ta branche `msc2-geoposition` n'est pas fusionnée : `Maps.Notebook` sur `main` en est la version complète.
- À savoir défendre : le choix des 400 m et du seuil de 25. Une limite à assumer : les lignes sans passage le
  jour de référence sont comptées comme des options.

## MSc 3 (le modèle)

- Ton modèle reste celui de la démo : c'est le score par défaut, et ta table n'a pas été touchée.
- Un modèle v2 a été ajouté à côté (`modele/potentiel_v2`, table `scores_potentiel_v2`).
  - Il a été testé à l'aveugle sur Toulouse : AUC 0,895, et 82 % des stations dans les 20 % de carreaux les
    mieux notés.
  - Son score est calibré et il donne 3 raisons par carreau, affichées dans la fiche station.
  - `modele/RESULTATS.md` compare les deux modèles.
- Deux points dans ton notebook :
  - `ECRIRE_RESULTATS = True` par défaut (ligne 55) réécrit la table que lit le site : à passer à False ;
  - à l'oral, dire que le modèle apprend « où Citiz est installé », et non « où Citiz fonctionne ».

## Le MBA et la PO

- Tes classeurs de coûts sont dans le dépôt (`docs/couts/`) et branchés dans le site.
- `docs/business_plan.md` donne les chiffres et les phrases pour les slides. `docs/questions_jury.md`
  prépare les questions, et `presentation/` contient une esquisse de slides en HTML et les captures de la démo.
