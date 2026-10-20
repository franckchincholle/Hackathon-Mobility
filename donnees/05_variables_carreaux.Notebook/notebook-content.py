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

# # Variables des carreaux : motorisation et équipements
# 
# Décrit les habitants et l'environnement de chaque carreau de 200 m, pour le modèle
# (décision 7) et les cartes. Quatre tables :
# 
# - `iris` : un IRIS (quartier INSEE d'environ 2 000 habitants) par ligne, avec la
#   motorisation de ses ménages (recensement 2023, publié le 20 octobre 2026) et, pour les
#   IRIS de la zone, leur contour.
# - `equipements` : les équipements de la zone et à moins de `rayon_m` (base permanente des
#   équipements 2025 : commerces, services, santé, enseignement, sport...), pour les cartes.
# - `carreaux_variables` et `carreaux_france_variables` : une ligne par carreau, même clé
#   `idcar_200m` que `carreaux` et `carreaux_france`. On y trouve l'IRIS du carreau, la
#   motorisation qui s'y applique, le nombre d'équipements par famille et le nombre
#   d'emplois salariés, dans le carreau (`_carreau`) et à moins de `rayon_m` de son centre
#   (`_5min`, le même rayon que pour les transports).
# 
# Les emplois viennent du répertoire Sirene, mis à jour chaque mois : les établissements
# actifs qui déclarent une tranche d'effectif salarié (au 31 décembre 2024), placés par la
# géolocalisation de l'INSEE et comptés pour le milieu de leur tranche (15 000 pour la
# tranche « 10 000 et plus »). Le total de la France, 27,3 millions, retombe sur les 27,0
# millions de salariés que compte l'INSEE. Les établissements placés au hasard dans leur
# commune (qualité 33) ne comptent pas. Une structure qui déclare tout son personnel à une
# adresse (mairie, CHU sur plusieurs sites) le concentre en un point.
# 
# La motorisation n'existe pas au carreau. Chaque carreau prend celle de l'IRIS où tombe son
# centre (`rattachement` = iris), celle de sa commune si elle n'est pas découpée en IRIS
# (= commune), ou celle de l'ensemble des communes qu'il touche s'il est à cheval sur
# plusieurs communes non découpées (= communes). Les contours des IRIS viennent de l'IGN ;
# seuls ceux des communes découpées sont chargés.
# 
# Les réglages viennent de la bibliothèque de variables `parametres_mobilite` ; 01_carreaux
# doit avoir tourné avant, avec le même jeu de valeurs.

# CELL ********************

import json
import math
import os
import tempfile
import time

import notebookutils
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import requests
from deltalake import DeltaTable, write_deltalake
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from pyproj import Transformer
    from scipy.spatial import cKDTree
except ImportError:  # absents de certaines images Python de Fabric
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "pyproj", "scipy"], check=True
    )
    from pyproj import Transformer
    from scipy.spatial import cKDTree

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Réglages partagés par les notebooks : bibliothèque de variables de l'espace.
parametres = notebookutils.variableLibrary.getLibrary("parametres_mobilite")
LAKEHOUSE = parametres.lakehouse
RAYON_M = int(parametres.rayon_m)
RETELECHARGER = str(parametres.retelecharger_insee).lower() == "true"
URL_LOGEMENT = "https://api.insee.fr/melodi/file/DS_RP_LOGEMENT_PRINC_IRIS_2023/PARQUET"
URL_BPE = "https://www.insee.fr/fr/statistiques/fichier/8217525/BPE25.parquet"
# Sirene sur data.gouv.fr : adresses stables, qui mènent au fichier du mois.
URL_SIRENE_STOCK = (
    "https://www.data.gouv.fr/api/1/datasets/r/a29c1297-1f92-4e2a-8f6b-8c902ce96c5f"
)
URL_SIRENE_GEOLOC = (
    "https://www.data.gouv.fr/api/1/datasets/r/672007af-0146-491f-835c-8314d63fa44e"
)
# Effectif salarié retenu pour chaque tranche de Sirene : le milieu de la tranche.
EFFECTIF_TRANCHE = {
    "01": 1.5,
    "02": 4.0,
    "03": 7.5,
    "11": 14.5,
    "12": 34.5,
    "21": 74.5,
    "22": 149.5,
    "31": 224.5,
    "32": 374.5,
    "41": 749.5,
    "42": 1499.5,
    "51": 3499.5,
    "52": 7499.5,
    "53": 15000.0,
}
WFS_IGN = "https://data.geopf.fr/wfs/ows"
COUCHE_IRIS = "STATISTICALUNITS.IRIS:contours_iris"
# Recensement 2023, au format long des normes européennes : une ligne par unité (IRIS, ou
# commune non découpée) et par croisement de modalités. On garde les résidences
# principales (autant que de ménages), toutes autres modalités confondues (« _T »)...
FILTRES_LOGEMENT = [("RP_MEASURE", "=", "DWELLINGS"), ("OCS", "=", "DW_MAIN")] + [
    (dimension, "=", "_T")
    for dimension in ("TDW", "L_STAY", "NRG_SRC", "NOR", "TSH", "BUILD_END", "UFS")
]
# ...puis on lit chaque compte de ménages par son nombre de voitures (CARS) et son
# emplacement réservé de stationnement (CARPARK). Anciens noms : P22_MEN, P22_RP_VOIT1P,
# P22_RP_VOIT1, P22_RP_VOIT2P et P22_RP_GARL (table de passage de l'INSEE).
COMPTES = {
    ("_T", "_T"): "menages",
    ("C_GE1", "_T"): "menages_avec_voiture",
    ("C1", "_T"): "menages_1_voiture",
    ("C_GE2", "_T"): "menages_2_voitures_plus",
    ("_T", "1"): "menages_avec_stationnement",
}
# Familles d'équipements, par sous-domaine de la BPE (nomenclature 2025). L'action sociale,
# l'automobile, le bâtiment et les transports n'en font pas partie : ils ne font pas venir
# les habitants à pied.
FAMILLES = {
    "B2": "commerces_alimentaires",
    "B3": "autres_commerces",
    "A1": "services",
    "A2": "services",
    "A5": "services",
    "D1": "sante",
    "D2": "sante",
    "D3": "sante",
    "C1": "enseignement",
    "C2": "enseignement",
    "C3": "enseignement",
    "C4": "enseignement",
    "C5": "enseignement",
    "C6": "enseignement",
    "C7": "enseignement",
    "F1": "sport_loisirs_culture",
    "F2": "sport_loisirs_culture",
    "F3": "sport_loisirs_culture",
    "G1": "tourisme",
}
# Les grandes surfaces (B1) se répartissent selon ce qu'elles vendent.
FAMILLES_TYPES = {
    "B104": "commerces_alimentaires",
    "B105": "commerces_alimentaires",
    "B103": "autres_commerces",
}
# Pôles qui attirent des déplacements au-delà du quartier.
POLES = {
    "B104": "hypermarches",
    "D101": "hopitaux",
    **{f"C50{k}": "enseignement_superieur" for k in (1, 2, 3, 4, 5, 9)},
    "E107": "gares",
    "E108": "gares",
    "E109": "gares",
}
print(f"Tables écrites dans le Lakehouse {LAKEHOUSE}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

espace = notebookutils.runtime.context["currentWorkspaceId"]
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "")
acces = {
    "bearer_token": notebookutils.credentials.getToken("storage"),
    "use_fabric_endpoint": "true",
}
dossier_local = tempfile.mkdtemp()
# Quatre essais espacés de 2, 4 puis 8 s : les serveurs coupent parfois une connexion.
session = requests.Session()
session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
        )
    ),
)


def api_fabric(methode, chemin, **options):
    """Appel à l'API REST de Fabric, dans l'espace du notebook, avec le jeton du notebook."""
    reponse = requests.request(
        methode,
        f"https://api.fabric.microsoft.com/v1/workspaces/{espace}/{chemin}",
        headers={
            "Authorization": f"Bearer {notebookutils.credentials.getToken('pbi')}"
        },
        timeout=120,
        **options,
    )
    reponse.raise_for_status()
    return reponse


def lakehouse_cible(nom):
    """Identifiants du Lakehouse nommé et de son point SQL ; erreur s'il est absent ou en double."""
    trouves = [
        lh
        for lh in api_fabric("GET", "lakehouses").json()["value"]
        if lh["displayName"] == nom
    ]
    if len(trouves) != 1:
        raise ValueError(
            f"{len(trouves)} Lakehouse nommé « {nom} » dans l'espace, il en faut un"
        )
    return trouves[0]["id"], trouves[0]["properties"]["sqlEndpointProperties"]["id"]


def synchroniser_point_sql():
    """Le point SQL ne voit pas toujours seul les tables écrites par deltalake : on le resynchronise."""
    try:
        api_fabric("POST", f"sqlEndpoints/{point_sql_id}/refreshMetadata", json={})
        print("Point SQL resynchronisé")
    except Exception as e:
        print(
            f"Point SQL non resynchronisé ({e!r}) : bouton « Actualiser » du point SQL"
        )


def source(url, chemin, verifier):
    """Copie locale d'un fichier source, gardée brute dans Files/ ; verifier(copie) échoue sur un fichier incomplet.

    Le site de l'INSEE coupe parfois un téléchargement sans le signaler et n'accepte pas la
    reprise : chaque copie est vérifiée, et retéléchargée jusqu'à trois fois.
    """
    distant = f"{racine}/Files/{chemin}"
    copie = os.path.join(dossier_local, os.path.basename(chemin))
    if not RETELECHARGER and notebookutils.fs.exists(distant):
        notebookutils.fs.cp(distant, f"file:{copie}")
        verifier(copie)
        return copie
    for essai in range(3):
        try:
            with session.get(
                url, stream=True, timeout=1800, headers={"User-Agent": "Mozilla/5.0"}
            ) as reponse:
                reponse.raise_for_status()
                with open(copie, "wb") as fichier:
                    for bloc in reponse.iter_content(chunk_size=1 << 20):
                        fichier.write(bloc)
            verifier(copie)
            break
        except Exception as e:
            print(
                f"Téléchargement de {os.path.basename(chemin)}, essai {essai + 1} : {e!r}"
            )
            if essai == 2:
                raise
            time.sleep(10)
    notebookutils.fs.cp(f"file:{copie}", distant)
    return copie


def parquet_complet(chemin):
    pq.ParquetFile(chemin)


def lire(table, colonnes=None):
    return DeltaTable(f"{racine}/Tables/dbo/{table}", storage_options=acces).to_pandas(
        columns=colonnes
    )


def ecrire(table, df):
    """Réécrit entièrement une table du Lakehouse : chaque passage repart des sources."""
    write_deltalake(
        f"{racine}/Tables/dbo/{table}",
        df,
        mode="overwrite",
        schema_mode="overwrite",
        storage_options=acces,
    )
    print(f"{table} : {len(df)} lignes écrites")


def anneaux_de(geometrie):
    """Anneaux (tableaux lon, lat) d'un Polygon ou d'un MultiPolygon GeoJSON."""
    polygones = (
        geometrie["coordinates"]
        if geometrie["type"] == "MultiPolygon"
        else [geometrie["coordinates"]]
    )
    return [
        np.asarray(anneau, dtype=float) for polygone in polygones for anneau in polygone
    ]


def boite(anneaux):
    """[lon_min, lat_min, lon_max, lat_max] d'un contour."""
    sommets = np.concatenate(anneaux)
    return [*sommets.min(axis=0), *sommets.max(axis=0)]


def dans_contour(lon, lat, anneaux):
    """Masque des points situés dans le contour : règle pair-impair, calculée par paquets de points."""
    croisements = np.zeros(len(lon), dtype=np.int64)
    for a in anneaux:
        x1, y1, x2, y2 = a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]
        for debut in range(0, len(lon), 2000):
            px, py = lon[debut : debut + 2000, None], lat[debut : debut + 2000, None]
            coupe = (y1 > py) != (y2 > py)
            with np.errstate(divide="ignore", invalid="ignore"):
                x_coupe = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            croisements[debut : debut + 2000] += np.count_nonzero(
                coupe & (px < x_coupe), axis=1
            )
    return croisements % 2 == 1


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

lakehouse_id, point_sql_id = lakehouse_cible(LAKEHOUSE)
racine = f"abfss://{espace}@{endpoint}/{lakehouse_id}"

# La zone et les carreaux, écrits par 01_carreaux.
communes_zone = lire("zone_communes", ["code_commune", "contour_geojson"])
codes_zone = set(communes_zone["code_commune"])
carreaux = lire(
    "carreaux",
    ["idcar_200m", "codes_communes", "lat", "lon", "x_3035", "y_3035", "population"],
)
france = lire(
    "carreaux_france",
    ["idcar_200m", "codes_communes", "epsg", "x", "y", "lat", "lon", "population"],
)
anneaux_zone = [anneaux_de(json.loads(g)) for g in communes_zone["contour_geojson"]]
boites_zone = np.array([boite(anneaux) for anneaux in anneaux_zone])
cases_zone = set(
    zip(
        (carreaux["x_3035"] // 200).astype(int), (carreaux["y_3035"] // 200).astype(int)
    )
)
portee = math.ceil(RAYON_M / 200)


def dans_la_zone(lon, lat):
    """Vrai si le point est dans une commune de la zone."""
    candidates = np.flatnonzero(
        (boites_zone[:, 0] <= lon)
        & (lon <= boites_zone[:, 2])
        & (boites_zone[:, 1] <= lat)
        & (lat <= boites_zone[:, 3])
    )
    return any(
        dans_contour(np.array([lon]), np.array([lat]), anneaux_zone[k])[0]
        for k in candidates
    )


def pres_de_la_zone(x, y):
    """Vrai si le point est à RAYON_M ou moins du centre d'un carreau habité de la zone."""
    i0, j0 = int(x // 200), int(y // 200)
    return any(
        (i, j) in cases_zone
        and math.hypot(i * 200 + 100 - x, j * 200 + 100 - y) <= RAYON_M
        for i in range(i0 - portee, i0 + portee + 1)
        for j in range(j0 - portee, j0 + portee + 1)
    )


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Motorisation par IRIS (recensement 2023, géographie au 1er janvier 2025).
logement = (
    pq.read_table(
        source(
            URL_LOGEMENT,
            "brut/insee/DS_RP_LOGEMENT_PRINC_IRIS_2023.parquet",
            parquet_complet,
        ),
        columns=["GEO", "GEO_OBJECT", "TYP_IRIS", "CARS", "CARPARK", "OBS_VALUE"],
        filters=FILTRES_LOGEMENT,
    )
    .to_pandas()
    .astype({c: str for c in ("GEO", "GEO_OBJECT", "TYP_IRIS", "CARS", "CARPARK")})
)
logement["compte"] = [
    COMPTES.get(cle) for cle in zip(logement["CARS"], logement["CARPARK"])
]
logement = logement[logement["compte"].notna()]
# Une ligne par unité et par compte : pivot échoue sur un doublon.
iris = logement.pivot(
    index=["GEO", "GEO_OBJECT", "TYP_IRIS"], columns="compte", values="OBS_VALUE"
).reset_index()
iris.columns.name = None
# Code IRIS sur 9 caractères ; une commune non découpée reçoit son code suivi de 0000.
iris["code_iris"] = np.where(
    iris["GEO_OBJECT"] == "IRIS", iris["GEO"], iris["GEO"] + "0000"
)
iris["code_commune"] = iris["GEO"].str[:5]
NOMS_COMPTES = list(COMPTES.values())
iris = iris.rename(columns={"TYP_IRIS": "type_iris"})[
    ["code_iris", "code_commune", "type_iris", *NOMS_COMPTES]
]
assert iris["code_iris"].is_unique and iris[NOMS_COMPTES].notna().all().all()
comptes_iris = iris.set_index("code_iris")[NOMS_COMPTES]
comptes_commune = iris.groupby("code_commune")[NOMS_COMPTES].sum()
communes_decoupees = set(iris.loc[iris["type_iris"] != "Z", "code_commune"])
print(
    f"Recensement : {len(iris)} IRIS, dont {(iris['type_iris'] != 'Z').sum()} dans "
    f"{len(communes_decoupees)} communes découpées"
)


def motorisation(comptes):
    """Indicateurs de motorisation à partir des comptes de ménages.

    voitures_par_menage compte 2 voitures pour « 2 voitures ou plus » : c'est un minimum.
    """
    menages = comptes["menages"].where(comptes["menages"] > 0)
    return pd.DataFrame(
        {
            "part_menages_sans_voiture": (
                1 - comptes["menages_avec_voiture"] / menages
            ).round(4),
            "voitures_par_menage": (
                (comptes["menages_1_voiture"] + 2 * comptes["menages_2_voitures_plus"])
                / menages
            ).round(3),
            "part_menages_2_voitures_plus": (
                comptes["menages_2_voitures_plus"] / menages
            ).round(4),
            "part_menages_avec_stationnement": (
                comptes["menages_avec_stationnement"] / menages
            ).round(4),
        },
        index=comptes.index,
    )


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def contours_iris_decoupes():
    """Contours IGN des IRIS des communes découpées, gardés dans Files/brut/ign/ (les autres IRIS sont leur commune)."""
    distant = f"{racine}/Files/brut/ign/contours_iris_decoupes.geojson"
    copie = os.path.join(dossier_local, "contours_iris_decoupes.geojson")
    if not RETELECHARGER and notebookutils.fs.exists(distant):
        notebookutils.fs.cp(distant, f"file:{copie}")
    else:
        elements, debut = [], 0
        while True:
            page = session.get(
                WFS_IGN,
                timeout=900,
                params={
                    "SERVICE": "WFS",
                    "VERSION": "2.0.0",
                    "REQUEST": "GetFeature",
                    "TYPENAMES": COUCHE_IRIS,
                    "OUTPUTFORMAT": "application/json",
                    "CQL_FILTER": "type_iris<>'Z'",
                    "SORTBY": "code_iris",
                    "COUNT": 2000,
                    "STARTINDEX": debut,
                },
            ).json()["features"]
            elements += page
            if len(page) < 2000:
                break
            debut += 2000
        with open(copie, "w", encoding="utf-8") as fichier:
            json.dump({"type": "FeatureCollection", "features": elements}, fichier)
        notebookutils.fs.cp(f"file:{copie}", distant)
    with open(copie, encoding="utf-8") as fichier:
        return json.load(fichier)["features"]


contours = [c for c in contours_iris_decoupes() if c.get("geometry")]
iris_par_commune, noms_iris, contours_geojson = {}, {}, {}
for c in contours:
    p = c["properties"]
    anneaux = anneaux_de(c["geometry"])
    iris_par_commune.setdefault(p["code_insee"], []).append(
        (p["code_iris"], anneaux, boite(anneaux))
    )
    noms_iris[p["code_iris"]] = p["nom_iris"]
    if p["code_insee"] in codes_zone:
        contours_geojson[p["code_iris"]] = json.dumps(c["geometry"])
print(
    f"IGN : {len(contours)} contours d'IRIS dans {len(iris_par_commune)} communes découpées"
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def rattacher(carreaux):
    """IRIS de chaque carreau, niveau du rattachement et motorisation qui s'y applique."""
    n = len(carreaux)
    lon, lat = carreaux["lon"].to_numpy(), carreaux["lat"].to_numpy()
    listes = carreaux["codes_communes"].str.split(",").to_numpy()
    code_iris = np.full(n, None, dtype=object)

    # 1. Le centre du carreau dans un IRIS d'une commune découpée qu'il touche.
    eclate = pd.Series(listes).explode()
    a_tester = eclate[eclate.isin(iris_par_commune.keys())]
    for commune, positions in a_tester.groupby(a_tester).groups.items():
        positions = np.asarray(positions)
        for code, anneaux, (x0, y0, x1, y1) in iris_par_commune[commune]:
            m = (
                (x0 <= lon[positions])
                & (lon[positions] <= x1)
                & (y0 <= lat[positions])
                & (lat[positions] <= y1)
            )
            if m.any():
                cibles = positions[m]
                code_iris[cibles[dans_contour(lon[cibles], lat[cibles], anneaux)]] = (
                    code
                )
    # Un IRIS de l'IGN absent du recensement (géographie plus récente) : on passe à la commune.
    inconnus = (
        pd.notna(code_iris) & ~pd.Series(code_iris).isin(comptes_iris.index).to_numpy()
    )
    code_iris[inconnus] = None

    # 2. Sinon, la commune non découpée qu'il touche, ou l'ensemble des communes touchées.
    rattachement = np.where(pd.notna(code_iris), "iris", "").astype(object)
    groupe = code_iris.copy()
    connues = set(comptes_commune.index)
    for i in np.flatnonzero(pd.isna(code_iris)):
        communes = [c for c in listes[i] if c in connues]
        simples = [c for c in communes if c not in communes_decoupees]
        base = simples or communes
        if not base:
            rattachement[i] = "aucun"
        elif len(base) == 1 and base[0] not in communes_decoupees:
            code_iris[i] = groupe[i] = base[0] + "0000"
            rattachement[i] = "commune"
        else:
            groupe[i] = "+".join(sorted(base))
            rattachement[i] = "communes"

    # 3. Les comptes du groupe : un IRIS, ou la somme des communes touchées.
    uniques = pd.unique(groupe[pd.notna(groupe)])
    des_iris = [g for g in uniques if g in comptes_iris.index]
    des_communes = [g for g in uniques if g not in comptes_iris.index]
    comptes = pd.concat(
        [
            comptes_iris.loc[des_iris],
            pd.DataFrame(
                [comptes_commune.loc[g.split("+")].sum() for g in des_communes],
                index=des_communes,
                columns=NOMS_COMPTES,
            ),
        ]
    )
    resultat = motorisation(comptes).reindex(groupe).reset_index(drop=True)
    resultat.insert(0, "idcar_200m", carreaux["idcar_200m"].to_numpy())
    resultat.insert(1, "code_iris", code_iris)
    resultat.insert(2, "rattachement", rattachement)
    print(
        f"Rattachement : {pd.Series(rattachement).value_counts().to_dict()}, "
        f"{int(inconnus.sum())} IRIS de l'IGN absents du recensement"
    )
    return resultat


variables_zone = rattacher(carreaux)
variables_france = rattacher(france)

# La table des IRIS : toute la France, contour pour ceux de la zone (IGN pour les IRIS des
# communes découpées, contour de la commune pour les autres).
contours_communes = dict(
    zip(communes_zone["code_commune"], communes_zone["contour_geojson"])
)
iris = pd.concat(
    [
        iris.reset_index(drop=True),
        motorisation(iris[NOMS_COMPTES]).reset_index(drop=True),
    ],
    axis=1,
)
iris["nom_iris"] = iris["code_iris"].map(noms_iris)
iris["dans_zone"] = iris["code_commune"].isin(codes_zone)
iris["contour_geojson"] = iris["code_iris"].map(contours_geojson)
simples = iris["dans_zone"] & (iris["type_iris"] == "Z")
iris.loc[simples, "contour_geojson"] = iris.loc[simples, "code_commune"].map(
    contours_communes
)
ecrire("iris", iris)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Équipements de la BPE 2025 bien géolocalisés, rangés par famille et par pôle.
bpe_fichier = source(URL_BPE, "brut/insee/BPE25.parquet", parquet_complet)
bpe = pd.read_parquet(
    bpe_fichier,
    columns=[
        "TYPEQU",
        "SDOM",
        "NOMRS",
        "DEPCOM",
        "DEP",
        "QUALITE_XY",
        "LONGITUDE",
        "LATITUDE",
    ],
)
# Qualité de géolocalisation : B bonne, A acceptable, _U coordonnées fournies par le
# producteur (équipements sportifs surtout). M (mauvaise, souvent le centre de la commune)
# et les équipements sans coordonnées sont écartés.
bpe = bpe[
    bpe["QUALITE_XY"].isin(["B", "A", "_U"])
    & bpe["LONGITUDE"].notna()
    & bpe["LATITUDE"].notna()
]
bpe = bpe.rename(
    columns={
        "QUALITE_XY": "qualite_xy",
        "TYPEQU": "type_equipement",
        "SDOM": "sous_domaine",
        "NOMRS": "nom",
        "DEPCOM": "code_commune",
        "DEP": "departement",
        "LONGITUDE": "lon",
        "LATITUDE": "lat",
    }
)
bpe["famille"] = (
    bpe["type_equipement"].map(FAMILLES_TYPES).fillna(bpe["sous_domaine"].map(FAMILLES))
)
bpe["pole"] = bpe["type_equipement"].map(POLES)
bpe = bpe[bpe["famille"].notna() | bpe["pole"].notna()].reset_index(drop=True)
print(f"BPE : {len(bpe)} équipements retenus")
print(bpe.groupby("famille").size().to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Emplois salariés : les établissements actifs qui ont une tranche d'effectif, joints à leur
# géolocalisation. Les deux fichiers ne sont lus que pour les colonnes utiles.
stock = ds.dataset(
    source(
        URL_SIRENE_STOCK,
        "brut/insee/sirene_stock_etablissements.parquet",
        parquet_complet,
    ),
    format="parquet",
).to_table(
    columns=["siret", "trancheEffectifsEtablissement"],
    filter=(ds.field("etatAdministratifEtablissement") == "A")
    & ds.field("trancheEffectifsEtablissement").isin(list(EFFECTIF_TRANCHE)),
)
geolocalisation = ds.dataset(
    source(
        URL_SIRENE_GEOLOC,
        "brut/insee/sirene_geolocalisation_etablissements.parquet",
        parquet_complet,
    ),
    format="parquet",
).to_table(
    columns=["siret", "plg_code_commune", "x_longitude", "y_latitude"],
    filter=ds.field("siret").isin(pc.unique(stock["siret"]))
    & (ds.field("qualite_xy") != "33"),
)
etablissements = (
    geolocalisation.join(stock, keys="siret", join_type="inner")
    .to_pandas()
    .rename(
        columns={
            "plg_code_commune": "code_commune",
            "x_longitude": "lon",
            "y_latitude": "lat",
        }
    )
)
etablissements["emplois"] = etablissements["trancheEffectifsEtablissement"].map(
    EFFECTIF_TRANCHE
)
# Les trois premiers caractères du code commune suffisent à trier les territoires (972 et
# 974 pour la Martinique et La Réunion, les autres DROM n'ont pas de carreaux INSEE).
etablissements["departement"] = etablissements["code_commune"].str[:3]
print(
    f"Sirene : {len(etablissements)} établissements employeurs placés, "
    f"{etablissements['emplois'].sum():,.0f} emplois (sur {len(stock)} actifs avec une tranche)"
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Projection des équipements dans la grille de chaque territoire des carreaux INSEE.
PROJECTIONS = {
    3035: lambda dep: ~dep.str.startswith("97"),
    5490: lambda dep: dep == "972",
    2975: lambda dep: dep == "974",
}
NOMS_FAMILLES = sorted(set(FAMILLES.values()))
NOMS_POLES = sorted(set(POLES.values()))


def compter(centres, epsg):
    """Équipements par famille dans chaque carreau et à moins de RAYON_M de son centre, pour un territoire."""
    points = bpe[PROJECTIONS[epsg](bpe["departement"])]
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(
        points["lon"].to_numpy(), points["lat"].to_numpy()
    )
    case = pd.Series(
        [
            f"CRS{epsg}RES200mN{int(b // 200) * 200}E{int(a // 200) * 200}"
            for a, b in zip(x, y)
        ],
        index=points.index,
    )
    resultat = pd.DataFrame({"idcar_200m": centres["idcar_200m"].to_numpy()})
    xy_centres = centres[["x", "y"]].to_numpy()
    for nom, colonne in [(f, "famille") for f in NOMS_FAMILLES] + [
        (p, "pole") for p in NOMS_POLES
    ]:
        choisis = (points[colonne] == nom).to_numpy()
        if colonne == "famille":
            dans_carreau = case[choisis].value_counts()
            resultat[f"{nom}_carreau"] = (
                resultat["idcar_200m"].map(dans_carreau).fillna(0).astype("int64")
            )
        arbre = (
            cKDTree(np.column_stack([x[choisis], y[choisis]]))
            if choisis.any()
            else None
        )
        resultat[f"{nom}_5min"] = (
            arbre.query_ball_point(xy_centres, r=RAYON_M, return_length=True)
            if arbre is not None
            else 0
        )
        resultat[f"{nom}_5min"] = resultat[f"{nom}_5min"].astype("int64")
    return resultat


def compter_emplois(centres, epsg):
    """Emplois dans chaque carreau et à moins de RAYON_M de son centre, pour un territoire.

    Les centres sont traités par paquets : à Paris, un rayon de 400 m touche des milliers
    d'établissements.
    """
    points = etablissements[PROJECTIONS[epsg](etablissements["departement"])]
    resultat = pd.DataFrame({"idcar_200m": centres["idcar_200m"].to_numpy()})
    if points.empty:
        resultat["emplois_carreau"] = resultat["emplois_5min"] = 0
        return resultat
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(
        points["lon"].to_numpy(), points["lat"].to_numpy()
    )
    emplois = points["emplois"].to_numpy()
    case = [
        f"CRS{epsg}RES200mN{int(b // 200) * 200}E{int(a // 200) * 200}"
        for a, b in zip(x, y)
    ]
    resultat["emplois_carreau"] = (
        resultat["idcar_200m"]
        .map(pd.Series(emplois).groupby(case).sum())
        .fillna(0)
        .round()
        .astype("int64")
    )
    arbre = cKDTree(np.column_stack([x, y]))
    xy_centres = centres[["x", "y"]].to_numpy()
    total = np.zeros(len(xy_centres))
    for debut in range(0, len(xy_centres), 100_000):
        voisins = arbre.query_ball_point(xy_centres[debut : debut + 100_000], r=RAYON_M)
        total[debut : debut + 100_000] = [emplois[v].sum() for v in voisins]
    resultat["emplois_5min"] = total.round().astype("int64")
    return resultat


equipements_zone = compter(
    carreaux.rename(columns={"x_3035": "x", "y_3035": "y"}), 3035
).merge(
    compter_emplois(carreaux.rename(columns={"x_3035": "x", "y_3035": "y"}), 3035),
    on="idcar_200m",
    validate="one_to_one",
)
equipements_france = pd.concat(
    [
        compter(groupe, epsg).merge(
            compter_emplois(groupe, epsg), on="idcar_200m", validate="one_to_one"
        )
        for epsg, groupe in france.groupby("epsg")
    ],
    ignore_index=True,
)
print(
    f"Emplois à 5 minutes, zone : médiane {equipements_zone['emplois_5min'].median():.0f} par carreau"
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Les équipements de la zone et à moins de RAYON_M, pour les cartes.
vers_metres = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
x0, y0, x1, y1 = (
    boites_zone[:, 0].min(),
    boites_zone[:, 1].min(),
    boites_zone[:, 2].max(),
    boites_zone[:, 3].max(),
)
marge = 0.01  # environ 1 km : le rayon de 400 m déborde de la zone
proches = bpe[
    bpe["lon"].between(x0 - marge, x1 + marge)
    & bpe["lat"].between(y0 - marge, y1 + marge)
].copy()
proches["x_3035"], proches["y_3035"] = vers_metres.transform(
    proches["lon"].to_numpy(), proches["lat"].to_numpy()
)
proches[["x_3035", "y_3035"]] = proches[["x_3035", "y_3035"]].round(1)
proches["idcar_200m"] = [
    f"CRS3035RES200mN{int(b // 200) * 200}E{int(a // 200) * 200}"
    for a, b in zip(proches["x_3035"], proches["y_3035"])
]
proches["dans_zone"] = [
    dans_la_zone(lon, lat) for lon, lat in zip(proches["lon"], proches["lat"])
]
pres = np.array(
    [pres_de_la_zone(x, y) for x, y in zip(proches["x_3035"], proches["y_3035"])],
    dtype=bool,
)
equipements = (
    proches[proches["dans_zone"].to_numpy() | pres]
    .drop(columns=["departement"])
    .reset_index(drop=True)
)
ecrire("equipements", equipements)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

carreaux_variables = variables_zone.merge(
    equipements_zone, on="idcar_200m", validate="one_to_one"
)
carreaux_france_variables = variables_france.merge(
    equipements_france, on="idcar_200m", validate="one_to_one"
)

# Contrôles : une ligne par carreau, et la part d'habitants sans motorisation reste faible.
assert (
    len(carreaux_variables) == len(carreaux)
    and carreaux_variables["idcar_200m"].is_unique
)
assert (
    len(carreaux_france_variables) == len(france)
    and carreaux_france_variables["idcar_200m"].is_unique
)
for nom, variables, base in (
    ("zone", carreaux_variables, carreaux),
    ("France", carreaux_france_variables, france),
):
    habitants = base.set_index("idcar_200m")["population"]
    part = (
        variables.groupby("rattachement")["idcar_200m"].apply(
            lambda ids: habitants.loc[ids].sum()
        )
        / habitants.sum()
    )
    print(f"{nom} : habitants par rattachement {part.round(4).to_dict()}")
    assert part.get("aucun", 0) < 0.01, f"{nom} : trop d'habitants sans motorisation"
ecrire("carreaux_variables", carreaux_variables)
ecrire("carreaux_france_variables", carreaux_france_variables)
synchroniser_point_sql()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
