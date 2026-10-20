# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "e3b26cda-daa2-4b1c-8fe1-828c20b1b836",
# META       "default_lakehouse_name": "Mobilite",
# META       "default_lakehouse_workspace_id": "94ef609e-283d-424d-9252-6d83b219c77d",
# META       "known_lakehouses": [
# META         {
# META           "id": "e3b26cda-daa2-4b1c-8fe1-828c20b1b836"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # 07 — · Modèle prédictif Citiz
# **Hackathon Mobility — Toulouse Métropole · Microsoft Fabric**
# 
# ### Objectif
# Attribuer **un score de potentiel entre 0 et 1** aux carreaux INSEE de 200 m candidats pour une **nouvelle station Citiz**. Les scores caractérisent la **ressemblance aux lieux où Citiz s'est déjà installé** : ils **ne prédisent pas le nombre de réservations, la rentabilité ou la demande réelle**.
# 
# ### Entrées : tables existantes du Lakehouse `Mobilite`
# - `dbo.carreaux_france` et `dbo.carreaux_france_variables` : démographie, revenus, motorisation (rattachée à l'IRIS ou à la commune), familles d'équipements dans un rayon de 400 m.
# - `dbo.carreaux` et `dbo.carreaux_variables` : mêmes informations pour Toulouse Métropole.
# - `dbo.citiz_stations` : stations Citiz des flux régionaux, pour créer la cible 0/1.
# - `dbo.arrets`, `dbo.arrets_lignes`, `dbo.stations_partagees` : calcul **direct** des lignes de transport et stations de vélos à 400 m à Toulouse, selon la méthode de `Maps.ipynb` ; pas besoin d'exécuter `Maps`.
# 
# ### Deux périmètres — point méthodologique essentiel
# - **National** : on entraîne et valide sur des communes de France métropolitaine avec une station Citiz identifiable dans un carreau habité. Variables démographiques, motorisation et équipements uniquement : les flux GTFS du projet **ne sont pas nationaux**.
# - **Local enrichi (Toulouse)** : mêmes variables **+** lignes TC et stations vélo dans un rayon de 400 m. La validation croisée se fait **par commune**, avec des groupes disjoints.
# 
# Le mode de prédiction par défaut donne priorité au **local enrichi si sa validation spatiale est possible** ; sinon il revient au national. Les résultats indiquent explicitement le modèle utilisé et les variables utilisées.
# 
# **Sécurité** : le notebook ne modifie aucune table tant que `ECRIRE_RESULTATS = False`. Un mode **démo simulé** est fourni pour tester l'enchaînement sans Fabric (les chiffres de la démo ne sont pas utilisables pour le jury).


# CELL ********************

# 0 — Réglages. Pour les vraies données, connecter le Lakehouse « Mobilite » au notebook.
MODE = "fabric"                 # "demo" (données fictives) ou "fabric" (données réelles)
RAYON_M = 400                 # approximation de 5 min de marche à vol d'oiseau
N_SPLITS = 3                  # validation géographique par commune
SEED = 42
MAX_CARREAUX_NATIONAUX = 350_000  # garde-fou mémoire : aucun échantillonnage silencieux
STRATEGIE_SCORE = "local_enrichi"  # "local_enrichi" si évaluable, sinon repli national ; ou "national"
ECRIRE_RESULTATS = True      # ne créer/écraser aucune table sans décision explicite
NOM_TABLE_RESULTATS = "scores_potentiel_msc3"

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

assert MODE in {"demo", "fabric"}
assert STRATEGIE_SCORE in {"local_enrichi", "national"}
assert RAYON_M == 400, "Vérifier le rayon commun de l'équipe avant de le modifier."
if MODE == "demo":
    assert not ECRIRE_RESULTATS, "Interdiction d'enregistrer les scores d'une démo dans Fabric."
print("Mode :", MODE, "| Rayon :", RAYON_M, "m | Écriture Fabric :", ECRIRE_RESULTATS)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Lecture des tables ou test de démonstration
# En mode Fabric : lecture **Spark** des tables Delta existantes (schéma `dbo`). Le filtrage des communes avec Citiz est réalisé côté Spark **avant** conversion pandas, pour éviter de charger 2,3 millions de carreaux dans le modèle.
# 
# Les colonnes inconnues ou manquantes provoquent un message explicite. Les zones non couvertes par les flux Citiz nationaux ne constituent pas des négatifs fiables : l'entraînement national se limite donc aux communes disposant d'une station rattachée à un carreau INSEE habité (**biais de sélection à signaler au jury**).

# CELL ********************

# Liste de colonnes effectivement présentes dans les notebooks de l'équipe.
COL_BASE = [
    "idcar_200m", "codes_communes", "population", "menages",
    "niveau_vie_moyen", "part_menages_pauvres", "menages_1_personne",
    "age_18_24", "age_25_39", "menages_logement_collectif",
    "menages_proprietaires", "logements_sociaux",
]
COL_VAR = [
    "part_menages_sans_voiture", "voitures_par_menage",
    "part_menages_2_voitures_plus", "part_menages_avec_stationnement",
    "commerces_alimentaires_5min", "autres_commerces_5min", "services_5min",
    "sante_5min", "enseignement_5min", "sport_loisirs_culture_5min",
    "tourisme_5min", "hypermarches_5min", "hopitaux_5min",
    "enseignement_superieur_5min", "gares_5min",
]

def exiger(df, colonnes, nom):
    absentes = [c for c in colonnes if c not in df.columns]
    if absentes:
        raise ValueError(f"{nom} : colonnes absentes : {absentes}")


def colonnes_presentes(df, colonnes):
    return [c for c in colonnes if c in df.columns]


def creer_demo(seed=SEED):
    """Simulation UNIQUEMENT pour vérifier le pipeline, pas une observation sur Toulouse."""
    rng = np.random.default_rng(seed)
    lignes, enrichissements, stations = [], [], []
    for v in range(15):
        ville = f"DEMO-{v:03d}"
        for j in range(110):
            pop = int(rng.integers(25, 600))
            men = max(1, int(pop / rng.uniform(1.4, 2.8)))
            niv = float(rng.uniform(17000, 42000))
            jeunes = int(pop * rng.uniform(.14, .45))
            logement = int(men * rng.uniform(.25, .95))
            x = 3500000 + v * 16000 + (j % 11) * 200 + 100
            y = 2600000 + (j // 11) * 200 + 100
            commerces = int(rng.poisson(3.5))
            sans_voiture = float(rng.uniform(.15, .65))
            proba = 1 / (1 + np.exp(-(-4.0 + pop / 460 + .6 * commerces / 5 + sans_voiture)))
            r = dict(idcar_200m=f"DEMO-GRILLE-{v:03d}-{j:04d}", codes_communes=ville,
                     epsg=3035, population=pop, menages=men, niveau_vie_moyen=niv,
                     part_menages_pauvres=float(rng.uniform(.05,.36)),
                     menages_1_personne=int(men*rng.uniform(.2,.75)),
                     age_18_24=int(jeunes * .4), age_25_39=int(jeunes * .6),
                     menages_logement_collectif=logement,
                     menages_proprietaires=int(men*rng.uniform(.1,.7)),
                     logements_sociaux=int(men*rng.uniform(0,.25)),
                     x_3035=x, y_3035=y)
            lignes.append(r)
            f = dict(idcar_200m=r['idcar_200m'], part_menages_sans_voiture=sans_voiture,
                     voitures_par_menage=float(1.5 - sans_voiture),
                     part_menages_2_voitures_plus=float(rng.uniform(.05,.35)),
                     part_menages_avec_stationnement=float(rng.uniform(.2,.9)))
            for c in COL_VAR[4:]:
                f[c] = commerces if c == 'commerces_alimentaires_5min' else int(rng.poisson(2))
            enrichissements.append(f)
            if rng.random() < proba:
                stations.append(dict(station_id=f"ST-{v}-{j}", idcar_200m=r['idcar_200m'],
                                     x_3035=float(x), y_3035=float(y)))
    nat = pd.DataFrame(lignes)
    enr = pd.DataFrame(enrichissements)
    st = pd.DataFrame(stations)
    # Un sous-ensemble de communes simule Toulouse pour tester aussi les 400 m.
    loc = nat[nat["codes_communes"].isin([f"DEMO-{i:03d}" for i in range(7)])].copy()
    locvar = enr[enr["idcar_200m"].isin(loc["idcar_200m"])].copy()
    tmp = loc.sample(min(len(loc), 320), random_state=seed).reset_index(drop=True)
    ar = pd.DataFrame({"arret_id": [f"STOP-{i}" for i in range(len(tmp))],
                       "x_3035": tmp["x_3035"].to_numpy() + rng.uniform(-70,70,len(tmp)),
                       "y_3035": tmp["y_3035"].to_numpy() + rng.uniform(-70,70,len(tmp))})
    li = pd.DataFrame({"arret_id": ar["arret_id"],
                       "reseau": "DEMO", "ligne_id": [f"LINE-{i%35}" for i in range(len(ar))]})
    velo = loc.sample(min(len(loc), 210), random_state=seed+1)
    part = pd.DataFrame({"operateur": "DEMO-VELO", "type": "velo",
                         "x_3035": velo["x_3035"].to_numpy() + rng.uniform(-80,80,len(velo)),
                         "y_3035": velo["y_3035"].to_numpy() + rng.uniform(-80,80,len(velo))})
    return {"carreaux_france": nat, "carreaux_france_variables": enr,
            "carreaux": loc, "carreaux_variables": locvar,
            "citiz_stations": st, "arrets": ar, "arrets_lignes": li,
            "stations_partagees": part}


def lire_fabric():
    """Lecture des vraies tables. N'ÉCRIT rien. Spark est disponible dans les notebooks Fabric."""
    from pyspark.sql import functions as F
    import notebookutils
    contexte = notebookutils.runtime.context
    espace_lh = contexte.get("defaultLakehouseWorkspaceId")
    id_lh = contexte.get("defaultLakehouseId")
    if not espace_lh or not id_lh:
        raise RuntimeError("Attacher le Lakehouse 'Mobilite' comme Lakehouse par défaut au notebook.")
    endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "")
    racine = f"abfss://{espace_lh}@{endpoint}/{id_lh}"
    def charger(nom):
        try:
            return spark.read.format("delta").load(f"{racine}/Tables/dbo/{nom}")
        except Exception as e:
            raise RuntimeError(f"Impossible de lire dbo.{nom} dans le Lakehouse par défaut (attendu : Mobilite) : {e}") from e
    nat = charger("carreaux_france")
    natv = charger("carreaux_france_variables")
    zone = charger("carreaux")
    zonev = charger("carreaux_variables")
    st = charger("citiz_stations")
    ar = charger("arrets")
    li = charger("arrets_lignes")
    part = charger("stations_partagees")
    if "epsg" not in nat.columns:
        raise ValueError("carreaux_france : 'epsg' absent")
    for nom, t in [("carreaux_france", nat), ("carreaux", zone)]:
        manq = [c for c in COL_BASE if c not in t.columns]
        if manq: raise ValueError(f"{nom}: colonnes absentes {manq}")
    if "idcar_200m" not in st.columns: raise ValueError("citiz_stations : idcar_200m absent")
    ids = st.select("idcar_200m").where(F.col("idcar_200m").isNotNull()).distinct()
    national = (nat.filter((F.col("epsg") == 3035) & (F.col("population") > 0))
                .withColumn("commune_cv", F.trim(F.split(F.coalesce(F.col("codes_communes"), F.lit("")), ",").getItem(0))))
    communes_avec_citiz = (national.join(ids, "idcar_200m", "inner")
                            .select("commune_cv").where(F.col("commune_cv") != "").distinct())
    national = national.join(F.broadcast(communes_avec_citiz), "commune_cv", "inner")
    n = national.count()
    print(f"Communes avec Citiz (carreau habité) : {communes_avec_citiz.count()} | carreaux : {n:,}")
    if n > MAX_CARREAUX_NATIONAUX:
        raise RuntimeError(f"{n:,} carreaux nationaux dépassent MAX_CARREAUX_NATIONAUX={MAX_CARREAUX_NATIONAUX:,}. "
                           "Augmenter ce seuil si la mémoire Fabric le permet ou adapter l'échantillonnage/documentation.")
    variables = national.select(*COL_BASE).join(natv, "idcar_200m", "left")
    cols_zone = COL_BASE + ["x_3035", "y_3035"]
    return {
        "carreaux_france": variables.toPandas(),
        # Le merge est déjà fait à l'étape de lecture ; adapter plus bas selon ce drapeau.
        "carreaux_france_variables": None,
        "carreaux": zone.select(*cols_zone).toPandas(),
        "carreaux_variables": zonev.toPandas(),
        "citiz_stations": st.select(*colonnes_presentes(st, ["station_id", "idcar_200m", "x_3035", "y_3035"])).toPandas(),
        "arrets": ar.select(*colonnes_presentes(ar, ["arret_id", "x_3035", "y_3035"])).toPandas(),
        "arrets_lignes": li.select(*colonnes_presentes(li, ["arret_id", "reseau", "ligne_id"])).toPandas(),
        "stations_partagees": part.select(*colonnes_presentes(part, ["operateur", "type", "x_3035", "y_3035"])).toPandas(),
    }, racine


if MODE == "demo":
    tables = creer_demo()
    racine_fabric = None
    print("ATTENTION : jeu 100 % SIMULÉ ; chiffres sans signification sur Toulouse.")
else:
    tables, racine_fabric = lire_fabric()
for nom, tableau in tables.items():
    print(f"{nom:27s} : {('joint en mémoire' if tableau is None else f'{len(tableau):,} lignes')}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Préparer les variables INSEE, motorisation et équipements
# Jointure sur `idcar_200m`, contrôles de doublons, parts d'âge/ménages et indicateurs `*_5min` créés par `05_variables_carreaux`.
# 
# **Attention à la granularité :** la motorisation est observée à l'IRIS ou à la commune, puis attribuée aux carreaux. Le nombre de commerces / équipements est calculé **dans un cercle de 400 m à vol d'oiseau**, pas le long du réseau piéton. La proximité actuelle des stations Citiz **n'entre pas** dans les variables explicatives : elle sert uniquement au contrôle des candidats.

# CELL ********************

COLS_CANDIDATES = [
    "population", "niveau_vie_moyen", "part_menages_pauvres", "menages",
    "part_menages_1_personne", "part_age_18_39", "part_menages_collectif",
    "part_menages_proprietaires", "part_logements_sociaux",
] + COL_VAR
VARIABLES_TRANSPORT = ["nb_lignes_400m", "nb_velo_400m"]


def assembler(base, var=None, nom="carreaux"):
    exiger(base, COL_BASE, nom)
    if base["idcar_200m"].duplicated().any():
        raise ValueError(f"{nom} : IDs de carreaux en double")
    if var is not None:
        exiger(var, ["idcar_200m"], nom + "_variables")
        if var["idcar_200m"].duplicated().any():
            raise ValueError(f"{nom}_variables : IDs en double")
        chevauch = [c for c in var if c in base.columns and c != "idcar_200m"]
        if chevauch:
            raise ValueError(f"{nom} : variables déjà présentes dans la base : {chevauch}")
        base = base.merge(var, on="idcar_200m", how="left", validate="one_to_one")
    r = base.copy()
    for c in COL_BASE[2:] + COL_VAR:
        if c in r.columns: r[c] = pd.to_numeric(r[c], errors="coerce")
    men = r["menages"].replace(0, np.nan)
    pop = r["population"].replace(0, np.nan)
    r["part_menages_1_personne"] = r["menages_1_personne"] / men
    r["part_age_18_39"] = (r["age_18_24"] + r["age_25_39"]) / pop
    r["part_menages_collectif"] = r["menages_logement_collectif"] / men
    r["part_menages_proprietaires"] = r["menages_proprietaires"] / men
    r["part_logements_sociaux"] = r["logements_sociaux"] / men
    r["commune_cv"] = r["codes_communes"].fillna("").astype(str).str.split(",").str[0].str.strip()
    r = r.loc[(r["population"] > 0) & (r["commune_cv"] != "")].copy()
    return r

national = assembler(tables["carreaux_france"], tables["carreaux_france_variables"], "France")
zone = assembler(tables["carreaux"], tables["carreaux_variables"], "Toulouse")
stations = tables["citiz_stations"].copy()
exiger(stations, ["idcar_200m"], "citiz_stations")
ids_citiz = set(stations["idcar_200m"].dropna().astype(str))
for df in (national, zone):
    df["citiz_present"] = df["idcar_200m"].astype(str).isin(ids_citiz).astype(int)

# La cible nationale 0/1 est entraînée uniquement dans les communes où un carreau positif est repéré.
communes_positives = set(national.loc[national["citiz_present"] == 1, "commune_cv"])
national = national.loc[national["commune_cv"].isin(communes_positives)].copy()
if len(national) == 0 or national["citiz_present"].nunique() != 2:
    raise RuntimeError("Impossible de créer les classes 0 et 1 dans les données nationales.")
print(f"National : {len(national):,} carreaux, {national.citiz_present.sum():,} positifs, "
      f"{national.commune_cv.nunique()} groupes de communes")
print(f"Toulouse : {len(zone):,} carreaux, {zone.citiz_present.sum():,} positifs, "
      f"{zone.commune_cv.nunique()} groupes")
print("Rattachement des stations à des carreaux habités nationaux :", len(ids_citiz.intersection(set(national.idcar_200m))), "/", len(ids_citiz))
print("Variables d'équipement disponibles :", [c for c in COL_VAR if c.endswith("_5min") and c in national.columns])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Lignes TC et stations vélo dans un cercle de 400 m (Toulouse)
# Reprise autonome de la logique de `Maps.ipynb` : une **ligne distincte** est comptée une seule fois par carreau même si elle dessert plusieurs arrêts. On identifie les lignes par `(réseau, ligne_id)`.
# 
# Les stations fixes **de vélo** sont filtrées sur le type `velo` ; on exclut Citiz et les scooters/trottinettes. `nb_citiz_400m` sert uniquement à **retirer les emplacements candidats déjà à proximité d'une station** : ne pas l'utiliser comme variable prédictive (fuite de cible).

# CELL ********************

def points_valides(df, nom):
    exiger(df, ["x_3035", "y_3035"], nom)
    r = df.copy()
    r["x_3035"] = pd.to_numeric(r["x_3035"], errors="coerce")
    r["y_3035"] = pd.to_numeric(r["y_3035"], errors="coerce")
    r = r.dropna(subset=["x_3035", "y_3035"]).reset_index(drop=True)
    return r


def voisins(point_centres, table_points, rayon=400):
    """Liste des indices de points proches de chaque centre ; renvoie des listes vides si table vide."""
    if len(table_points) == 0: return [[] for _ in range(len(point_centres))]
    return cKDTree(table_points[["x_3035", "y_3035"]].to_numpy(dtype=float)).query_ball_point(
        point_centres[["x_3035", "y_3035"]].to_numpy(dtype=float), r=rayon)


def calculer_accessibilite(zone, arrets, arrets_lignes, partagees, stations_citiz):
    exiger(zone, ["idcar_200m", "x_3035", "y_3035"], "carreaux Toulouse")
    ar = points_valides(arrets, "arrets")
    exiger(ar, ["arret_id"], "arrets")
    exiger(arrets_lignes, ["arret_id", "ligne_id"], "arrets_lignes")
    ar = ar.drop_duplicates("arret_id")
    ref = arrets_lignes[[c for c in ["arret_id", "reseau", "ligne_id"] if c in arrets_lignes]].drop_duplicates()
    if "reseau" not in ref: ref["reseau"] = "reseau_inconnu"
    ref["cle_ligne"] = ref["reseau"].fillna("").astype(str) + ":" + ref["ligne_id"].fillna("").astype(str)
    lignes_arret = ref.groupby("arret_id")["cle_ligne"].agg(set).to_dict()
    par_arret = voisins(zone, ar, RAYON_M)
    ids = ar["arret_id"].to_numpy()
    nb_lignes = [len(set().union(*(lignes_arret.get(ids[i], set()) for i in indices))) if indices else 0
                 for indices in par_arret]

    st = points_valides(partagees, "stations_partagees")
    exiger(st, ["operateur", "type"], "stations_partagees")
    # Citiz ne compte pas comme une station vélo ; le reste est typé par le fournisseur.
    velos = st[(st["operateur"] != "Citiz") &
               st["type"].fillna("").str.contains("velo", case=False, regex=False)].copy()
    cz = points_valides(stations_citiz, "citiz_stations")
    # Utiliser la table nationale pour trouver aussi les stations juste au-delà du bord Toulouse.
    res = pd.DataFrame({"idcar_200m": zone["idcar_200m"].to_numpy(),
                        "nb_lignes_400m": nb_lignes,
                        "nb_velo_400m": [len(v) for v in voisins(zone, velos, RAYON_M)],
                        "nb_citiz_400m": [len(v) for v in voisins(zone, cz, RAYON_M)]})
    res["nb_options_hors_citiz_400m"] = res["nb_lignes_400m"] + res["nb_velo_400m"]
    return res

accessibilite = calculer_accessibilite(
    zone, tables["arrets"], tables["arrets_lignes"],
    tables["stations_partagees"], stations
)
zone = zone.merge(accessibilite, on="idcar_200m", how="left", validate="one_to_one")
print("Accessibilité calculée sur", len(zone), "carreaux Toulouse")
print(zone[["nb_lignes_400m", "nb_velo_400m", "nb_citiz_400m"]].describe().round(1).to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Variables retenues et vérifications
# Pour chaque modèle, les valeurs manquantes sont remplacées **par une médiane calculée uniquement sur le pli d'entraînement** (pipeline scikit-learn). Une colonne complètement vide dans le national est exclue des deux modèles. Les indicateurs `*_5min` incluent commerces et équipements, et `nb_lignes_400m` / `nb_velo_400m` sont utilisés **uniquement dans le modèle local**.

# CELL ********************

VARIABLES_BASE = [c for c in COLS_CANDIDATES if c in national.columns and c in zone.columns]
# Imputation médiane impossible si toutes les lignes sont manquantes.
exclues = [c for c in VARIABLES_BASE if national[c].notna().sum() == 0]
VARIABLES_BASE = [c for c in VARIABLES_BASE if c not in exclues]
VARIABLES_LOCALES = [c for c in VARIABLES_BASE if zone[c].notna().sum() > 0] + VARIABLES_TRANSPORT
assert len(VARIABLES_BASE) >= 5, "Pas assez de variables nationales : vérifier la table des variables."
assert all(c in zone.columns for c in VARIABLES_TRANSPORT)
print("Variables nationales retenues :", VARIABLES_BASE)
print("Variables locales enrichies :", VARIABLES_LOCALES)
if exclues: print("Exclues car entièrement vides dans le national :", exclues)
print("Valeurs manquantes nationales (%) :")
print((national[VARIABLES_BASE].isna().mean()*100).round(1).to_string())
print("Valeurs manquantes Toulouse (%) :")
print((zone[VARIABLES_LOCALES].isna().mean()*100).round(1).to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. Entraînement et validation croisée **géographique**
# Deux candidats pour le national (régression logistique standardisée, Random Forest). Idem pour Toulouse, en comparant **sans puis avec** les transports à 400 m : cela mesure si les transports ajoutent un gain sur le même périmètre.
# 
# - Plis créés par `StratifiedGroupKFold`, en regroupant les carreaux par **code de commune**. Une commune entière n'apparaît jamais à la fois à l'entraînement et à l'évaluation.
# - Mesure principale : **Average Precision (AP)**, appropriée aux stations rares, comparée à la proportion positive (*baseline aléatoire*). ROC-AUC en complément.
# - Si les groupes ne permettent pas de validation avec des 0 ET des 1 dans chaque pli, **pas d'évaluation inventée** ; le modèle local ne sera pas retenu.
# - Les scores `predict_proba` sont interprétés ici comme des **scores de classement**, pas comme des probabilités de rentabilité ou de réservations.

# CELL ********************

def modele_logistique():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("normaliser", StandardScaler()),
        ("classifieur", LogisticRegression(max_iter=800, class_weight="balanced", random_state=SEED)),
    ])


def modele_foret():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("classifieur", RandomForestClassifier(n_estimators=90, max_depth=13, min_samples_leaf=7,
                                               class_weight="balanced_subsample", random_state=SEED,
                                               n_jobs=-1)),
    ])

ALGORITHMES = {"logistique": modele_logistique, "random_forest": modele_foret}


def plis_geographiques(df, maximum=N_SPLITS):
    groupes = df["commune_cv"].astype(str)
    cible = df["citiz_present"].astype(int)
    if cible.nunique() < 2: return []
    for k in range(min(maximum, groupes.nunique()), 1, -1):
        try:
            gen = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=SEED)
            plis = list(gen.split(df, cible, groupes))
            if all(cible.iloc[a].nunique() == 2 and cible.iloc[b].nunique() == 2
                   for a, b in plis):
                return plis
        except ValueError:
            continue
    return []


def evaluer(df, variables, nom, plis=None):
    plis = plis if plis is not None else plis_geographiques(df)
    if not plis:
        print(f"ATTENTION — {nom} : validation géographique non faisable avec les groupes/classes disponibles.")
        return pd.DataFrame()
    x = df[variables].apply(pd.to_numeric, errors="coerce")
    y = df["citiz_present"].astype(int)
    lignes = []
    for algo, constructeur in ALGORITHMES.items():
        for i, (a, b) in enumerate(plis, 1):
            mod = constructeur()
            mod.fit(x.iloc[a], y.iloc[a])
            p = mod.predict_proba(x.iloc[b])[:, 1]
            lignes.append({"perimetre": nom, "modele": algo, "pli": i,
                           "n_test": len(b), "positifs_test": int(y.iloc[b].sum()),
                           "baseline_aleatoire": float(y.iloc[b].mean()),
                           "average_precision": float(average_precision_score(y.iloc[b], p)),
                           "roc_auc": float(roc_auc_score(y.iloc[b], p))})
    return pd.DataFrame(lignes)


# L'entraînement national prend les communes ayant au moins une implantation observée.
plis_nationaux = plis_geographiques(national)
if not plis_nationaux:
    raise RuntimeError("Pas de validation nationale valable : examiner les communes et les classes Citiz.")
mesures_national = evaluer(national, VARIABLES_BASE, "national", plis_nationaux)
print("Validation nationale :")
print(mesures_national.groupby("modele")[["average_precision", "roc_auc", "baseline_aleatoire"]].mean().round(3).to_string())

# Toulouse : test rigoureusement apparié des mêmes plis avec et sans TC.
plis_toulouse = plis_geographiques(zone)
mesures_local_base = evaluer(zone, VARIABLES_BASE, "toulouse_sans_transports", plis_toulouse) if plis_toulouse else pd.DataFrame()
mesures_local_enrichi = evaluer(zone, VARIABLES_LOCALES, "toulouse_avec_400m", plis_toulouse) if plis_toulouse else pd.DataFrame()
mesures = pd.concat([m for m in [mesures_national, mesures_local_base, mesures_local_enrichi] if not m.empty], ignore_index=True)
print("\nComparaison (moyenne des plis géographiques) :")
print(mesures.groupby(["perimetre", "modele"])[["average_precision", "roc_auc", "baseline_aleatoire"]].mean().round(3).to_string())
if not plis_toulouse:
    print("ATTENTION : pas assez de groupes/classes pour valider le modèle local ; repli national.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 6. Choisir le modèle et produire les scores Toulouse
# On choisit le meilleur algorithme en AP parmi les modèles évalués. Le modèle local enrichi est utilisé si :
# 1. sa validation géographique a pu être faite ;
# 2. son AP moyenne est supérieure à la prévalence moyenne et **au meilleur modèle local sans transports**, évalué sur les mêmes plis ;
# 3. et la stratégie demandée est `local_enrichi`.
# 
# Sinon, on entraîne le meilleur modèle national. Les deux validations n'ont **pas** la même population, leurs AP ne sont donc **pas directement comparables**. En cas de doute, utiliser `STRATEGIE_SCORE='national'`.
# 
# Pour les **nouveaux emplacements**, on retire les carreaux avec station Citiz ou une station Citiz à moins de 400 m. **On ne retire pas** les carreaux qui ont déjà un bus ou un vélo, puisque l'autopartage peut compléter ces offres.

# CELL ********************

def meilleur_algo(mesures_perimetre):
    return (mesures_perimetre.groupby("modele")["average_precision"].mean()
            .sort_values(ascending=False).index[0])

algo_national = meilleur_algo(mesures_national)
local_eligible = False
if not mesures_local_enrichi.empty:
    m = mesures_local_enrichi.groupby("modele").agg(ap=("average_precision", "mean"),
                                                     base=("baseline_aleatoire", "mean"))
    algo_local = m["ap"].idxmax()
    # Le test national n'est pas comparable en AP avec Toulouse. Comparer les modèles
    # locaux avec/sans transports sur les mêmes plis de communes.
    ap_sans_transports = (mesures_local_base.groupby("modele")["average_precision"].mean().max()
                          if not mesures_local_base.empty else float("nan"))
    local_eligible = bool((m.loc[algo_local, "ap"] > m.loc[algo_local, "base"])
                          and (m.loc[algo_local, "ap"] >= ap_sans_transports))
    print(f"AP locale enrichie = {m.loc[algo_local, 'ap']:.3f} ; "
          f"AP meilleure locale sans transports = {ap_sans_transports:.3f}")
    if not local_eligible:
        print("Le modèle enrichi ne fait pas mieux que la version locale simple ou que l'aléatoire : repli national.")

utiliser_local = (STRATEGIE_SCORE == "local_enrichi" and local_eligible)
if utiliser_local:
    nom_modele = "toulouse_avec_400m"
    algo_retenu = algo_local
    donnees_fit = zone
    colonnes_fit = VARIABLES_LOCALES
else:
    nom_modele = "national"
    algo_retenu = algo_national
    donnees_fit = national
    colonnes_fit = VARIABLES_BASE

modele_final = ALGORITHMES[algo_retenu]()
modele_final.fit(donnees_fit[colonnes_fit], donnees_fit["citiz_present"].astype(int))
zone["score_potentiel"] = modele_final.predict_proba(zone[colonnes_fit])[:, 1]
zone["modele_applique"] = nom_modele + ":" + algo_retenu
zone["transports_dans_modele"] = bool(utiliser_local)

# La stratégie de candidature de l'équipe : zone habitée, pas déjà couverte par Citiz à 400 m.
zone["candidat_citiz"] = ((zone["citiz_present"] == 0) &
                           (zone["nb_citiz_400m"].fillna(0) == 0))
colonnes_sortie = ["idcar_200m", "codes_communes", "population", "score_potentiel",
                   "candidat_citiz", "citiz_present", "nb_citiz_400m", "nb_lignes_400m",
                   "nb_velo_400m", "nb_options_hors_citiz_400m", "modele_applique",
                   "transports_dans_modele"]
for c in ["x_3035", "y_3035"]:
    if c in zone.columns: colonnes_sortie.append(c)
scores = zone[colonnes_sortie].sort_values("score_potentiel", ascending=False).reset_index(drop=True)
candidats = scores[scores["candidat_citiz"]].copy()
assert scores["idcar_200m"].is_unique
assert scores["score_potentiel"].between(0, 1).all()
print("\nModèle retenu :", scores["modele_applique"].iloc[0])
print("Transports à 400 m effectivement utilisés pour prédire ?", bool(utiliser_local))
print(f"Scores calculés : {len(scores):,} carreaux ; candidats sans Citiz à 400 m : {len(candidats):,}")
print("10 meilleurs candidats (à interpréter seulement après validation) :")
print(candidats.head(10).to_string(index=False))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Comprendre les variables influentes
# Les importances d’une Random Forest ou les coefficients d’une régression logistique sont **des indicateurs de fonctionnement du modèle**, pas des effets causaux. Les variables fortement corrélées peuvent partager leur importance.

# CELL ********************

cl = modele_final.named_steps["classifieur"]
if hasattr(cl, "feature_importances_"):
    importances = pd.Series(cl.feature_importances_, index=colonnes_fit).sort_values(ascending=False)
    print("Variables les plus utilisées par le Random Forest :")
    print(importances.head(12).round(3).to_string())
elif hasattr(cl, "coef_"):
    effets = pd.Series(cl.coef_[0], index=colonnes_fit)
    print("Coefficients de régression logistique standardisée (en valeur absolue) :")
    print(effets.reindex(effets.abs().sort_values(ascending=False).index).head(12).round(3).to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 7. Sauvegarde facultative
# `scores` contient un score pour **tous** les carreaux habités de Toulouse et `candidat_citiz` indique si le carreau peut être proposé par l'optimiseur. `candidats` contient uniquement les emplacements sans Citiz à 400 m.
# 
# **Par défaut, aucune écriture** dans le Lakehouse. Une fois les données et le modèle validés, régler `MODE='fabric'` puis `ECRIRE_RESULTATS=True` **après accord de l'équipe** : cela crée / met à jour **uniquement** la table nommée `dbo.scores_potentiel_msc3`, pas les tables sources.

# CELL ********************


if MODE == "fabric" and ECRIRE_RESULTATS:
    sauvegarde = scores.copy()

    for c in [
        "citiz_present", "nb_citiz_400m",
        "nb_lignes_400m", "nb_velo_400m",
        "nb_options_hors_citiz_400m"
    ]:
        sauvegarde[c] = sauvegarde[c].astype("int64")

    nom_table = f"dbo.{NOM_TABLE_RESULTATS}"

    spark_scores = spark.createDataFrame(sauvegarde)

    (spark_scores.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(nom_table))

    print("Table enregistrée :", nom_table)
    print("Nombre de lignes :", spark.table(nom_table).count())

else:
    print("Aucune table écrite.")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
