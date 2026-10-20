# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.11"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "e3b26cda-daa2-4b1c-8fe1-828c20b1b836",
# META       "default_lakehouse_name": "Mobilite",
# META       "default_lakehouse_workspace_id": "94ef609e-283d-424d-9252-6d83b219c77d"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Score de potentiel Citiz, version 2
#
# Reprend le modèle prédictif (`modele_predictif`, table `scores_potentiel_msc3`) sans le
# remplacer : ce notebook écrit deux tables neuves et ne touche à aucune autre.
#
# - `scores_potentiel_v2` : une ligne par carreau de Toulouse Métropole, avec un score de
#   potentiel calibré (la probabilité qu'un carreau de ce profil porte une station Citiz),
#   son rang, une classe de A à E, l'occupation attendue d'une station et les trois raisons
#   principales du score.
# - `usage_stations` : le taux d'occupation mesuré de chaque station des 15 réseaux, avec
#   l'occupation que le modèle d'usage prédit pour elle sans avoir vu son réseau.
#
# Ce qui change par rapport au modèle actuel :
#
# - le modèle apprend sur les 14 autres réseaux Citiz et prédit Toulouse sans l'avoir vue : le
#   test à l'aveugle mesure ce que vaudra le score dans une ville où il n'a rien appris ;
# - un pli de validation laisse de côté un réseau entier, jamais un bout de ville ;
# - les carreaux sans station mais à moins de 400 m d'une station sortent des négatifs :
#   ce sont des emplacements aussi bons, que Citiz n'a simplement pas choisis ;
# - variables disponibles partout en France, dont les emplois (Sirene) et la densité du
#   voisinage à 400 m et 1 km ;
# - le score est calibré : le site le multiplie par la population, son échelle compte ;
# - un second modèle prédit l'usage (taux d'occupation des voitures), mesuré sur les relevés
#   GBFS des 15 réseaux ;
# - chaque carreau reçoit ses trois raisons, regroupées en critères proches de ceux de Citiz.
#
# Rien n'est écrit tant que `ECRIRE_RESULTATS = False`, et une table déjà présente n'est
# jamais écrasée.

# CELL ********************

import json
from datetime import datetime, timezone

import notebookutils
import numpy as np
import pandas as pd
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import DeltaProtocolError, TableNotFoundError
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import lightgbm as lgb
    from pyproj import Transformer
except ImportError:  # absents de certaines images Python de Fabric
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "lightgbm", "pyproj"], check=True)
    import lightgbm as lgb
    from pyproj import Transformer

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Réglages. Aucune écriture tant que ECRIRE_RESULTATS vaut False.
ECRIRE_RESULTATS = False
SEED = 42
RESEAU_TEST = "occitanie"  # réseau de Toulouse : jamais vu à l'entraînement
ZONE_SERVICE_M = 3000  # carreaux d'entraînement : à moins de 3 km d'une station de leur réseau
COURONNE_M = 400  # négatifs ambigus retirés : sans station mais à moins de 400 m d'une
RATTACHEMENT_M = 300  # station dans un carreau inhabité : carreau habité le plus proche
# Gradient boosting peu profond : 400 arbres de 4 niveaux au plus, tirage de lignes et de
# colonnes, pour qu'aucun réseau ne soit appris par cœur.
PARAMS_GB = dict(
    n_estimators=400, learning_rate=0.05, num_leaves=15, max_depth=4, min_child_samples=50,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    random_state=SEED, n_jobs=-1, verbose=-1,
)

contexte = notebookutils.runtime.context
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "")
racine = (
    f"abfss://{contexte['defaultLakehouseWorkspaceId']}@{endpoint}"
    f"/{contexte['defaultLakehouseId']}/Tables/dbo"
)
acces = {
    "bearer_token": notebookutils.credentials.getToken("storage"),
    "use_fabric_endpoint": "true",
}


def lire(table, colonnes=None):
    """Une table du Lakehouse. Celles écrites par Spark avec des « deletion vectors », que
    deltalake ne lit pas encore (scores_potentiel_msc3 par exemple), passent par DuckDB."""
    try:
        return DeltaTable(f"{racine}/{table}", storage_options=acces).to_pandas(columns=colonnes)
    except DeltaProtocolError:
        import os
        import re

        import duckdb

        # le client HTTP de DuckDB ne trouve pas toujours seul les certificats du système
        if os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
            os.environ.setdefault("CURL_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")
        con = duckdb.connect()
        for extension in ("azure", "delta"):
            con.install_extension(extension)
            con.load_extension(extension)
        con.execute("SET azure_transport_option_type = 'curl'")
        # CREATE SECRET n'accepte pas de paramètre « ? » : le jeton est écrit tel quel, après
        # avoir vérifié qu'il n'est fait que de caractères de jeton (aucune injection)
        jeton = acces["bearer_token"]
        if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", jeton):
            raise ValueError("jeton de stockage inattendu")
        con.execute(
            "CREATE SECRET onelake (TYPE azure, PROVIDER access_token, ACCOUNT_NAME 'onelake', "
            f"ACCESS_TOKEN '{jeton}')"
        )
        cols = ", ".join(f'"{c}"' for c in colonnes) if colonnes else "*"
        return con.execute(f"SELECT {cols} FROM delta_scan('{racine}/{table}')").df()


def existe(table):
    try:
        DeltaTable(f"{racine}/{table}", storage_options=acces)
        return True
    except TableNotFoundError:
        return False


print("Lakehouse :", racine, "| écriture :", ECRIRE_RESULTATS)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 1. Lecture
#
# Toute la France (2,3 millions de carreaux habités) avec leurs variables, les carreaux de
# Toulouse Métropole, les 1 615 stations des 15 réseaux, le score actuel pour comparer, et
# l'usage mesuré : la table `usage_stations` si elle existe, sinon il est recalculé depuis
# `citiz_releves` (même définition, cellule 6).

# CELL ********************

COLS_FR = [
    "idcar_200m", "codes_communes", "epsg", "x", "y", "lat", "lon", "population", "menages",
    "niveau_vie_moyen", "part_menages_pauvres", "menages_1_personne", "menages_5_personnes_plus",
    "menages_proprietaires", "menages_monoparentaux", "surface_logements_m2",
    "menages_logement_collectif", "menages_maison", "logements_avant_1945", "logements_sociaux",
    "age_18_24", "age_25_39", "age_65_79", "age_80_plus", "age_0_3", "age_4_5", "age_6_10",
    "age_11_17",
]
fr = lire("carreaux_france", COLS_FR)
frv = lire("carreaux_france_variables")
tls = lire("carreaux", ["idcar_200m"])
stations = lire("citiz_stations")
msc3 = lire("scores_potentiel_msc3", ["idcar_200m", "score_potentiel"])
print(f"{len(fr):,} carreaux France, {len(tls):,} carreaux Toulouse, {len(stations):,} stations")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 2. Variables, disponibles partout en France
#
# Les variables du carreau (Filosofi, motorisation de l'IRIS, équipements et emplois à
# 5 minutes), plus la population à 400 m et à 1 km et le nombre de carreaux habités à 1 km,
# sommés sur la grille de 200 m : un carreau peu peuplé au milieu d'un centre-ville dense
# n'est pas un carreau isolé. Les transports en commun ne sont connus qu'autour de
# Toulouse : seule la présence d'une gare (BPE) représente ce critère dans un modèle
# national.
#
# Les variables sont regroupées en huit critères, au plus près de ceux de Citiz ; les
# raisons d'un score se lisent par critère (cellule 7).

# CELL ********************

# Métropole seulement : l'identifiant donne le coin bas-gauche du carreau en EPSG:3035.
fr = fr[fr["idcar_200m"].str.startswith("CRS3035RES200m")].copy()
fr = fr.merge(
    frv.drop(columns=["code_iris", "rattachement"]), on="idcar_200m", how="left", validate="one_to_one"
)
coords = fr["idcar_200m"].str.extract(r"N(\d+)E(\d+)").astype(np.int64)
fr["cy"], fr["cx"] = coords[0].to_numpy() + 100, coords[1].to_numpy() + 100
fr = fr.reset_index(drop=True)


def somme_voisinage(df, colonne, rayon_m):
    """Somme d'une colonne sur les carreaux dont le centre est à moins de rayon_m (grille de 200 m)."""
    ix, iy = (df["cx"].to_numpy() - 100) // 200, (df["cy"].to_numpy() - 100) // 200
    cle = pd.Index(ix * 10_000_000 + iy)
    valeurs = df[colonne].fillna(0).to_numpy(dtype=float)
    total = np.zeros(len(df))
    r = rayon_m // 200
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            pos = cle.get_indexer((ix + dx) * 10_000_000 + (iy + dy))
            ok = pos >= 0
            total[ok] += valeurs[pos[ok]]
    return total


fr["un"] = 1.0
fr["population_400m"] = somme_voisinage(fr, "population", 400)
fr["population_1km"] = somme_voisinage(fr, "population", 1000)
fr["carreaux_habites_1km"] = somme_voisinage(fr, "un", 1000)
men = fr["menages"].replace(0, np.nan)
pop = fr["population"].replace(0, np.nan)
fr["part_menages_1_personne"] = fr["menages_1_personne"] / men
fr["part_menages_5_plus"] = fr["menages_5_personnes_plus"] / men
fr["part_menages_collectif"] = fr["menages_logement_collectif"] / men
fr["part_menages_proprietaires"] = fr["menages_proprietaires"] / men
fr["part_menages_monoparentaux"] = fr["menages_monoparentaux"] / men
fr["part_logements_sociaux"] = fr["logements_sociaux"] / men
fr["part_logements_avant_1945"] = fr["logements_avant_1945"] / men
fr["surface_par_menage"] = fr["surface_logements_m2"] / men
fr["part_age_18_39"] = (fr["age_18_24"] + fr["age_25_39"]) / pop
fr["part_age_65_plus"] = (fr["age_65_79"] + fr["age_80_plus"]) / pop
fr["part_moins_18"] = (fr["age_0_3"] + fr["age_4_5"] + fr["age_6_10"] + fr["age_11_17"]) / pop
fr["emplois_par_habitant_400m"] = fr["emplois_5min"] / (fr["population_400m"] + 50)

# critère -> (variables, raison quand il pousse le score vers le haut, puis vers le bas)
CRITERES = {
    "transports": (["gares_5min"], "Gare à 5 min à pied", "Pas de gare à 5 min"),
    "densite": (
        ["population", "menages", "population_400m", "population_1km", "carreaux_habites_1km"],
        "Quartier dense", "Quartier peu dense",
    ),
    "mixite": (
        ["emplois_5min", "emplois_carreau", "emplois_par_habitant_400m", "commerces_alimentaires_5min",
         "autres_commerces_5min", "services_5min", "sante_5min", "enseignement_5min",
         "sport_loisirs_culture_5min", "tourisme_5min", "enseignement_superieur_5min", "hopitaux_5min",
         "hypermarches_5min"],
        "Mixité habitat, emplois et commerces", "Peu d'emplois et de commerces autour",
    ),
    "motorisation": (
        ["part_menages_sans_voiture", "voitures_par_menage", "part_menages_2_voitures_plus"],
        "Ménages peu motorisés", "Ménages très motorisés",
    ),
    "stationnement": (
        ["part_menages_avec_stationnement"], "Peu de places de parking privées", "Parking privé courant",
    ),
    "habitat": (
        ["part_menages_collectif", "part_logements_avant_1945", "surface_par_menage",
         "part_menages_proprietaires", "part_logements_sociaux"],
        "Habitat collectif de centre-ville", "Habitat individuel ou peu adapté",
    ),
    "menages": (
        ["part_menages_1_personne", "part_menages_5_plus", "part_menages_monoparentaux", "part_age_18_39",
         "part_age_65_plus", "part_moins_18"],
        "Petits ménages, jeunes actifs", "Profil des ménages peu favorable",
    ),
    "revenus": (
        ["niveau_vie_moyen", "part_menages_pauvres"], "Niveau de vie favorable", "Niveau de vie peu favorable",
    ),
}
VARIABLES = [v for vs, _, _ in CRITERES.values() for v in vs]
CRITERE_DE = {v: k for k, (vs, _, _) in CRITERES.items() for v in vs}
# Les 24 variables du modèle actuel, pour comparer les deux jeux à méthode égale.
VARIABLES_MSC3 = [
    "population", "niveau_vie_moyen", "part_menages_pauvres", "menages", "part_menages_1_personne",
    "part_age_18_39", "part_menages_collectif", "part_menages_proprietaires", "part_logements_sociaux",
    "part_menages_sans_voiture", "voitures_par_menage", "part_menages_2_voitures_plus",
    "part_menages_avec_stationnement", "commerces_alimentaires_5min", "autres_commerces_5min",
    "services_5min", "sante_5min", "enseignement_5min", "sport_loisirs_culture_5min", "tourisme_5min",
    "hypermarches_5min", "hopitaux_5min", "enseignement_superieur_5min", "gares_5min",
]
print(len(VARIABLES), "variables en", len(CRITERES), "critères")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 3. Cible et périmètres
#
# - Cible : le carreau porte au moins une station Citiz réelle (les stations virtuelles ne
#   comptent pas). Une station dans un carreau inhabité, absent de la grille, est rattachée
#   au carreau habité le plus proche, à 300 m au plus.
# - Entraînement : les carreaux à moins de 3 km d'une station des 14 autres réseaux. Au-delà,
#   l'absence de Citiz dit où la coopérative n'est pas implantée, pas ce que vaut le carreau.
# - Les carreaux sans station mais à moins de 400 m d'une station sortent des négatifs.
# - Test : les 7 070 carreaux de Toulouse Métropole, tous, couronne comprise ; le réseau
#   `occitanie` n'est jamais vu à l'entraînement.

# CELL ********************

arbre = cKDTree(fr[["cx", "cy"]].to_numpy(dtype=float))
st = stations.dropna(subset=["x_3035", "y_3035"]).copy()
d, i = arbre.query(st[["x_3035", "y_3035"]].to_numpy(dtype=float))
st["carreau"] = np.where(d <= RATTACHEMENT_M, fr["idcar_200m"].to_numpy()[i], None)
print("stations rattachées à un carreau habité :", int(st["carreau"].notna().sum()), "/", len(st))
reelles = st[~st["virtuelle"].fillna(False).astype(bool) & st["carreau"].notna()]
nb_stations = reelles.groupby("carreau").size()
fr["nb_stations"] = fr["idcar_200m"].map(nb_stations).fillna(0).astype(int)
fr["citiz"] = (fr["nb_stations"] > 0).astype(int)

# Distance de chaque carreau à la station la plus proche, et réseau de cette station.
arbre_st = cKDTree(st[["x_3035", "y_3035"]].to_numpy(dtype=float))
d_st, i_st = arbre_st.query(fr[["cx", "cy"]].to_numpy(dtype=float))
fr["distance_station_m"] = d_st
fr["reseau"] = st["reseau"].to_numpy()[i_st]
fr["toulouse"] = fr["idcar_200m"].isin(set(tls["idcar_200m"]))

entr = fr[(fr["distance_station_m"] <= ZONE_SERVICE_M) & (fr["reseau"] != RESEAU_TEST) & ~fr["toulouse"]]
entr = entr[(entr["citiz"] == 1) | (entr["distance_station_m"] > COURONNE_M)].reset_index(drop=True)
test = fr[fr["toulouse"]].reset_index(drop=True)
print(
    f"entraînement : {len(entr):,} carreaux, {entr.citiz.sum()} positifs, {entr.reseau.nunique()} réseaux ;"
    f" test Toulouse : {len(test):,} carreaux, {test.citiz.sum()} positifs"
)
assert len(test) == len(tls), "carreaux de Toulouse absents de carreaux_france"
assert RESEAU_TEST not in set(entr["reseau"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 4. Validation : un réseau de côté à chaque pli, puis calibration
#
# Quatorze plis : chaque réseau est prédit par un modèle appris sur les treize autres. Trois
# candidats : gradient boosting sur les variables v2, régression logistique sur les mêmes,
# et gradient boosting sur les 24 variables du modèle actuel (l'apport des nouvelles
# variables, à méthode égale). Mesures : ROC-AUC, AP (à comparer au taux de base), et la
# part des stations tombées dans les 10 % et 20 % de carreaux les mieux notés.
#
# Calibration : méthode de Platt (régression logistique sur le logit du score), apprise sur
# les prédictions hors réseau ; elle garde l'ordre des carreaux, l'isotonique crée des ex
# aequo. Les deux sont jugées par le score de Brier, apprises sur 13 réseaux et mesurées sur
# le 14e, puis sur Toulouse.

# CELL ********************


def gb():
    return lgb.LGBMClassifier(**PARAMS_GB)


def logistique():
    return Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("std", StandardScaler()),
        ("lr", LogisticRegression(max_iter=1000)),
    ])


def hors_reseau(df, variables, fabrique, cible="citiz"):
    """Prédictions hors échantillon : chaque réseau est prédit par un modèle qui ne l'a pas vu."""
    p = np.zeros(len(df))
    for r in sorted(df["reseau"].unique()):
        a, b = df["reseau"] != r, df["reseau"] == r
        m = fabrique().fit(df.loc[a, variables], df.loc[a, cible])
        p[b.to_numpy()] = m.predict_proba(df.loc[b, variables])[:, 1]
    return p


def part_stations_top(score, nb_st, part):
    """Part des stations dont le carreau est dans les `part` meilleurs carreaux."""
    seuil = np.quantile(score, 1 - part)
    return float(nb_st[score >= seuil].sum() / nb_st.sum())


def mesures(y, p, nb_st=None):
    r = {"roc_auc": roc_auc_score(y, p), "ap": average_precision_score(y, p), "taux_base": float(np.mean(y))}
    if nb_st is not None:
        r["stations_top10"] = part_stations_top(p, nb_st, 0.10)
        r["stations_top20"] = part_stations_top(p, nb_st, 0.20)
    return {k: round(float(v), 4) for k, v in r.items()}


resultats = {}
oof = {}
for nom, variables, fabrique in [
    ("v2_gb", VARIABLES, gb),
    ("v2_logistique", VARIABLES, logistique),
    ("24var_gb", VARIABLES_MSC3, gb),
]:
    oof[nom] = hors_reseau(entr, variables, fabrique)
    par_reseau = {
        r: mesures(entr.loc[entr.reseau == r, "citiz"], oof[nom][entr.reseau == r])["roc_auc"]
        for r in sorted(entr.reseau.unique())
    }
    resultats[f"validation_14_reseaux_{nom}"] = {
        **mesures(entr["citiz"], oof[nom], entr["nb_stations"].to_numpy()),
        "roc_auc_par_reseau": par_reseau,
    }
    print(nom, resultats[f"validation_14_reseaux_{nom}"])

def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


class Platt:
    """Calibration de Platt : régression logistique sur le logit du score brut. Elle garde
    l'ordre des carreaux (aucun ex aequo), à la différence de l'isotonique."""

    def fit(self, p, y):
        self.lr = LogisticRegression(C=1e6).fit(logit(p), y)
        return self

    def predict(self, p):
        return self.lr.predict_proba(logit(p))[:, 1]


class Isotonique:
    def fit(self, p, y):
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p, y)
        return self

    def predict(self, p):
        return self.iso.predict(p)


# Brier mesuré proprement : le calibreur est appris sur 13 réseaux et jugé sur le 14e.
p_brut = oof["v2_gb"]
y_e = entr["citiz"].to_numpy()
calib = {
    "brier_brut": round(brier_score_loss(y_e, p_brut), 5),
    "brier_taux_constant": round(brier_score_loss(y_e, np.full(len(y_e), y_e.mean())), 5),
}
for nom, Calibreur in [("platt", Platt), ("isotonique", Isotonique)]:
    p_cal = np.zeros(len(entr))
    for r in sorted(entr["reseau"].unique()):
        a, b = (entr["reseau"] != r).to_numpy(), (entr["reseau"] == r).to_numpy()
        p_cal[b] = Calibreur().fit(p_brut[a], y_e[a]).predict(p_brut[b])
    calib[f"brier_{nom}"] = round(brier_score_loss(y_e, p_cal), 5)
resultats["calibration_14_reseaux"] = calib
calibreur = Platt().fit(p_brut, y_e)
isotonique = Isotonique().fit(p_brut, y_e)
print("calibration", resultats["calibration_14_reseaux"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 5. Test à l'aveugle sur Toulouse
#
# Le modèle final apprend sur les 14 réseaux et note les 7 070 carreaux de Toulouse
# Métropole, qu'il n'a jamais vus. Le score actuel (`scores_potentiel_msc3`) est mesuré de la
# même façon, mais il a appris sur Toulouse : ses chiffres sont des chiffres d'entraînement,
# donc flatteurs. L'intervalle à 95 % vient de 1 000 tirages des carreaux.

# CELL ********************

modele = gb().fit(entr[VARIABLES], entr["citiz"])
test["score_brut"] = modele.predict_proba(test[VARIABLES])[:, 1]
test["score_potentiel"] = calibreur.predict(test["score_brut"])
test["score_isotonique"] = isotonique.predict(test["score_brut"])
modele24 = gb().fit(entr[VARIABLES_MSC3], entr["citiz"])
test["score_24var"] = modele24.predict_proba(test[VARIABLES_MSC3])[:, 1]
test = test.merge(
    msc3.rename(columns={"score_potentiel": "score_msc3"}), on="idcar_200m", how="left"
)
y_t, n_t = test["citiz"].to_numpy(), test["nb_stations"].to_numpy()
hors_couronne = ((test["citiz"] == 1) | (test["distance_station_m"] > COURONNE_M)).to_numpy()
for nom in ["score_potentiel", "score_isotonique", "score_24var", "score_msc3"]:
    resultats[f"toulouse_{nom}"] = mesures(y_t, test[nom].to_numpy(), n_t)
    resultats[f"toulouse_{nom}_sans_couronne"] = mesures(
        y_t[hors_couronne], test[nom].to_numpy()[hors_couronne], n_t[hors_couronne]
    )
    print("Toulouse", nom, resultats[f"toulouse_{nom}"])
resultats["toulouse_brier"] = {
    "brut": round(brier_score_loss(y_t, test["score_brut"]), 5),
    "platt": round(brier_score_loss(y_t, test["score_potentiel"]), 5),
    "isotonique": round(brier_score_loss(y_t, test["score_isotonique"]), 5),
    "taux_constant": round(brier_score_loss(y_t, np.full(len(y_t), y_t.mean())), 5),
    "msc3": round(brier_score_loss(y_t, test["score_msc3"]), 5),
    "somme_scores_calibres": round(float(test["score_potentiel"].sum()), 1),
    "moyenne_msc3": round(float(test["score_msc3"].mean()), 4),
    "carreaux_avec_station": int(y_t.sum()),
    "stations_rattachees": int(n_t.sum()),
}
print("Brier Toulouse", resultats["toulouse_brier"])

rng = np.random.default_rng(SEED)
boots = []
for _ in range(1000):
    k = rng.integers(0, len(test), len(test))
    if y_t[k].sum() == 0:
        continue
    boots.append((
        roc_auc_score(y_t[k], test["score_potentiel"].to_numpy()[k]),
        part_stations_top(test["score_potentiel"].to_numpy()[k], n_t[k], 0.20),
    ))
boots = np.array(boots)
resultats["toulouse_intervalles_95"] = {
    "roc_auc": np.percentile(boots[:, 0], [2.5, 97.5]).round(3).tolist(),
    "stations_top20": np.percentile(boots[:, 1], [2.5, 97.5]).round(3).tolist(),
}
print("intervalles", resultats["toulouse_intervalles_95"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 6. Modèle d'usage
#
# Cible : le taux d'occupation d'une station, la part des couples (voiture, relevé) où la
# voiture est réservée, sur les heures facturées (7 h-23 h, heure de Paris), mesuré par les
# relevés GBFS toutes les 10 minutes. Une voiture reste rattachée à sa station : seul
# `reserve` dit qu'elle est prise. Les stations de moins de 100 relevés sont écartées.
#
# Modèle volontairement simple (arbres de 2 niveaux, ou régression ridge), validé en
# laissant un réseau de côté, comparé à la moyenne des autres réseaux. Avec un jour et demi de
# relevés, la mesure est bruitée : l'intervalle du Spearman vient de 1 000 tirages des
# stations.

# CELL ********************


def calculer_usage(releves, stations, ids_toulouse):
    """Une ligne par station : part des couples (voiture, relevé) où la voiture est réservée,
    sur 24 h et sur les heures facturées (7 h-23 h, heure de Paris)."""
    r = releves.copy()
    r["station_cle"] = r["reseau"] + ":" + r["station_id"].astype(str)
    heure = r["releve_utc"].dt.tz_convert("Europe/Paris").dt.hour
    r["facture"] = (heure >= 7) & (heure < 23)
    r["reserve"] = r["reserve"].astype(float)
    g = r.groupby(["reseau", "station_cle"])
    u = pd.DataFrame({
        "nb_voitures": g["vehicule_id"].nunique(),
        "nb_releves": g["releve_utc"].nunique(),
        "occupation_24h": g["reserve"].mean(),
        "part_desactivees": g["desactive"].mean(),
    })
    u["occupation_jour"] = r[r["facture"]].groupby(["reseau", "station_cle"])["reserve"].mean()
    u = u.reset_index()
    pos = stations[["station_id", "lat", "lon", "idcar_200m"]].rename(columns={"station_id": "station_cle"})
    u = u.merge(pos, on="station_cle", how="left")
    u["dans_zone"] = u["idcar_200m"].isin(ids_toulouse)
    u["debut_utc"], u["fin_utc"] = r["releve_utc"].min(), r["releve_utc"].max()
    return u


COLS_USAGE = [
    "reseau", "station_cle", "nb_voitures", "nb_releves", "occupation_24h", "lat", "lon",
    "part_desactivees", "occupation_jour", "idcar_200m", "dans_zone", "debut_utc", "fin_utc",
]
if existe("usage_stations"):
    usage = lire("usage_stations", COLS_USAGE)
else:
    releves = lire(
        "citiz_releves", ["releve_utc", "reseau", "vehicule_id", "station_id", "reserve", "desactive"]
    )
    releves["releve_utc"] = pd.to_datetime(releves["releve_utc"], utc=True)
    usage = calculer_usage(releves, stations, set(tls["idcar_200m"]))
print(len(usage), "stations avec usage")

u = usage.copy()
vers_m = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
ux, uy = vers_m.transform(u["lon"].to_numpy(), u["lat"].to_numpy())
du, iu = arbre.query(np.c_[ux, uy])
u["carreau_variables"] = np.where(du <= RATTACHEMENT_M, fr["idcar_200m"].to_numpy()[iu], None)
u = u.merge(
    fr[["idcar_200m"] + VARIABLES].rename(columns={"idcar_200m": "carreau_variables"}),
    on="carreau_variables", how="left",
)
u_ok = u[u["carreau_variables"].notna() & (u["nb_releves"] >= 100)].reset_index(drop=True)
print("usage : stations avec variables et assez de relevés :", len(u_ok), "/", len(u))


def gb_usage():
    return lgb.LGBMRegressor(
        n_estimators=200, learning_rate=0.03, num_leaves=4, max_depth=2, min_child_samples=30,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
        random_state=SEED, n_jobs=-1, verbose=-1,
    )


def ridge_usage():
    return Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("std", StandardScaler()),
        ("r", Ridge(alpha=30.0)),
    ])


CIBLE_USAGE = "occupation_jour"
y_u = u_ok[CIBLE_USAGE].to_numpy()
pred_u = {}
for nom, fabrique in [("gb", gb_usage), ("ridge", ridge_usage)]:
    p = np.zeros(len(u_ok))
    for r in sorted(u_ok["reseau"].unique()):
        a, b = (u_ok["reseau"] != r).to_numpy(), (u_ok["reseau"] == r).to_numpy()
        p[b] = fabrique().fit(u_ok.loc[a, VARIABLES], y_u[a]).predict(u_ok.loc[b, VARIABLES])
    pred_u[nom] = p
    naif = np.array([u_ok.loc[u_ok.reseau != r, CIBLE_USAGE].mean() for r in u_ok["reseau"]])
    tl = (u_ok["reseau"] == RESEAU_TEST).to_numpy()
    resultats[f"usage_{nom}"] = {
        "spearman": round(float(spearmanr(y_u, p).statistic), 3),
        "spearman_toulouse_reseau": round(float(spearmanr(y_u[tl], p[tl]).statistic), 3),
        "mae": round(mean_absolute_error(y_u, p), 4),
        "mae_naif": round(mean_absolute_error(y_u, naif), 4),
        "n": int(len(u_ok)),
    }
    print("usage", nom, resultats[f"usage_{nom}"])

meilleur_u = max(pred_u, key=lambda k: resultats[f"usage_{k}"]["spearman"])
b_sp = []
for _ in range(1000):
    k = rng.integers(0, len(u_ok), len(u_ok))
    b_sp.append(spearmanr(y_u[k], pred_u[meilleur_u][k]).statistic)
resultats[f"usage_{meilleur_u}"]["spearman_ic95"] = np.percentile(b_sp, [2.5, 97.5]).round(3).tolist()
u_ok["occupation_prevue_hors_echantillon"] = pred_u[meilleur_u]

# Score de présence contre usage mesuré, sur les stations de Toulouse Métropole.
ut = u_ok[u_ok["dans_zone"]].merge(
    test[["idcar_200m", "score_potentiel", "score_brut", "score_msc3"]].rename(
        columns={"idcar_200m": "carreau_variables"}
    ),
    on="carreau_variables", how="left",
)
corr = {"n_stations": int(len(ut))}
for nom in ["score_brut", "score_msc3"]:
    ok = ut[nom].notna()
    xs, ys = ut.loc[ok, nom].to_numpy(), ut.loc[ok, CIBLE_USAGE].to_numpy()
    bs = []
    for _ in range(1000):
        k = rng.integers(0, len(xs), len(xs))
        bs.append(spearmanr(xs[k], ys[k]).statistic)
    corr[nom] = {
        "spearman": round(float(spearmanr(xs, ys).statistic), 3),
        "ic95": np.nanpercentile(bs, [2.5, 97.5]).round(3).tolist(),
        "n": int(ok.sum()),
    }
resultats["toulouse_presence_contre_usage"] = corr
print("présence contre usage", corr)

# Modèle d'usage final (toutes les stations), appliqué à chaque carreau de Toulouse.
modele_u = (gb_usage if meilleur_u == "gb" else ridge_usage)().fit(u_ok[VARIABLES], y_u)
test["occupation_prevue"] = np.clip(modele_u.predict(test[VARIABLES]), 0, 1)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 7. Les trois raisons de chaque score
#
# Contribution de chaque variable au score d'un carreau (valeurs de Shapley des arbres,
# calculées par LightGBM), sommée par critère. Les trois critères qui pèsent le plus, dans un
# sens ou dans l'autre, donnent les raisons : « Quartier dense » s'il pousse le score vers le
# haut, « Quartier peu dense » s'il le tire vers le bas. Ce sont des raisons du modèle, pas
# des causes : deux variables liées se partagent leur poids.

# CELL ********************

contrib = modele.predict_proba(test[VARIABLES], pred_contrib=True)[:, :-1]
par_critere = pd.DataFrame(contrib, columns=VARIABLES).T.groupby(CRITERE_DE).sum().T
raisons = []
for _, ligne in par_critere.iterrows():
    tri = ligne.reindex(ligne.abs().sort_values(ascending=False).index)[:3]
    raisons.append([CRITERES[c][1] if v > 0 else CRITERES[c][2] for c, v in tri.items()])
test[["raison_1", "raison_2", "raison_3"]] = pd.DataFrame(raisons)
resultats["importance_criteres_toulouse"] = (
    par_critere.abs().mean().sort_values(ascending=False).round(3).to_dict()
)
print("importance des critères", resultats["importance_criteres_toulouse"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## 8. Sorties
#
# - `score_potentiel` : la probabilité calibrée, entre 0 et 1, qu'un carreau de ce profil
#   porte une station Citiz. C'est la colonne que le site multiplie par la population.
# - `rang_centile` (0 à 100) et `classe` : A pour les 20 % de carreaux les mieux notés, puis
#   B, C, D et E par tranches de 20 %.
# - `occupation_prevue` : le taux d'occupation attendu d'une station dans ce carreau.
# - horodatage `calcule_utc` en UTC, avec fuseau.
#
# Écriture seulement si `ECRIRE_RESULTATS = True`, et seulement dans une table absente.

# CELL ********************

maintenant = pd.Timestamp(datetime.now(timezone.utc))
test["rang_centile"] = (test["score_potentiel"].rank(pct=True, method="average") * 100).round(1)
test["classe"] = pd.cut(test["rang_centile"], [-1, 20, 40, 60, 80, 100.1], labels=list("EDCBA")).astype(str)
scores_v2 = test[[
    "idcar_200m", "score_potentiel", "rang_centile", "classe", "occupation_prevue", "raison_1",
    "raison_2", "raison_3", "score_brut", "nb_stations", "distance_station_m",
]].copy()
scores_v2["nb_stations"] = scores_v2["nb_stations"].astype("int64")
scores_v2["modele"] = "potentiel_v2:gb_aveugle_toulouse"
scores_v2["calcule_utc"] = maintenant
assert scores_v2["idcar_200m"].is_unique and len(scores_v2) == len(tls)
assert scores_v2["score_potentiel"].between(0, 1).all()

usage_sortie = usage[COLS_USAGE].merge(
    u_ok[["station_cle", "occupation_prevue_hors_echantillon"]], on="station_cle", how="left"
)
usage_sortie["calcule_utc"] = maintenant
print(json.dumps(resultats, indent=1, ensure_ascii=False, default=float))
print(scores_v2["classe"].value_counts().sort_index().to_dict())

if ECRIRE_RESULTATS:
    for nom, df in [("scores_potentiel_v2", scores_v2), ("usage_stations", usage_sortie)]:
        if existe(nom):
            print(f"{nom} existe déjà : rien n'est écrit")
            continue
        write_deltalake(f"{racine}/{nom}", df, mode="error", storage_options=acces)
        print(f"{nom} : {len(df)} lignes écrites")
else:
    print("Aucune table écrite (ECRIRE_RESULTATS = False).")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
