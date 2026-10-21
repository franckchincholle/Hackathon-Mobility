# Fiche oral (MSc 4 : optimisation et outil de démo)

> Les chiffres entre crochets viennent des données réelles (Toulouse Métropole, copie du Lakehouse du 21/10 à
> 2 h 16) : l'accessibilité de MSc 2 (seuil de 50 habitants), le modèle prédictif v2 pris par son rang et les
> coûts sourcés du MBA pour Citiz, le vélo et le bus. Ils ont été recalculés le 21/10. Le « 99,8 % de
> l'optimum » est mesuré sur le scénario de la démo contre une résolution exacte ; le « 99,4 % en moyenne » de
> `comparer_exact.py` (gardé en local) date de l'ancien score : à relancer sur ces données.

## L'algorithme en trois phrases

1. Pour chaque emplacement possible, on compte les habitants à moins de 400 m (5 minutes à pied) qui n'ont
   pas encore cet équipement, pondérés par le curseur équité, et on multiplie par le score de potentiel de
   l'emplacement.
2. On pose d'abord la station qui rapporte le plus **par euro**, on retire ces habitants (chacun ne compte
   qu'une fois), et on recommence tant que le budget le permet.
3. On vérifie qu'aucune station seule ne ferait mieux, et on mesure l'écart avec la solution exacte :
   **[99,8 %] de l'optimum** sur le scénario de la démo.

## Démo pas à pas (environ 3 minutes)

Avant de passer :

- lancez `./start.sh --hors-ligne` à la racine du dépôt (la copie des tables doit avoir été faite par `./start.sh`) ;
- si le réseau est mauvais, coupez « Fond de carte ».

1. **Le problème** (budget Citiz, 500 k€ par an, α = 1, coûts par défaut du MBA).
   *« Citiz consacre 500 000 € par an à de nouvelles stations. Où les poser dans la métropole ? »*
   Lisez la phrase-choc : *« Avec 500 k€ par an, Citiz touche [84 840] habitants de plus ([69 960] à
   [124 350] selon les coûts). »* Précisez : *« Une station coûte [21 000] € par an, un chiffre sourcé et
   recoupé avec le seuil de rentabilité que Citiz nous a donné. »*
2. **La liste**. *« La n°1 est celle qui touche le plus d'habitants par euro. L'ordre de la liste, c'est
   l'ordre de priorité. »* [23] stations se répartissent entre Toulouse, Colomiers, Cugnaux et Blagnac.
3. **Les calques**. Ouvrez « Calques de la carte » et cochez « Zones à potentiel » : *« En rouge, les
   emplacements les plus prometteurs avant tout arbitrage de budget. Les stations retenues tombent dessus. »*
   Ajoutez les stations Citiz existantes et les lignes de bus. Recadrez sur une commune (Blagnac).
   La carte de chaleur de MSc 2 et le score du modèle se superposent ici.
4. **Vos critères**. Dans « Zones à potentiel : sur quoi se baser ? », choisissez « Mes critères », puis
   cochez seulement la densité et les ménages sans voiture. *« Le décideur peut tester ses propres
   hypothèses : la carte et la liste se recalculent sur les seuls critères qu'il garde. Le modèle prédictif
   reste notre référence, et il est lui-même un critère possible. »* Montrez un calque d'analyse (motorisation
   ou niveau de vie).
   Si on vous parle des arbres : *« Citiz nous l'a demandé. 19 stations sur 23 ont déjà leur place de parking,
   à plus de 10 m de tout arbre recensé, avec son adresse : calque "Places proposées" et fiche de la station. »*
5. **Le budget**. Glissez de 500 à 250 k€, puis à 1 M€ : *« Le calcul est instantané. »*
   Onglet **Budget → habitants** : *« Chaque euro rapporte moins que le précédent. »*
6. **L'équité**. Restez sur Citiz et passez le curseur de 0 à 3 : l'encadré « Effet de ce réglage » montre
   le prix. *« Pour Citiz, servir d'abord les habitants sans transport fait passer ceux qu'on gagne de [160] à
   [1 010], pour [5 %] d'habitants touchés en moins. Le modèle de potentiel désigne les quartiers denses et
   déjà desservis, là où l'autopartage marche : l'autopartage seul ne comblera pas les zones sans transport. »*
   Basculez sur la collectivité à α = 3 : *« Ici, le même curseur apporte un vélo ou un bus à [7 080]
   habitants de plus qui n'avaient rien, pour [7 %] d'habitants touchés en moins. Le décideur tranche. »*
7. **La robustesse**. Passez en coûts hauts : *« [18] stations au lieu de [23], mais les mêmes, dans le même ordre. »*
8. **La collectivité**, 1 M€ par an : *« Même méthode. Les arrêts de bus ne sont proposés que sur des lignes Tisséo
   qui existent. »*
9. **La preuve**. Onglet **Méthode** : *« [151] calculs au lieu de [67 400] grâce au glouton paresseux, et
   [99,8 %] de l'optimum sur ce scénario, mesuré contre une résolution exacte. »*

Ajouté dans la nuit du 20 au 21, à montrer si le jury creuse :

- la deuxième ligne de l'en-tête (Citiz) : recette prévue, seuil de rentabilité (30 % d'usage, contre 29 % mesuré
  sur nos voitures), investissement, voitures personnelles en moins, CO2 évité ;
- l'onglet **Business plan** : le curseur « occupation visée » (de 29 % à 40 %, le plan passe de l'équilibre à
  +163 k€ par an) et l'usage mesuré de nos stations ;
- l'onglet **Impact** : 82 % des habitants gagnés vivent dans la moitié la plus modeste de la métropole ;
- sous la liste, la **fiche d'une station** : ses 8 critères Citiz, sa place et son adresse ;
- dans « Zones à potentiel », le choix **Les 8 critères de Citiz**.

## Questions probables du jury, sur ma partie

### Jury non technique

**1. Pourquoi faire confiance à cette liste ?**
Chaque station est justifiée par un chiffre vérifiable : les habitants qu'elle touche et son coût. Nous
avons comparé la méthode à la solution mathématiquement optimale sur le scénario présenté : [99,8 %]. Et la
liste reste la même quelle que soit la fourchette de coûts : en coûts hauts, [18] stations, les mêmes, dans
le même ordre.

**2. Le curseur équité, c'est vous qui choisissez sa valeur ?**
Non. L'outil montre le prix de chaque choix. Pour la collectivité, à α = 3 : [−7 %] d'habitants desservis,
mais [16 110] habitants sans transport gagnés au lieu de [9 030]. Pour Citiz, le curseur ne change presque
rien, car le potentiel de l'autopartage est dans les quartiers denses : c'est un résultat, pas un défaut. Le choix revient au décideur. α = 1 est un
point de départ : un habitant sans transport y compte double.

**3. Que se passe-t-il si les coûts sont faux ?**
On calcule tout avec les trois niveaux de coûts (12 200, 21 000 et 26 700 € par station et par an).
Les coûts hauts gardent le début de la même liste ; seul le nombre de stations change.

**4. Pourquoi pas directement là où il y a le plus de monde ?**
On compte les habitants **nouvellement** desservis. Une station au cœur de Toulouse, où Citiz est déjà
présent, en gagne peu de nouveaux. Et deux stations voisines se partagent leurs habitants : on ne compte
jamais deux fois la même personne.

**5. Et la vie privée ?**
Les carreaux sous le seuil sont grisés et jamais affichés seuls, et toutes les populations sont arrondies
à la dizaine.

### Jury data scientist

**6. Pourquoi un glouton plutôt qu'une optimisation exacte ?**
C'est une couverture maximale sous budget, un problème NP-difficile à rendements décroissants. Le glouton
au ratio, combiné au meilleur élément seul, a une garantie démontrée de ½(1 − 1/e). Il répond en une
fraction de seconde, contre 3 à 53 s pour HiGHS. Et l'écart mesuré avec l'optimum prouvé est de
[1,7 %] au pire.

**7. Qu'est-ce que le glouton paresseux change ?**
Rien au résultat (un test le vérifie sur 30 instances), tout à la vitesse. Les gains ne peuvent que
baisser, donc les anciens sont des majorants : [151] recalculs au lieu de [67 400].

**8. Comment le score de potentiel entre-t-il dans le calcul ?**
Comme le dit la décision 7 : valeur d'un emplacement = habitants nouvellement desservis × score de cet
emplacement. Dans la version exacte, chaque habitant est rattaché à une seule station et vaut son score.
Ce score est le rang du modèle v2, ramené entre 0 et 1 : sa probabilité calibrée varierait trop d'un
carreau à l'autre. *Pour la construction et les limites du modèle, je renvoie à MSc 3.*

**9. Comment l'outil tient-il compte de l'offre existante ?**
Un candidat n'a pas déjà la même offre à 400 m, et un habitant qui l'a déjà ne compte pas comme gagné. Le
curseur équité utilise le nombre d'options à 5 min (lignes distinctes et stations).
*Pour la mesure de l'accessibilité et le choix des 400 m, je renvoie à MSc 2.*

**10. Comment ça passe à l'échelle ?**
La géométrie se calcule une fois : un KDTree donne les voisins à 400 m de chaque candidat, rangés dans une
matrice creuse. Chaque scénario ne change que des poids et des coûts. Pour passer à l'Occitanie, il suffit
que MSc 1 change sa zone (`ZONE` dans `01_carreaux`) : le code de l'optimisation ne change pas.

**Question bonus : pourquoi ne pas toujours utiliser vos critères plutôt que le modèle ?**
Le modèle est évalué : il apprend, par validation croisée, ce qui distingue les quartiers où Citiz est déjà
installé (testé à l'aveugle sur Toulouse, il en retrouve 82 % dans ses 20 % de carreaux les mieux notés).
Les critères, eux, traduisent des hypothèses du décideur. Ils sont utiles pour explorer (« et si on misait sur
les ménages sans voiture ? »), mais leurs poids sont un choix, pas une mesure. L'outil montre les deux, et
dit toujours lequel est utilisé.
