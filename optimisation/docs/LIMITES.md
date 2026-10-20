# Limites assumées (partie MSc 4)

| Limite | Effet | Pour aller plus loin |
| --- | --- | --- |
| **Accessibilité de MSc 2 avec ses propres règles** : seuil de 25 habitants, lignes sans passage comptées comme des options | Moins de candidats (2 929) ; un carreau près d'une ligne qui ne passe pas paraît desservi. | Filtrer les lignes sur `passages_jour > 0` dans le notebook Maps. |
| **Recette d'une nouvelle station = usage moyen mesuré** (29 %) : 30 heures de relevés ne prédisent pas l'usage station par station | Toutes les stations proposées ont la même recette prévue ; l'onglet Business plan montre l'effet d'un usage plus haut ou plus bas. | Un mois de relevés, puis un modèle d'usage (`modele/RESULTATS.md`). |
| **Cercle de 400 m à vol d'oiseau** (décision 4) | Ignore les coupures (Garonne, rocade, voies ferrées). | Réseau piéton OSM, prévu par MSc 2 si le temps le permet ; seule la matrice de couverture change. |
| **Coût Citiz du MBA : coût brut, recettes non déduites** ; chiffres d'autres territoires (Genevois, Belgique) ; usure et amortissement du boîtier supposés par l'équipe | Le coût réel net pour Citiz est plus bas que celui utilisé. | Déduire les recettes par voiture (repère : 10 000 € par an en Occitanie). |
| **Arrêt de bus à 548 € par an** (MBA : aménagement amorti sur 20 ans) | L'arrêt est de loin l'équipement le moins cher : la contrainte est l'emplacement, sur une ligne existante. | Ajouter le coût d'exploitation d'un arrêt (temps de parcours de la ligne). |
| **Coût identique pour toutes les stations d'un type** | Ignore le foncier, le génie civil ou une place déjà existante. | Coût par emplacement : l'algorithme le gère déjà. |
| **Budget annuel** (coût complet amorti, choix du MBA) | Ne montre pas l'effort de trésorerie de la première année (67 500 € par station Citiz par défaut). | Le classeur du MBA le donne pour le business case. |
| **Une station = une option, sans capacité** | Une petite station Citiz « dessert » autant qu'une grande. | Capacité (`capacite` dans `stations_partagees`) en paramètre. |
| **Arrêt de bus ajouté sans coût d'exploitation** | Un arrêt de plus allonge le trajet de toute la ligne. | Pénalité de temps par arrêt, à valider avec Tisséo. |
| **Population nouvellement desservie par type** (choix MSc 4, à valider) | Diffère de la lecture littérale du vocabulaire du kit (« aucune option »). | Trancher en point d'équipe. |
| **Glouton, pas l'optimum** | [98,3 à 100 %] de l'optimum mesuré sur Toulouse Métropole. | La version exacte existe (`exact.py`), en 3 à 53 s. |
| **Précision de 200 m** | L'emplacement est un carreau, pas une adresse. | Étude de terrain sur les emplacements retenus. |
| **Grille Power BI discrète** | Pas de 50 ou 100 k€, 7 valeurs de α. | Streamlit pour les valeurs intermédiaires. |
| **Score de potentiel et équité** (Citiz) | Le modèle donne un score faible aux zones sans transport, donc le curseur équité n'y change presque rien. | Score appliqué aux habitants, ou α plus élevé : à décider en équipe. |
| **Critères au choix : poids subjectifs** | Le classement dépend des poids donnés par le décideur. | C'est voulu : l'outil explore des hypothèses, le modèle prédictif reste la référence. |
| **Critères corrélés** (densité, logement en immeuble, ménages d'une personne) | Les cocher ensemble revient à donner plus de poids à la même idée. | Garder un critère par idée, ou baisser leurs poids. |
| **Motorisation et services mesurés par quartier (IRIS)** | Tous les carreaux d'un quartier ont la même valeur. | Données au carreau, si elles existent. |
| **Arbres** : en attente de la carte ; mesure à 200 m | Le critère décrit le secteur, pas la place exacte. | Étude de terrain sur les emplacements retenus. |
