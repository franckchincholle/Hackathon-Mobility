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

# # Stations partagées (GBFS)
#
# Charge les systèmes de véhicules partagés (format GBFS) et construit trois tables :
#
# - `stations_partagees` : les stations de la zone (vélos, autopartage...) et celles à
#   moins de `rayon_m` d'un de ses carreaux (une station juste derrière la limite sert aussi
#   les habitants du bord) ; la colonne `dans_zone` les distingue. La colonne `virtuelle`
#   repère les zones de dépose sans équipement que l'opérateur déclare comme stations
#   (toutes celles de Pony à Perpignan) : à écarter pour compter les options (décision 3)
#   si l'équipe le décide.
# - `citiz_stations` : toutes les stations Citiz de France (15 réseaux régionaux), avec le
#   carreau INSEE où elles se trouvent, pour la cible du modèle (décision 7).
# - `vehicules_libres` : une photo à l'instant T des véhicules sans station
#   (free-floating). Ils ne comptent pas comme option de transport (décision 3).
#
# Les systèmes de la zone sont trouvés dans le catalogue de transport.data.gouv.fr : ceux
# dont la couverture déclarée touche une commune, une intercommunalité, un département ou la
# région de la zone. Les 15 réseaux Citiz forment une liste fixe, la même que celle de
# 04_collecte_citiz, pour que les identifiants de stations des deux tables se rejoignent.
# Le type d'un véhicule (vélo, trottinette, scooter) est celui que l'opérateur déclare.
#
# Chaque point porte ses coordonnées en lat/lon, en mètres (EPSG:3035, la projection des
# carreaux INSEE) et l'identifiant du carreau où il se trouve. Les réglages viennent de la
# bibliothèque de variables `parametres_mobilite` ; 01_carreaux doit avoir tourné avant,
# avec le même jeu de valeurs.

# CELL ********************

import datetime as dt
import json
import math
import re
import unicodedata

import notebookutils
import numpy as np
import pandas as pd
import requests
from deltalake import DeltaTable, write_deltalake
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
LAKEHOUSE = parametres.lakehouse
RAYON_M = int(parametres.rayon_m)
CATALOGUE = "https://transport.data.gouv.fr/api/datasets"
# Les 15 flux GBFS régionaux de Citiz publiés sur transport.data.gouv.fr ; la même liste
# sert au notebook 04_collecte_citiz.
FLUX_CITIZ = {
    "developpement": "https://www.data.gouv.fr/api/1/datasets/r/e64161a2-b7f9-4562-9f13-50a7b758e04a",
    "auvergne_rhone_alpes": "https://www.data.gouv.fr/api/1/datasets/r/4553afe7-fdc4-4f0f-98e5-9d11b5039c57",
    "grand_est": "https://www.data.gouv.fr/api/1/datasets/r/0a81bd24-df76-4d1f-a712-3265b1ee75d8",
    "metropole_de_lyon": "https://www.data.gouv.fr/api/1/datasets/r/5ca23de0-8f2d-442b-addb-f423f5da11cc",
    "provence": "https://www.data.gouv.fr/api/1/datasets/r/4d37b9c9-1014-4981-9810-6601e558198c",
    "occitanie": "https://www.data.gouv.fr/api/1/datasets/r/a73a8d89-a43e-4d9b-883d-854b5864a4bf",
    "hauts_de_france": "https://www.data.gouv.fr/api/1/datasets/r/ea739e26-e3b8-4e93-84d3-31b12c12a10d",
    "nantes_metropole": "https://www.data.gouv.fr/api/1/datasets/r/644cc960-79a3-41ae-bdfe-4efbcb81f04e",
    "gironde": "https://www.data.gouv.fr/api/1/datasets/r/4a69aee4-05ea-45e9-81b7-f9dbdfc7a344",
    "rennes_metropole": "https://www.data.gouv.fr/api/1/datasets/r/9d526d49-1db5-48f8-baa0-a5b83991a222",
    "pays_basque": "https://www.data.gouv.fr/api/1/datasets/r/3c8fc225-a3e0-42fb-86e6-e696c629415f",
    "bourgogne_franche_comte": "https://www.data.gouv.fr/api/1/datasets/r/9713ac07-d86f-4e04-9368-9c78af612c67",
    "angers_loire_metropole": "https://www.data.gouv.fr/api/1/datasets/r/03bae304-927d-4e0e-80fd-2238bd582d4c",
    "grand_poitiers": "https://www.data.gouv.fr/api/1/datasets/r/3d6ff3dc-f3c5-4e23-a508-0420be4c46c4",
    "la_rochelle": "https://www.data.gouv.fr/api/1/datasets/r/a2158a72-466a-4a3f-b7cd-4267538f44b2",
}
# Nom court et opérateur des systèmes publiés le premier jour, gardés pour ne pas changer
# les identifiants et les libellés que l'équipe utilise déjà.
NOMS_PUBLIES = {
    "VLS VélôToulouse Toulouse Métropole": ("velotoulouse", "VélôToulouse"),
    "Scooters YEGO Toulouse": ("yego_toulouse", "YEGO"),
}
PREFIXES = ("VLS ", "Scooters ", "Vélos et trottinettes ", "Trottinettes ", "Vélos ")
# Forme d'un véhicule GBFS (form_factor) et type retenu dans les tables.
FORMES = {
    "bicycle": "velo",
    "cargo_bicycle": "velo",
    "scooter": "trottinette",
    "scooter_standing": "trottinette",
    "scooter_seated": "scooter",
    "moped": "scooter",
    "car": "autopartage",
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
jour = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
# Quatre essais espacés de 2, 4 puis 8 s : les serveurs GBFS coupent parfois une connexion.
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


def nom_court(titre):
    """Nom court d'un système, tiré de son titre au catalogue : « VLS Vélomagg ... » donne « velomagg_... »."""
    for prefixe in PREFIXES:
        if titre.startswith(prefixe):
            titre = titre[len(prefixe) :]
            break
    sans_accents = (
        unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "_", sans_accents.lower()).strip("_")


def flux_systeme(url):
    """Flux d'un système GBFS, {nom: adresse}, en GBFS 3.0 comme en 2.x."""
    donnees = session.get(url, timeout=60).json()["data"]
    if "feeds" not in donnees:  # GBFS 2.x : les flux sont rangés par langue
        donnees = donnees.get("fr") or next(iter(donnees.values()))
    return {f["name"]: f["url"] for f in donnees["feeds"]}


def lire_flux(flux, nom, garde_sous):
    """Contenu d'un flux, gardé brut dans Files/brut/gbfs/<jour>/."""
    reponse = session.get(flux[nom], timeout=60)
    reponse.raise_for_status()
    notebookutils.fs.put(
        f"{racine}/Files/brut/gbfs/{jour}/{garde_sous}_{nom}.json", reponse.text, True
    )
    return reponse.json()


def texte(valeur):
    """Les noms sont des chaînes en GBFS 2.x et des listes traduites en GBFS 3.0."""
    if isinstance(valeur, list):
        return next(
            (v["text"] for v in valeur if v.get("language") == "fr"),
            valeur[0]["text"] if valeur else None,
        )
    return valeur


def horodatage(valeur):
    """GBFS 3.0 date en ISO, GBFS 2.x en secondes depuis 1970 : tout passe en UTC."""
    if isinstance(valeur, (int, float)):
        return pd.to_datetime(valeur, unit="s", utc=True)
    return pd.to_datetime(valeur, utc=True)


vers_metres = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def placer(df):
    """Ajoute x/y en mètres (EPSG:3035) et l'identifiant INSEE du carreau de 200 m du point."""
    x, y = vers_metres.transform(df["lon"].to_numpy(), df["lat"].to_numpy())
    df["x_3035"], df["y_3035"] = x.round(1), y.round(1)
    df["idcar_200m"] = [
        f"CRS3035RES200mN{int(b // 200) * 200}E{int(a // 200) * 200}"
        for a, b in zip(x, y)
    ]
    return df


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

lakehouse_id, point_sql_id = lakehouse_cible(LAKEHOUSE)
racine = f"abfss://{espace}@{endpoint}/{lakehouse_id}"

# La zone, écrite par 01_carreaux : ses communes (codes et contours) et les centres de ses
# carreaux habités, rangés par case de la grille de 200 m.
communes_zone = lire("zone_communes")
couverture_zone = {
    "commune": set(communes_zone["code_commune"]),
    "epci": set(communes_zone["code_epci"].dropna()),
    "departement": set(communes_zone["code_departement"].dropna()),
    "region": set(communes_zone["code_region"].dropna()),
}
anneaux_zone = [
    [
        np.asarray(anneau, dtype=float)
        for polygone in (
            g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        )
        for anneau in polygone
    ]
    for g in map(json.loads, communes_zone["contour_geojson"])
]


# Rectangle qui entoure chaque commune : on ne teste le contour que des communes dont le
# rectangle contient le point.
def boite(anneaux):
    """[lon_min, lat_min, lon_max, lat_max] du contour d'une commune."""
    sommets = np.concatenate(anneaux)
    return [*sommets.min(axis=0), *sommets.max(axis=0)]


boites = np.array([boite(anneaux) for anneaux in anneaux_zone])
zone = lire("carreaux", ["x_3035", "y_3035"])
cases_zone = set(
    zip((zone["x_3035"] // 200).astype(int), (zone["y_3035"] // 200).astype(int))
)
portee = math.ceil(RAYON_M / 200)


def dans_la_zone(lon, lat):
    """Vrai si le point est dans une commune de la zone (règle pair-impair sur son contour)."""
    candidates = np.flatnonzero(
        (boites[:, 0] <= lon)
        & (lon <= boites[:, 2])
        & (boites[:, 1] <= lat)
        & (lat <= boites[:, 3])
    )
    for k in candidates:
        croisements = 0
        for a in anneaux_zone[k]:
            x1, y1, x2, y2 = (
                a[:, 0],
                a[:, 1],
                np.roll(a[:, 0], -1),
                np.roll(a[:, 1], -1),
            )
            coupe = (y1 > lat) != (y2 > lat)
            x_coupe = x1[coupe] + (lat - y1[coupe]) * (x2[coupe] - x1[coupe]) / (
                y2[coupe] - y1[coupe]
            )
            croisements += int(np.count_nonzero(lon < x_coupe))
        if croisements % 2:
            return True
    return False


def pres_de_la_zone(x, y):
    """Vrai si le point est à RAYON_M ou moins du centre d'un carreau habité de la zone."""
    i0, j0 = int(x // 200), int(y // 200)
    return any(
        (i, j) in cases_zone
        and math.hypot(i * 200 + 100 - x, j * 200 + 100 - y) <= RAYON_M
        for i in range(i0 - portee, i0 + portee + 1)
        for j in range(j0 - portee, j0 + portee + 1)
    )


def garder_zone(df):
    """Garde les points de la zone et ceux à moins de RAYON_M d'un de ses carreaux."""
    df["dans_zone"] = [dans_la_zone(lon, lat) for lon, lat in zip(df["lon"], df["lat"])]
    pres = np.array(
        [pres_de_la_zone(x, y) for x, y in zip(df["x_3035"], df["y_3035"])], dtype=bool
    )
    return df[df["dans_zone"].to_numpy() | pres].reset_index(drop=True)


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def stations(reseau, flux, operateur, type_station):
    contenu = lire_flux(flux, "station_information", reseau)
    return pd.DataFrame(
        [
            {
                "station_id": f"{reseau}:{s['station_id']}",
                "operateur": operateur,
                "type": type_station,
                "reseau": reseau,
                "nom": texte(s.get("name")),
                "adresse": s.get("address"),
                "capacite": s.get("capacity"),
                "virtuelle": bool(s.get("is_virtual_station", False)),
                "lat": float(s["lat"]),
                "lon": float(s["lon"]),
            }
            for s in contenu["data"]["stations"]
        ]
    )


citiz, erreurs = [], []
for reseau, url in FLUX_CITIZ.items():
    try:
        citiz.append(stations(reseau, flux_systeme(url), "Citiz", "autopartage"))
    except Exception as e:
        erreurs.append(f"{reseau} : {e!r}")
if erreurs:
    raise RuntimeError("Flux Citiz en échec : " + " ; ".join(erreurs))
citiz = placer(pd.concat(citiz, ignore_index=True))
citiz["capacite"] = pd.to_numeric(citiz["capacite"], errors="coerce").astype("Int64")

# Deux réseaux qui publieraient la même station : même nom au même endroit, à 10 m près.
citiz["doublon"] = pd.DataFrame(
    {"nom": citiz["nom"], "lat": citiz["lat"].round(4), "lon": citiz["lon"].round(4)}
).duplicated()
print(
    f"Citiz : {len(citiz)} stations sur {citiz['reseau'].nunique()} réseaux, "
    f"{int(citiz['doublon'].sum())} doublons retirés"
)
citiz = citiz[~citiz.pop("doublon")].reset_index(drop=True)
assert citiz["station_id"].is_unique
ecrire("citiz_stations", citiz)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def touche_la_zone(jeu):
    """Vrai si la couverture déclarée du jeu touche une commune, une intercommunalité, un département ou la région de la zone."""
    return any(
        str(z.get("insee")) in couverture_zone.get(z.get("type"), set())
        for z in jeu.get("covered_area") or []
    )


catalogue = session.get(CATALOGUE, timeout=300).json()
systemes = [
    jeu
    for jeu in catalogue
    if jeu.get("type") == "vehicles-sharing"
    and "citiz" not in jeu["title"].lower()
    and touche_la_zone(jeu)
]
avec_stations, sans_station, erreurs = [citiz], [], []
for jeu in systemes:
    ressources = [
        r
        for r in jeu.get("resources", [])
        if r.get("format") == "gbfs" and r.get("is_available", True)
    ]
    if not ressources:
        print(f"Sans flux GBFS, écarté : {jeu['title']}")
        continue
    reseau, operateur = NOMS_PUBLIES.get(jeu["title"], (nom_court(jeu["title"]), None))
    try:
        flux = flux_systeme(
            max(ressources, key=lambda r: r.get("updated") or "")["url"]
        )
        if operateur is None and "system_information" in flux:
            operateur = texte(
                lire_flux(flux, "system_information", reseau)["data"].get("name")
            )
        operateur = operateur or jeu["title"]
        formes = {}
        if "vehicle_types" in flux:
            formes = {
                t["vehicle_type_id"]: FORMES.get(t.get("form_factor"), "autre")
                for t in lire_flux(flux, "vehicle_types", reseau)["data"][
                    "vehicle_types"
                ]
            }
        if "station_information" in flux:
            type_station = ",".join(sorted(set(formes.values()))) or (
                "velo" if jeu["title"].startswith("VLS") else "autre"
            )
            avec_stations.append(stations(reseau, flux, operateur, type_station))
            print(f"{reseau} : stations ({type_station})")
        else:
            nom_flux = (
                "vehicle_status" if "vehicle_status" in flux else "free_bike_status"
            )
            contenu = lire_flux(flux, nom_flux, reseau)
            releve = horodatage(contenu["last_updated"])
            vehicules = (
                contenu["data"].get("vehicles") or contenu["data"].get("bikes") or []
            )
            sans_station.append(
                pd.DataFrame(
                    [
                        {
                            "vehicule_id": f"{reseau}:{v.get('vehicle_id') or v.get('bike_id')}",
                            "operateur": operateur,
                            "type": formes.get(v.get("vehicle_type_id"), "autre"),
                            "reseau": reseau,
                            "reserve": bool(v.get("is_reserved")),
                            "desactive": bool(v.get("is_disabled")),
                            "autonomie_m": v.get("current_range_meters"),
                            "lat": float(v["lat"]),
                            "lon": float(v["lon"]),
                            "releve_utc": releve,
                        }
                        for v in vehicules
                        if v.get("lat") is not None
                    ]
                )
            )
            print(f"{reseau} : {len(vehicules)} véhicules sans station")
    except Exception as e:
        erreurs.append(f"{reseau} : {e!r}")
        print(f"{reseau} écarté : {e!r}")

partagees = placer(pd.concat(avec_stations, ignore_index=True))
partagees["capacite"] = pd.to_numeric(partagees["capacite"], errors="coerce").astype(
    "Int64"
)
partagees = garder_zone(partagees)
print(partagees.groupby(["operateur", "dans_zone"]).size().to_string())
ecrire("stations_partagees", partagees)

if sans_station:
    libres = placer(pd.concat(sans_station, ignore_index=True))
    libres["releve_utc"] = libres["releve_utc"].astype("datetime64[us, UTC]")
    libres["autonomie_m"] = pd.to_numeric(
        libres["autonomie_m"], errors="coerce"
    ).astype("float64")
    ecrire("vehicules_libres", garder_zone(libres))
else:
    print("Aucun véhicule sans station dans la zone")
synchroniser_point_sql()
# Un système en échec est signalé après l'écriture : les tables gardent les autres, et
# l'exécution apparaît en échec dans le suivi.
if erreurs:
    raise RuntimeError("Systèmes GBFS en échec : " + " ; ".join(erreurs))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
