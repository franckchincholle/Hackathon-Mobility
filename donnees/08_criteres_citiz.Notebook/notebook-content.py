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

# # Les 8 critères de Citiz, mesurés sur chaque carreau
#
# Citiz décrit « l'emplacement idéal » d'une station par 8 critères : transports
# collectifs, densité urbaine, mixité habitat/activité, accessibilité/circulation, simple
# pour stationner, taux de motorisation faible, visible, arbres à distance (une voiture ne
# stationne pas sous un arbre : branches, sève, chutes). Ce notebook les mesure sur chacun
# des carreaux habités de 200 m de la zone, et propose dans chaque carreau une place précise,
# loin des arbres. Cinq tables :
#
# - `arbres` : un arbre par ligne. L'inventaire des arbres urbains de Toulouse Métropole
#   (open data, jeu « arbres-urbains »), complété par les arbres d'OpenStreetMap
#   (natural=tree) qu'il ne contient pas déjà (aucun arbre de l'inventaire à moins de
#   `DOUBLON_ARBRE_M`).
# - `parkings_osm` : les parkings d'OpenStreetMap (amenity=parking : points, contours et
#   multipolygones), avec leur surface, leur capacité quand elle est renseignée et leur accès.
# - `routes_osm` : les tronçons des routes principales d'OpenStreetMap (primary, secondary,
#   tertiary et leurs bretelles ; pas d'autoroute, on ne s'y gare pas).
# - `criteres_citiz` : une ligne par carreau, clé `idcar_200m` : la valeur brute de chaque
#   critère dans son unité, sa note de 0 à 100 (rang centile dans la zone, 100 = le
#   meilleur) et l'indice Citiz, moyenne des 8 notes.
# - `places_candidates` : dans chaque carreau, le point d'un parking public OSM le plus
#   éloigné des arbres, s'il l'est d'au moins `DISTANCE_ARBRE_MIN_M`, avec son adresse
#   (géocodage inverse de la Base adresse nationale, service de l'IGN).
#
# Les inventaires d'arbres ne couvrent pas toute la zone. Une commune compte comme mesurée
# si l'inventaire de Toulouse Métropole y recense au moins `ARBRES_INVENTAIRE_MIN` arbres
# (Toulouse, Tournefeuille, Cornebarrieu, Beauzelle), ou si OpenStreetMap y compte au
# moins `ARBRES_PAR_CARREAU_MIN` arbres par carreau habité, le niveau d'une commune
# inventoriée en entier (Cornebarrieu : 6,5). Ailleurs, le critère « arbres à distance »
# prend la note neutre de 50 (`arbres_mesures` faux) et la place proposée est le plus grand
# parking public du carreau, sans distance aux arbres.
#
# Les réglages viennent de la bibliothèque de variables `parametres_mobilite` ; 01_carreaux,
# 02_arrets, 03_stations et 05_variables_carreaux doivent avoir tourné avant.

# CELL ********************

import datetime as dt
import io
import json
import os
import tempfile
import time

import notebookutils
import numpy as np
import pandas as pd
import requests
from deltalake import DeltaTable, write_deltalake
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import shapely
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    from scipy.stats import rankdata
    from shapely.geometry import LineString, Point, Polygon, shape
    from shapely.ops import polygonize, unary_union
except ImportError:  # absents de certaines images Python de Fabric
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "pyproj", "scipy", "shapely"],
        check=True,
    )
    import shapely
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    from scipy.stats import rankdata
    from shapely.geometry import LineString, Point, Polygon, shape
    from shapely.ops import polygonize, unary_union

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Réglages partagés par les notebooks : bibliothèque de variables de l'espace.
parametres = notebookutils.variableLibrary.getLibrary("parametres_mobilite")
LAKEHOUSE = parametres.lakehouse
RAYON_M = int(parametres.rayon_m)  # les 5 minutes à pied (décision 4)
RETELECHARGER = str(parametres.retelecharger_insee).lower() == "true"
# Inventaire des arbres urbains de Toulouse Métropole (open data), export complet.
URL_ARBRES = (
    "https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/"
    "arbres-urbains/exports/parquet"
)
URL_OVERPASS = "https://overpass-api.de/api/interpreter"
# Géocodage inverse de la Base adresse nationale, par fichier CSV (service de l'IGN).
URL_BAN_INVERSE = "https://data.geopf.fr/geocodage/reverse/csv"
# Overpass refuse (406) une requête sans agent explicite.
AGENT = {"User-Agent": "hackathon-mobility-epitech/1.0 (criteres Citiz)"}
MARGE_DEG = 0.01  # environ 1 km autour de la zone : les rayons débordent des communes
ROUTES = ("primary", "secondary", "tertiary")  # accessibilité : toute route principale
AXES = ("primary", "secondary")  # visibilité : les axes passants
# Un parking sert à Citiz s'il est ouvert au public ; ceux-là sont réservés.
ACCES_RESERVES = {"private", "no", "residents", "permit", "restricted", "delivery"}
RAYON_PARKING_M = 200  # « simple pour stationner » : parkings à moins de 200 m du centre
RAYON_VISIBLE_M = 200  # « visible » : commerces et équipements à moins de 200 m
DISTANCE_ARBRE_MIN_M = 10  # une place sous un arbre ou à moins de 10 m ne compte pas
DOUBLON_ARBRE_M = 3  # un arbre OSM à moins de 3 m d'un arbre de l'inventaire est le même
ARBRES_INVENTAIRE_MIN = 500
ARBRES_PAR_CARREAU_MIN = 5
PAS_PLACE_M = 5  # pas de la grille de points essayés dans chaque parking
PAS_DEGAGEMENT_M = 10  # pas de la grille qui mesure la part dégagée de chaque carreau
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
# Quatre essais espacés de 2, 4 puis 8 s : Overpass répond parfois 429 ou 504 quand il est chargé.
session = requests.Session()
session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=4,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=None,
        )
    ),
)
vers_metres = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
vers_degres = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)


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


def brut(chemin, telecharger):
    """Copie locale d'un fichier source, gardée brute dans Files/brut/ ; reprise telle quelle
    tant que `retelecharger_insee` est faux. telecharger(copie) écrit le fichier."""
    distant = f"{racine}/Files/brut/{chemin}"
    copie = os.path.join(dossier_local, os.path.basename(chemin))
    if not RETELECHARGER and notebookutils.fs.exists(distant):
        notebookutils.fs.cp(distant, f"file:{copie}")
        return copie
    telecharger(copie)
    notebookutils.fs.cp(f"file:{copie}", distant)
    return copie


def overpass(nom, requete):
    """Réponse JSON brute d'Overpass, gardée dans Files/brut/osm/<nom>.json."""

    def telecharger(copie):
        reponse = session.post(
            URL_OVERPASS, data={"data": requete}, headers=AGENT, timeout=600
        )
        reponse.raise_for_status()
        donnees = reponse.json()  # échoue sur une réponse coupée
        if "remark" in donnees:  # Overpass signale ainsi un délai dépassé
            raise RuntimeError(f"Overpass {nom} : {donnees['remark']}")
        with open(copie, "wb") as fichier:
            fichier.write(reponse.content)

    with open(brut(f"osm/{nom}.json", telecharger), encoding="utf-8") as fichier:
        return json.load(fichier)


def lire(table, colonnes=None):
    return DeltaTable(f"{racine}/Tables/dbo/{table}", storage_options=acces).to_pandas(
        columns=colonnes
    )


def ecrire(table, df):
    """Réécrit entièrement une table du Lakehouse : chaque passage repart des sources.
    Les horodatages partent en microsecondes UTC, que le point SQL sait lire."""
    df = df.copy()
    for colonne in df.columns[[isinstance(t, pd.DatetimeTZDtype) for t in df.dtypes]]:
        df[colonne] = df[colonne].dt.tz_convert("UTC").astype("datetime64[us, UTC]")
    write_deltalake(
        f"{racine}/Tables/dbo/{table}",
        df,
        mode="overwrite",
        schema_mode="overwrite",
        storage_options=acces,
    )
    print(f"{table} : {len(df)} lignes écrites")


def entier(texte):
    """Nombre entier d'une étiquette OSM (« 120 »), ou None si elle est absente ou libre."""
    try:
        return int(float(str(texte).strip()))
    except (ValueError, OverflowError):
        return None


def en_metres(geometrie):
    """Géométrie lon/lat projetée en EPSG:3035 (mètres), comme les carreaux."""
    return shapely.transform(
        geometrie, lambda xy: np.column_stack(vers_metres.transform(xy[:, 0], xy[:, 1]))
    )


def idcar(x, y):
    """Identifiant INSEE du carreau de 200 m qui contient le point (EPSG:3035)."""
    return [
        f"CRS3035RES200mN{int(b // 200) * 200}E{int(a // 200) * 200}"
        for a, b in zip(x, y)
    ]


def note(valeurs, croissant=True, masque=None):
    """Rang centile de 0 à 100 dans la zone (100 = le meilleur) ; 50, la note neutre, pour une
    valeur absente ou hors de `masque` (critère non mesuré là)."""
    serie = pd.Series(valeurs, dtype=float)
    if masque is not None:
        serie = serie.where(masque)
    rang = (serie if croissant else -serie).rank(pct=True, method="average") * 100
    return rang.fillna(50.0).round(1).to_numpy()


def auc(scores, positifs):
    """Aire sous la courbe ROC : probabilité qu'un carreau positif ait un score plus haut
    qu'un carreau négatif (0,5 = hasard)."""
    rangs = rankdata(scores)
    n1, n0 = positifs.sum(), (~positifs).sum()
    return (rangs[positifs].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

lakehouse_id, point_sql_id = lakehouse_cible(LAKEHOUSE)
racine = f"abfss://{espace}@{endpoint}/{lakehouse_id}"

# La zone, les carreaux et leurs variables, les arrêts et les équipements (notebooks 01 à 05).
communes_zone = lire("zone_communes", ["code_commune", "nom", "contour_geojson"])
carreaux = lire(
    "carreaux", ["idcar_200m", "codes_communes", "x_3035", "y_3035", "lat", "lon", "population"]
)
variables = lire(
    "carreaux_variables",
    [
        "idcar_200m",
        "part_menages_sans_voiture",
        "emplois_5min",
        *[
            f"{famille}_5min"
            for famille in (
                "autres_commerces",
                "commerces_alimentaires",
                "services",
                "sante",
                "enseignement",
                "sport_loisirs_culture",
                "tourisme",
            )
        ],
    ],
)
arrets = lire("arrets", ["arret_id", "x_3035", "y_3035"])
arrets_lignes = lire("arrets_lignes", ["arret_id", "ligne_id", "passages_jour"])
equipements = lire("equipements", ["x_3035", "y_3035"])
stations = lire("stations_partagees", ["operateur", "idcar_200m", "dans_zone"])
carreaux = carreaux.merge(variables, on="idcar_200m", how="left", validate="one_to_one")
xy_carreaux = carreaux[["x_3035", "y_3035"]].to_numpy()

# Commune du centre de chaque carreau (celle de son code INSEE s'il tombe hors des contours).
contours = [shape(json.loads(g)) for g in communes_zone["contour_geojson"]]
index_communes = shapely.STRtree(contours)


def commune_de(lon, lat):
    """Code de la commune de la zone qui contient chaque point ; None hors de la zone."""
    points, polygones = index_communes.query(
        shapely.points(np.asarray(lon), np.asarray(lat)), predicate="within"
    )
    codes = np.full(len(lon), None, dtype=object)
    codes[points] = communes_zone["code_commune"].to_numpy()[polygones]
    return codes


carreaux["code_commune"] = commune_de(carreaux["lon"], carreaux["lat"])
carreaux["code_commune"] = carreaux["code_commune"].fillna(
    carreaux["codes_communes"].str.split(",").str[0]
)
sommets = np.concatenate([np.asarray(g.bounds).reshape(1, 4) for g in contours])
SUD, OUEST = sommets[:, 1].min() - MARGE_DEG, sommets[:, 0].min() - MARGE_DEG
NORD, EST = sommets[:, 3].max() + MARGE_DEG, sommets[:, 2].max() + MARGE_DEG
BOITE = f"{SUD:.4f},{OUEST:.4f},{NORD:.4f},{EST:.4f}"
print(f"{len(carreaux)} carreaux, boîte OSM {BOITE}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Les arbres
#
# OpenStreetMap a importé l'inventaire de Toulouse Métropole : à Toulouse, 93 % de ses
# arbres sont à moins d'un mètre d'un arbre de l'inventaire. Il apporte en plus des arbres
# relevés ailleurs (Colomiers, Balma, Saint-Orens-de-Gameville, Blagnac...). Un arbre OSM
# n'est gardé que s'il n'a pas de double dans l'inventaire.

# CELL ********************

def telecharger_arbres(copie):
    with session.get(URL_ARBRES, stream=True, timeout=1800, headers=AGENT) as reponse:
        reponse.raise_for_status()
        with open(copie, "wb") as fichier:
            for bloc in reponse.iter_content(chunk_size=1 << 20):
                fichier.write(bloc)
    pd.read_parquet(copie, columns=["id"])  # échoue sur un fichier incomplet


inventaire = pd.read_parquet(
    brut("toulouse_metropole/arbres-urbains.parquet", telecharger_arbres),
    columns=["id", "longitude", "latitude", "genre", "espece", "hauteur_approx_forestry"],
).dropna(subset=["longitude", "latitude"])
arbres_tm = pd.DataFrame(
    {
        "arbre_id": "tm:" + inventaire["id"].astype(str),
        "source": "toulouse_metropole",
        "lon": inventaire["longitude"],
        "lat": inventaire["latitude"],
        "genre": inventaire["genre"],
        "espece": inventaire["espece"],
        "hauteur": inventaire["hauteur_approx_forestry"],
    }
)
reponse_arbres = overpass(
    "arbres", f'[out:json][timeout:300];node["natural"="tree"]({BOITE});out qt;'
)
noeuds = reponse_arbres["elements"]
arbres_osm = pd.DataFrame(
    {
        "arbre_id": [f"osm:node/{n['id']}" for n in noeuds],
        "source": "osm",
        "lon": [n["lon"] for n in noeuds],
        "lat": [n["lat"] for n in noeuds],
        "genre": [n.get("tags", {}).get("genus") for n in noeuds],
        "espece": [n.get("tags", {}).get("species") for n in noeuds],
        # l'inventaire donne une classe (« 2 - 7 à 12m »), OSM une hauteur en mètres
        "hauteur": [
            f"{n['tags']['height']} m" if "height" in n.get("tags", {}) else None
            for n in noeuds
        ],
    }
)
for df in (arbres_tm, arbres_osm):
    df["x_3035"], df["y_3035"] = vers_metres.transform(
        df["lon"].to_numpy(), df["lat"].to_numpy()
    )
distance_inventaire, _ = cKDTree(arbres_tm[["x_3035", "y_3035"]].to_numpy()).query(
    arbres_osm[["x_3035", "y_3035"]].to_numpy(), distance_upper_bound=DOUBLON_ARBRE_M
)
nouveaux = arbres_osm[np.isinf(distance_inventaire)]
print(
    f"Inventaire : {len(arbres_tm)} arbres ; OSM : {len(arbres_osm)}, dont {len(nouveaux)} absents de l'inventaire"
)
arbres = pd.concat([arbres_tm, nouveaux], ignore_index=True)
arbres["code_commune"] = commune_de(arbres["lon"], arbres["lat"])
arbres["idcar_200m"] = idcar(arbres["x_3035"], arbres["y_3035"])
arbres[["x_3035", "y_3035"]] = arbres[["x_3035", "y_3035"]].round(1)

# Communes où les arbres sont mesurés : inventaire, ou densité OSM d'une commune inventoriée.
carreaux_par_commune = carreaux["code_commune"].value_counts()
par_commune = arbres.groupby(["code_commune", "source"]).size().unstack(fill_value=0)
par_commune = par_commune.reindex(carreaux_par_commune.index, fill_value=0)
couvertes = set(
    par_commune.index[
        (par_commune.get("toulouse_metropole", 0) >= ARBRES_INVENTAIRE_MIN)
        | (par_commune.sum(axis=1) / carreaux_par_commune >= ARBRES_PAR_CARREAU_MIN)
    ]
)
noms = communes_zone.set_index("code_commune")["nom"]
print("Arbres mesurés à : " + ", ".join(sorted(noms.get(c, c) for c in couvertes)))
carreaux["arbres_mesures"] = carreaux["code_commune"].isin(couvertes)
arbres["commune_mesuree"] = arbres["code_commune"].isin(couvertes)
xy_arbres = arbres[["x_3035", "y_3035"]].to_numpy()
index_arbres = cKDTree(xy_arbres)
ecrire("arbres", arbres)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Parkings et routes d'OpenStreetMap

# CELL ********************

reponse_parkings = overpass(
    "parkings",
    f'[out:json][timeout:300];nwr["amenity"="parking"]({BOITE});out tags geom qt;',
)
reponse_routes = overpass(
    "routes",
    f'[out:json][timeout:300];way["highway"~"^({"|".join(ROUTES)})(_link)?$"]({BOITE});out tags geom qt;',
)
extrait_le = pd.Timestamp(reponse_parkings["osm3s"]["timestamp_osm_base"]).tz_convert("UTC")


def ligne(points):
    return LineString([(p["lon"], p["lat"]) for p in points])


def geometrie_parking(element):
    """Point, contour fermé, ou multipolygone (contours extérieurs moins les cours intérieures)."""
    if element["type"] == "node":
        return Point(element["lon"], element["lat"])
    if element["type"] == "way":
        trace = ligne(element["geometry"])
        if trace.is_closed and len(trace.coords) >= 4:
            return Polygon(trace.coords)
        return trace
    membres = [
        m for m in element.get("members", []) if m.get("type") == "way" and m.get("geometry")
    ]
    exterieur = unary_union(
        list(polygonize(unary_union([ligne(m["geometry"]) for m in membres if m.get("role") != "inner"])))
    )
    interieurs = [ligne(m["geometry"]) for m in membres if m.get("role") == "inner"]
    if interieurs:
        exterieur = exterieur.difference(unary_union(list(polygonize(unary_union(interieurs)))))
    return exterieur


lignes_parkings = []
for element in reponse_parkings["elements"]:
    geometrie = geometrie_parking(element)
    if geometrie.is_empty:
        continue
    metres = en_metres(geometrie)
    if metres.geom_type in ("LineString", "MultiLineString"):
        metres = metres.buffer(1.25)  # parking dessiné comme une ligne : une file de places
    tags = element.get("tags", {})
    centre = metres.representative_point()
    lignes_parkings.append(
        {
            "osm_id": f"{element['type']}/{element['id']}",
            "nom": tags.get("name"),
            "type_parking": tags.get("parking"),
            "acces": tags.get("access"),
            "payant": tags.get("fee"),
            "capacite": entier(tags.get("capacity")),
            "surface_m2": round(metres.area, 1) if metres.area > 0 else np.nan,
            "x_3035": round(centre.x, 1),
            "y_3035": round(centre.y, 1),
            "contour_wkt": geometrie.wkt,
            "geometrie_3035": metres,
        }
    )
parkings = pd.DataFrame(lignes_parkings)
parkings["capacite"] = parkings["capacite"].astype("Int64")
parkings["lon"], parkings["lat"] = vers_degres.transform(
    parkings["x_3035"].to_numpy(), parkings["y_3035"].to_numpy()
)
parkings["public"] = ~parkings["acces"].isin(ACCES_RESERVES)
parkings["idcar_200m"] = idcar(parkings["x_3035"], parkings["y_3035"])
parkings["code_commune"] = commune_de(parkings["lon"], parkings["lat"])
parkings["dans_zone"] = parkings["code_commune"].notna()
parkings["extrait_le"] = extrait_le
ecrire("parkings_osm", parkings.drop(columns="geometrie_3035"))

routes = pd.DataFrame(
    [
        {
            "osm_id": f"way/{element['id']}",
            "type_route": element["tags"]["highway"],
            "nom": element["tags"].get("name"),
            "ref": element["tags"].get("ref"),
            "geometrie": ligne(element["geometry"]),
        }
        for element in reponse_routes["elements"]
        if len(element.get("geometry", [])) >= 2
    ]
)
routes["geometrie_3035"] = [en_metres(g) for g in routes["geometrie"]]
routes["longueur_m"] = [round(g.length, 1) for g in routes["geometrie_3035"]]
routes["trace_wkt"] = [g.wkt for g in routes["geometrie"]]
routes["extrait_le"] = pd.Timestamp(
    reponse_routes["osm3s"]["timestamp_osm_base"]
).tz_convert("UTC")
ecrire("routes_osm", routes.drop(columns=["geometrie", "geometrie_3035"]))


def points_des_routes(types):
    """Sommets des routes de ces types, redécoupées tous les 10 m : la distance au plus proche
    sommet approche celle de la route à 5 m près."""
    garde = routes["type_route"].str.replace("_link", "").isin(types)
    return np.concatenate(
        [
            shapely.get_coordinates(shapely.segmentize(g, 10))
            for g in routes.loc[garde, "geometrie_3035"]
        ]
    )


index_routes = cKDTree(points_des_routes(ROUTES))
index_axes = cKDTree(points_des_routes(AXES))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Les 8 critères
#
# | Critère (mot de Citiz) | Valeur brute | Sens |
# | --- | --- | --- |
# | Transports collectifs | passages par jour des lignes qui s'arrêtent à `rayon_m`, chaque ligne comptée une fois, à son arrêt le plus desservi | plus = mieux |
# | Densité urbaine | habitants à `rayon_m` | plus = mieux |
# | Mixité habitat/activité | équilibre emplois/habitants à `rayon_m` (1 - abs(2 × part des emplois - 1)) et équipements à `rayon_m` | plus = mieux |
# | Accessibilité/circulation | distance à la route principale la plus proche | moins = mieux |
# | Simple pour stationner | parkings publics OSM à moins de 200 m, nombre et surface | plus = mieux |
# | Taux de motorisation faible | part des ménages sans voiture (IRIS) | plus = mieux |
# | Visible | commerces et équipements à moins de 200 m, et distance à l'axe passant (primary, secondary) le plus proche | plus, puis moins = mieux |
# | Arbres à distance | part du carreau à plus de 10 m de tout arbre | plus = mieux |
#
# Quand un critère a deux valeurs brutes, sa note est la moyenne de leurs deux rangs.

# CELL ********************

n = len(carreaux)
voisins = cKDTree(xy_carreaux)

# Transports collectifs : chaque ligne une fois, à son arrêt le plus desservi dans le rayon.
proches = cKDTree(arrets[["x_3035", "y_3035"]].to_numpy()).query_ball_point(xy_carreaux, r=RAYON_M)
paires = pd.DataFrame(
    {
        "carreau": np.repeat(np.arange(n), [len(p) for p in proches]),
        "arret_id": arrets["arret_id"].to_numpy()[np.concatenate(proches).astype(int)],
    }
)
desserte = (
    paires.merge(arrets_lignes, on="arret_id")
    .groupby(["carreau", "ligne_id"])["passages_jour"]
    .max()
    .groupby(level="carreau")
    .agg(["sum", "size"])
)
carreaux["passages_jour_400m"] = desserte["sum"].reindex(range(n), fill_value=0).astype(int).to_numpy()
carreaux["lignes_400m"] = desserte["size"].reindex(range(n), fill_value=0).astype(int).to_numpy()

# Densité urbaine : habitants des carreaux dont le centre est dans le rayon.
population = carreaux["population"].to_numpy()
carreaux["habitants_400m"] = [
    round(population[p].sum()) for p in voisins.query_ball_point(xy_carreaux, r=RAYON_M)
]

# Mixité : emplois et habitants à 5 minutes, et équipements à 5 minutes.
emplois = carreaux["emplois_5min"].fillna(0).to_numpy(float)
actifs = emplois + carreaux["habitants_400m"].to_numpy(float)
part_emplois = np.divide(emplois, actifs, out=np.zeros(n), where=actifs > 0)
carreaux["equilibre_emplois_habitants"] = (1 - np.abs(2 * part_emplois - 1)).round(3)
carreaux["equipements_5min"] = (
    carreaux.filter(like="_5min").drop(columns=["emplois_5min"]).fillna(0).sum(axis=1).astype(int)
)

# Accessibilité : distance du centre à la route principale la plus proche.
carreaux["dist_route_m"] = index_routes.query(xy_carreaux)[0].round(0)

# Simple pour stationner : parkings publics dont le centre est à moins de 200 m.
publics = parkings[parkings["public"]].reset_index(drop=True)
autour = cKDTree(publics[["x_3035", "y_3035"]].to_numpy()).query_ball_point(xy_carreaux, r=RAYON_PARKING_M)
surfaces = publics["surface_m2"].fillna(0).to_numpy()
carreaux["parkings_200m"] = [len(p) for p in autour]
carreaux["surface_parkings_200m_m2"] = [round(surfaces[p].sum()) for p in autour]

# Visible : commerces et équipements à 200 m, et distance à l'axe passant le plus proche.
carreaux["equipements_200m"] = cKDTree(equipements[["x_3035", "y_3035"]].to_numpy()).query_ball_point(
    xy_carreaux, r=RAYON_VISIBLE_M, return_length=True
)
carreaux["dist_axe_m"] = index_axes.query(xy_carreaux)[0].round(0)

# Arbres à distance : arbres du carreau, et part de sa surface à plus de 10 m de tout arbre
# (grille de points tous les PAS_DEGAGEMENT_M).
carreaux["arbres_carreau"] = (
    carreaux["idcar_200m"].map(arbres["idcar_200m"].value_counts()).fillna(0).astype(float)
)
decalages = np.arange(PAS_DEGAGEMENT_M / 2 - 100, 100, PAS_DEGAGEMENT_M)
gx, gy = np.meshgrid(decalages, decalages)
grille = np.column_stack([gx.ravel(), gy.ravel()])
part_degagee = np.empty(n)
for debut in range(0, n, 500):
    centres = xy_carreaux[debut : debut + 500]
    essais = (centres[:, None, :] + grille[None, :, :]).reshape(-1, 2)
    distance, _ = index_arbres.query(essais, distance_upper_bound=DISTANCE_ARBRE_MIN_M)
    part_degagee[debut : debut + 500] = (
        np.isinf(distance).reshape(len(centres), -1).mean(axis=1)
    )
carreaux["part_sans_arbre_10m"] = part_degagee.round(3)
carreaux.loc[~carreaux["arbres_mesures"], ["arbres_carreau", "part_sans_arbre_10m"]] = np.nan

# Les notes : rang centile dans la zone ; moyenne des deux rangs quand il y a deux valeurs.
mesures = carreaux["arbres_mesures"].to_numpy()
carreaux["note_transports"] = note(carreaux["passages_jour_400m"])
carreaux["note_densite"] = note(carreaux["habitants_400m"])
carreaux["note_mixite"] = (
    (note(carreaux["equilibre_emplois_habitants"]) + note(carreaux["equipements_5min"])) / 2
).round(1)
carreaux["note_accessibilite"] = note(carreaux["dist_route_m"], croissant=False)
carreaux["note_stationnement"] = (
    (note(carreaux["parkings_200m"]) + note(carreaux["surface_parkings_200m_m2"])) / 2
).round(1)
carreaux["note_motorisation"] = note(carreaux["part_menages_sans_voiture"])
carreaux["note_visibilite"] = (
    (note(carreaux["equipements_200m"]) + note(carreaux["dist_axe_m"], croissant=False)) / 2
).round(1)
carreaux["note_arbres"] = note(carreaux["part_sans_arbre_10m"], masque=mesures)
NOTES = [c for c in carreaux if c.startswith("note_")]
carreaux["indice_citiz"] = carreaux[NOTES].mean(axis=1).round(1)
print(carreaux[NOTES + ["indice_citiz"]].describe().round(1).T)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## L'indice a-t-il du sens ?
#
# Les stations Citiz actuelles ont été placées par Citiz, avec ses critères : leurs carreaux
# devraient avoir un indice plus haut que les autres. L'AUC est la probabilité qu'un carreau
# qui a une station ait un indice plus haut qu'un carreau qui n'en a pas (0,5 = le hasard).

# CELL ********************

avec_citiz = carreaux["idcar_200m"].isin(
    stations.loc[(stations["operateur"] == "Citiz") & stations["dans_zone"], "idcar_200m"]
).to_numpy()
print(
    f"{avec_citiz.sum()} carreaux avec une station Citiz : indice moyen "
    f"{carreaux.loc[avec_citiz, 'indice_citiz'].mean():.1f}, contre "
    f"{carreaux.loc[~avec_citiz, 'indice_citiz'].mean():.1f} pour les {(~avec_citiz).sum()} autres"
)
validation = pd.DataFrame(
    {
        "moyenne_avec_station": carreaux.loc[avec_citiz, NOTES + ["indice_citiz"]].mean(),
        "moyenne_sans_station": carreaux.loc[~avec_citiz, NOTES + ["indice_citiz"]].mean(),
        "auc": [auc(carreaux[c].to_numpy(), avec_citiz) for c in NOTES + ["indice_citiz"]],
    }
).round(3)
print(validation)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Une place précise par carreau
#
# Dans chaque parking public, on essaie un point tous les `PAS_PLACE_M` mètres et on mesure
# sa distance à l'arbre le plus proche. La place du carreau est le point le plus éloigné des
# arbres, tous parkings du carreau confondus, s'il l'est d'au moins `DISTANCE_ARBRE_MIN_M`.
# Là où les arbres ne sont pas mesurés, c'est le centre du plus grand parking public du
# carreau, sans distance. Son adresse vient de la Base adresse nationale, en un seul envoi.

# CELL ********************

lignes_essais = []
for i, geometrie in enumerate(publics["geometrie_3035"]):
    if geometrie.geom_type == "Point":
        x, y = np.array([geometrie.x]), np.array([geometrie.y])
    else:
        xmin, ymin, xmax, ymax = geometrie.bounds
        gx, gy = np.meshgrid(
            np.arange(xmin + PAS_PLACE_M / 2, xmax, PAS_PLACE_M),
            np.arange(ymin + PAS_PLACE_M / 2, ymax, PAS_PLACE_M),
        )
        dedans = shapely.contains_xy(geometrie, gx.ravel(), gy.ravel())
        if dedans.any():
            x, y = gx.ravel()[dedans], gy.ravel()[dedans]
        else:  # parking plus petit que la grille : son point intérieur
            centre = geometrie.representative_point()
            x, y = np.array([centre.x]), np.array([centre.y])
    lignes_essais.append(pd.DataFrame({"parking": i, "x_3035": x, "y_3035": y}))
essais = pd.concat(lignes_essais, ignore_index=True)
essais["idcar_200m"] = idcar(essais["x_3035"], essais["y_3035"])
essais = essais[essais["idcar_200m"].isin(set(carreaux["idcar_200m"]))]
essais["dist_arbre_m"] = index_arbres.query(essais[["x_3035", "y_3035"]].to_numpy())[0]
essais = essais.merge(carreaux[["idcar_200m", "arbres_mesures"]], on="idcar_200m")
print(f"{len(essais)} points essayés dans {essais['parking'].nunique()} parkings publics")

# Arbres mesurés : le point le plus éloigné des arbres, s'il l'est assez.
mesures_essais = essais[essais["arbres_mesures"]]
loin = mesures_essais.loc[mesures_essais.groupby("idcar_200m")["dist_arbre_m"].idxmax()]
loin = loin[loin["dist_arbre_m"] >= DISTANCE_ARBRE_MIN_M]
# Arbres non mesurés : le point du plus grand parking le plus proche de son centre.
autres = essais[~essais["arbres_mesures"]].copy()
autres["taille"] = publics["surface_m2"].fillna(0).to_numpy()[autres["parking"]]
autres["ecart"] = np.hypot(
    autres["x_3035"] - publics["x_3035"].to_numpy()[autres["parking"]],
    autres["y_3035"] - publics["y_3035"].to_numpy()[autres["parking"]],
)
grand = autres.sort_values(["idcar_200m", "taille", "ecart"], ascending=[True, False, True])
grand = grand.drop_duplicates("idcar_200m").assign(dist_arbre_m=np.nan)
places = pd.concat([loin, grand], ignore_index=True)
infos = publics.drop(columns=["geometrie_3035", "x_3035", "y_3035", "lon", "lat", "idcar_200m", "contour_wkt", "extrait_le"])
places = places.join(infos, on="parking").drop(columns=["parking"])
places = places.rename(columns={"osm_id": "parking_osm_id", "nom": "nom_parking"})
places["lon"], places["lat"] = vers_degres.transform(places["x_3035"].to_numpy(), places["y_3035"].to_numpy())
places[["lon", "lat"]] = places[["lon", "lat"]].round(6)
places[["x_3035", "y_3035"]] = places[["x_3035", "y_3035"]].round(1)
places["dist_arbre_m"] = places["dist_arbre_m"].round(1)
places = places.drop(columns=["taille", "ecart"], errors="ignore").sort_values("idcar_200m").reset_index(drop=True)

# Adresse : géocodage inverse de la Base adresse nationale, un seul fichier CSV.
places["adresse"] = None
try:
    envoi = places[["idcar_200m", "lat", "lon"]].to_csv(index=False)
    reponse = session.post(
        URL_BAN_INVERSE, files={"data": ("places.csv", envoi, "text/csv")}, headers=AGENT, timeout=900
    )
    reponse.raise_for_status()
    adresses = pd.read_csv(io.StringIO(reponse.text), dtype=str).drop_duplicates("idcar_200m")
    adresses = adresses.set_index("idcar_200m")
    places["adresse"] = places["idcar_200m"].map(adresses["result_label"])
    places["adresse_distance_m"] = pd.to_numeric(places["idcar_200m"].map(adresses["result_distance"]))
    places["adresse_type"] = places["idcar_200m"].map(adresses["result_type"])
except Exception as e:  # le service est parfois saturé : les places restent, sans adresse
    print(f"Adresses non trouvées ({e!r})")
places["calcule_le"] = dt.date.today()
print(
    f"{len(places)} carreaux avec une place : {len(loin)} à {DISTANCE_ARBRE_MIN_M} m ou plus de tout arbre, "
    f"{len(grand)} là où les arbres ne sont pas mesurés ; {places['adresse'].notna().sum()} adresses"
)
ecrire("places_candidates", places)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# La table des critères : valeurs brutes, notes, indice, et la distance de la place proposée.
criteres = carreaux[
    [
        "idcar_200m",
        "code_commune",
        "population",
        "passages_jour_400m",
        "lignes_400m",
        "habitants_400m",
        "equilibre_emplois_habitants",
        "equipements_5min",
        "dist_route_m",
        "parkings_200m",
        "surface_parkings_200m_m2",
        "part_menages_sans_voiture",
        "equipements_200m",
        "dist_axe_m",
        "arbres_carreau",
        "part_sans_arbre_10m",
        "arbres_mesures",
        *NOTES,
        "indice_citiz",
    ]
].merge(places[["idcar_200m", "dist_arbre_m"]].rename(columns={"dist_arbre_m": "dist_arbre_place_m"}), on="idcar_200m", how="left")
criteres["a_place"] = criteres["idcar_200m"].isin(set(places["idcar_200m"]))
criteres["station_citiz"] = avec_citiz
criteres["arbres_carreau"] = criteres["arbres_carreau"].astype("Int64")
criteres["calcule_le"] = dt.date.today()
assert len(criteres) == len(carreaux) and criteres["idcar_200m"].is_unique
assert criteres[NOTES + ["indice_citiz"]].notna().all().all()
ecrire("criteres_citiz", criteres)
synchroniser_point_sql()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
