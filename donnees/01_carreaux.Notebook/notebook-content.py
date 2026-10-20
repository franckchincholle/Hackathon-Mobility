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

# # Carreaux INSEE de 200 m
# 
# Charge les carreaux de 200 m de l'INSEE (Filosofi 2021 : population, ménages, revenus,
# âges, logements) et construit trois tables :
# 
# - `zone_communes` : les communes de la zone d'étude, leur intercommunalité, leur
#   département, leur région et leur contour (geo.api.gouv.fr). Les notebooks 02 et 03 la
#   relisent pour savoir ce qui est dans la zone et quels réseaux la desservent.
# - `carreaux` : une ligne par carreau habité de la zone d'étude, avec son centre (lat/lon
#   pour les cartes, x/y en mètres pour les distances), son contour en WKT et ses variables.
#   C'est la table de référence des cartes et du modèle.
# - `carreaux_france` : les mêmes variables pour toute la France publiée par l'INSEE
#   (métropole, Martinique, La Réunion), sans contour, pour entraîner le modèle sur toutes
#   les villes où Citiz est présent.
# 
# Les réglages sont dans la bibliothèque de variables `parametres_mobilite` de l'espace :
# son jeu de valeurs actif choisit la zone et le Lakehouse où écrire (Toulouse Métropole
# dans `Mobilite` par défaut, l'Occitanie dans `MobiliteOccitanie` avec le jeu
# « occitanie »).
# 
# L'identifiant INSEE porte le coin sud-ouest du carreau dans sa projection
# (`CRS3035RES200mN2316600E3630000`) : le centre est 100 m plus au nord et plus à l'est.
# Les carreaux trop peu peuplés ont des valeurs estimées par l'INSEE (secret statistique) :
# la colonne `valeurs_imputees` les repère.

# CELL ********************

import json
import os
import tempfile
import zipfile

import notebookutils
import pandas as pd
import requests
from deltalake import write_deltalake
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from pyproj import Transformer
except ImportError:  # absent de certaines images Python de Fabric
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyproj"], check=True)
    from pyproj import Transformer

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Réglages partagés par les notebooks 01 à 03 : bibliothèque de variables de l'espace.
parametres = notebookutils.variableLibrary.getLibrary("parametres_mobilite")
ZONE = parametres.zone
LAKEHOUSE = parametres.lakehouse
RETELECHARGER = str(parametres.retelecharger_insee).lower() == "true"
URL_INSEE = "https://www.insee.fr/fr/statistiques/fichier/8735162/Filosofi2021_carreaux_200m_csv.zip"
print(f"Zone {ZONE}, tables écrites dans le Lakehouse {LAKEHOUSE}")

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


def source(url, chemin):
    """Copie locale d'un fichier source, gardé brut dans Files/ pour pouvoir rejouer."""
    distant = f"{racine}/Files/{chemin}"
    copie = os.path.join(dossier_local, os.path.basename(chemin))
    if RETELECHARGER or not notebookutils.fs.exists(distant):
        with session.get(
            url, stream=True, timeout=900, headers={"User-Agent": "Mozilla/5.0"}
        ) as reponse:
            reponse.raise_for_status()
            with open(copie, "wb") as fichier:
                for bloc in reponse.iter_content(chunk_size=1 << 20):
                    fichier.write(bloc)
        notebookutils.fs.cp(f"file:{copie}", distant)
    else:
        notebookutils.fs.cp(distant, f"file:{copie}")
    return copie


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


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

lakehouse_id, point_sql_id = lakehouse_cible(LAKEHOUSE)
racine = f"abfss://{espace}@{endpoint}/{lakehouse_id}"

# Les communes de la zone et leur contour. ZONE est une requête de geo.api.gouv.fr :
# "epcis/<code>/communes", "departements/<code>/communes" ou "communes?codeRegion=<code>".
separateur = "&" if "?" in ZONE else "?"
champs = "fields=code,nom,codeEpci,codeDepartement,codeRegion&format=geojson&geometry=contour"
communes = session.get(
    f"https://geo.api.gouv.fr/{ZONE}{separateur}{champs}", timeout=600
).json()["features"]
zone_communes = pd.DataFrame(
    {
        "code_commune": [c["properties"]["code"] for c in communes],
        "nom": [c["properties"]["nom"] for c in communes],
        "code_epci": [c["properties"].get("codeEpci") for c in communes],
        "code_departement": [c["properties"].get("codeDepartement") for c in communes],
        "code_region": [c["properties"].get("codeRegion") for c in communes],
        "contour_geojson": [json.dumps(c["geometry"]) for c in communes],
    }
)
if zone_communes.empty:
    raise ValueError(f"geo.api.gouv.fr ne renvoie aucune commune pour la zone {ZONE}")
codes_zone = set(zone_communes["code_commune"])
print(f"Zone {ZONE} : {len(codes_zone)} communes")
ecrire("zone_communes", zone_communes)

zip_insee = source(URL_INSEE, "brut/insee/Filosofi2021_carreaux_200m_csv.zip")
TERRITOIRES = {
    "carreaux_200m_met.csv": "metropole",
    "carreaux_200m_mart.csv": "martinique",
    "carreaux_200m_reun.csv": "reunion",
}
morceaux = []
with zipfile.ZipFile(zip_insee) as archive:
    for nom, territoire in TERRITOIRES.items():
        with archive.open(nom) as fichier:
            morceau = pd.read_csv(
                fichier,
                dtype={
                    "idcar_200m": str,
                    "idcar_1km": str,
                    "idcar_nat": str,
                    "lcog_geo": str,
                },
            )
        morceau["territoire"] = territoire
        morceaux.append(morceau)
insee = pd.concat(morceaux, ignore_index=True)
assert insee["idcar_200m"].is_unique, (
    "identifiant de carreau en double dans le fichier INSEE"
)
print(f"{len(insee)} carreaux habités en France, {insee['ind'].sum():,.0f} habitants")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Noms explicites pour toute l'équipe ; le dictionnaire de l'INSEE est sur la page
# https://www.insee.fr/fr/statistiques/8735162
RENOMMAGE = {
    "lcog_geo": "codes_communes",
    "i_est_200": "valeurs_imputees",
    "i_est_1km": "valeurs_imputees_1km",
    "ind": "population",
    "men": "menages",
    "men_pauv": "menages_pauvres",
    "men_1ind": "menages_1_personne",
    "men_5ind": "menages_5_personnes_plus",
    "men_prop": "menages_proprietaires",
    "men_fmp": "menages_monoparentaux",
    "ind_snv": "somme_niveaux_vie",
    "men_surf": "surface_logements_m2",
    "men_coll": "menages_logement_collectif",
    "men_mais": "menages_maison",
    "log_av45": "logements_avant_1945",
    "log_45_70": "logements_1945_1970",
    "log_70_90": "logements_1970_1990",
    "log_ap90": "logements_apres_1990",
    "log_inc": "logements_date_inconnue",
    "log_soc": "logements_sociaux",
    "ind_0_3": "age_0_3",
    "ind_4_5": "age_4_5",
    "ind_6_10": "age_6_10",
    "ind_11_17": "age_11_17",
    "ind_18_24": "age_18_24",
    "ind_25_39": "age_25_39",
    "ind_40_54": "age_40_54",
    "ind_55_64": "age_55_64",
    "ind_65_79": "age_65_79",
    "ind_80p": "age_80_plus",
    "ind_inc": "age_inconnu",
}
insee = insee.rename(columns=RENOMMAGE).drop(columns=["idcar_nat"])
insee["valeurs_imputees"] = insee["valeurs_imputees"] == 1
insee["valeurs_imputees_1km"] = insee["valeurs_imputees_1km"] == 1
habite = insee["population"] > 0
insee["niveau_vie_moyen"] = (
    (insee["somme_niveaux_vie"] / insee["population"]).where(habite).round(0)
)
insee["part_menages_pauvres"] = (
    (insee["menages_pauvres"] / insee["menages"]).where(insee["menages"] > 0).round(4)
)

# Centre du carreau dans sa projection (mètres), puis en lat/lon (WGS84).
parties = (
    insee["idcar_200m"]
    .str.extract(r"CRS(?P<epsg>\d+)RES(?P<cote>\d+)mN(?P<nord>\d+)E(?P<est>\d+)")
    .astype(int)
)
insee["epsg"] = parties["epsg"]
insee["x"] = parties["est"] + parties["cote"] / 2
insee["y"] = parties["nord"] + parties["cote"] / 2
for epsg, groupe in insee.groupby("epsg"):
    lon, lat = Transformer.from_crs(
        f"EPSG:{epsg}", "EPSG:4326", always_xy=True
    ).transform(groupe["x"].to_numpy(), groupe["y"].to_numpy())
    insee.loc[groupe.index, "lon"] = lon
    insee.loc[groupe.index, "lat"] = lat
insee[["lon", "lat"]] = insee[["lon", "lat"]].round(6)

TETE = [
    "idcar_200m",
    "idcar_1km",
    "territoire",
    "codes_communes",
    "epsg",
    "x",
    "y",
    "lat",
    "lon",
    "population",
    "menages",
    "niveau_vie_moyen",
    "part_menages_pauvres",
    "valeurs_imputees",
]
insee = insee[TETE + [c for c in insee.columns if c not in TETE]]
ecrire("carreaux_france", insee)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Un carreau est dans la zone s'il touche au moins une de ses communes ; ceux qui touchent
# aussi une commune hors zone sont repérés par a_cheval_limite.
listes = insee["codes_communes"].str.split(",")
dans_zone = listes.map(lambda codes: any(c in codes_zone for c in codes))
carreaux = insee[dans_zone].drop(columns=["territoire", "epsg"]).copy()
carreaux.insert(
    3,
    "a_cheval_limite",
    listes[dans_zone].map(lambda codes: not all(c in codes_zone for c in codes)),
)
assert (insee.loc[dans_zone, "epsg"] == 3035).all(), (
    "la zone doit être en France métropolitaine"
)
carreaux = carreaux.rename(columns={"x": "x_3035", "y": "y_3035"})

# Contour du carreau en WKT (lon lat), pour les cartes.
vers_gps = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
coins = [(-100, -100), (100, -100), (100, 100), (-100, 100), (-100, -100)]
sommets = [
    vers_gps.transform(
        carreaux["x_3035"].to_numpy() + dx, carreaux["y_3035"].to_numpy() + dy
    )
    for dx, dy in coins
]
carreaux["contour_wkt"] = [
    "POLYGON((" + ", ".join(f"{lon[i]:.6f} {lat[i]:.6f}" for lon, lat in sommets) + "))"
    for i in range(len(carreaux))
]
ecrire("carreaux", carreaux.reset_index(drop=True))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Contrôles : ils arrêtent le notebook si la table n'a pas la forme attendue.
assert carreaux["idcar_200m"].is_unique
assert carreaux["population"].gt(0).all()
assert carreaux["lat"].between(41, 52).all() and carreaux["lon"].between(-6, 10).all()
imputes = carreaux["valeurs_imputees"]
print(
    f"Zone : {len(carreaux)} carreaux, {carreaux['population'].sum():,.0f} habitants, "
    f"{carreaux['menages'].sum():,.0f} ménages, niveau de vie moyen "
    f"{carreaux['somme_niveaux_vie'].sum() / carreaux['population'].sum():,.0f} euros"
)
print(f"Carreaux à cheval sur la limite : {int(carreaux['a_cheval_limite'].sum())}")
print(
    f"Valeurs estimées par l'INSEE : {int(imputes.sum())} carreaux, "
    f"{carreaux.loc[imputes, 'population'].sum() / carreaux['population'].sum():.1%} de la population"
)
synchroniser_point_sql()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
