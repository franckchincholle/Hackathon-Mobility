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

# # Arrêts de transport en commun (GTFS)
#
# Charge les GTFS des réseaux qui desservent la zone et construit deux tables :
#
# - `arrets` : un arrêt par zone d'arrêt GTFS (`parent_station`) et par réseau. Le
#   dédoublonnage se fait en deux temps : les quais d'un même arrêt (un par sens, par voie)
#   sont regroupés sous leur zone d'arrêt, puis deux zones d'arrêt du même réseau, au même
#   nom et à moins de `fusion_homonymes_m`, sont fusionnées (le producteur ne leur a pas
#   donné de parent commun).
# - `arrets_lignes` : chaque ligne qui s'arrête à chaque arrêt, avec son mode et son nombre
#   de passages un mardi hors vacances scolaires (le bonus fréquence de la décision 3).
#
# Les réseaux sont trouvés dans le catalogue de transport.data.gouv.fr : ceux dont la
# couverture déclarée touche une commune, une intercommunalité, un département ou la région
# de la zone. Le GTFS national de la SNCF s'y ajoute, réduit aux TER (trains et cars) : les
# TGV, Intercités et Ouigo font de la longue distance.
#
# Une ligne a un identifiant unique (`ligne_id` : réseau, exploitant et nom commercial) :
# ses variantes et ses deux sens ne comptent qu'une fois. On garde les arrêts de la zone et
# ceux à moins de `rayon_m` d'un de ses carreaux. Les réglages viennent de la bibliothèque
# de variables `parametres_mobilite` ; 01_carreaux doit avoir tourné avant, avec le même
# jeu de valeurs.

# CELL ********************

import datetime as dt
import io
import json
import math
import os
import re
import tempfile
import time
import unicodedata
import zipfile

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
SEMAINES = int(parametres.semaines_reference)
FUSION_M = int(parametres.fusion_homonymes_m)
CATALOGUE = "https://transport.data.gouv.fr/api/datasets"
# Le GTFS national de la SNCF couvre toute la France : la zone ne le désigne pas, il
# s'ajoute à part. Le service est écrit dans l'identifiant du quai
# ("StopPoint:OCETrain TER-87611004") : on ne garde que les quais des TER.
GTFS_NATIONAUX = {
    "sncf_ter": "https://www.data.gouv.fr/api/1/datasets/r/9ae758ec-cd7a-40cd-a890-bb3963224942"
}
FILTRE_QUAIS = {"sncf_ter": " TER-"}
# Noms courts des réseaux publiés le premier jour, gardés pour ne pas changer les
# identifiants d'arrêts que l'équipe utilise déjà.
NOMS_PUBLIES = {
    "Réseau urbain Tisséo": "tisseo",
    "Réseau interurbain liO Occitanie": "lio",
}
PREFIXES = ("Réseau urbain et scolaire ", "Réseau urbain ", "Réseau interurbain ")
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


def nom_court(titre):
    """Nom court d'un réseau, tiré de son titre au catalogue : « Réseau urbain TaM » donne « tam »."""
    if titre in NOMS_PUBLIES:
        return NOMS_PUBLIES[titre]
    for prefixe in PREFIXES:
        if titre.startswith(prefixe):
            titre = titre[len(prefixe) :]
            break
    sans_accents = (
        unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "_", sans_accents.lower()).strip("_")


def telecharger(reseau, url):
    """Archive GTFS du jour, gardée brute dans Files/brut/gtfs/<jour>/."""
    copie = os.path.join(dossier_local, f"{reseau}.zip")
    # Une archive coupée en cours de lecture échappe aux reprises de la session : trois
    # essais de plus, espacés de 5 puis 10 s.
    for essai in range(3):
        try:
            reponse = session.get(url, timeout=600)
            reponse.raise_for_status()
            break
        except (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
        ):
            if essai == 2:
                raise
            time.sleep(5 * (essai + 1))
    with open(copie, "wb") as fichier:
        fichier.write(reponse.content)
    notebookutils.fs.cp(
        f"file:{copie}", f"{racine}/Files/brut/gtfs/{jour}/{reseau}.zip"
    )
    return zipfile.ZipFile(io.BytesIO(reponse.content))


def table_gtfs(archive, nom, colonnes=None):
    """Un fichier du GTFS, tout en texte ; None s'il est absent (calendar.txt est facultatif)."""
    if nom not in archive.namelist():
        return None
    with archive.open(nom) as fichier:
        return pd.read_csv(
            fichier,
            dtype=str,
            encoding="utf-8-sig",
            usecols=(lambda c: c in colonnes) if colonnes else None,
        )


def colonne(df, nom, defaut=None):
    """Une colonne facultative du GTFS, ou une colonne remplie de defaut si le réseau ne la publie pas."""
    return (
        df[nom]
        if nom in df.columns
        else pd.Series(defaut, index=df.index, dtype="object")
    )


JOURS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def services_actifs(g, date):
    """Services qui roulent ce jour-là : calendar.txt, corrigé par calendar_dates.txt."""
    numero = date.strftime("%Y%m%d")
    actifs = set()
    if g["calendar"] is not None:
        c = g["calendar"]
        actifs = set(
            c.loc[
                (c["start_date"] <= numero)
                & (c["end_date"] >= numero)
                & (c[JOURS[date.weekday()]] == "1"),
                "service_id",
            ]
        )
    if g["calendar_dates"] is not None:
        d = g["calendar_dates"][g["calendar_dates"]["date"] == numero]
        actifs |= set(d.loc[d["exception_type"] == "1", "service_id"])
        actifs -= set(d.loc[d["exception_type"] == "2", "service_id"])
    return actifs


def mode(route_type):
    """Mode d'une ligne d'après le route_type GTFS, types étendus compris."""
    try:
        t = int(float(route_type))
    except (TypeError, ValueError):
        return "autre"
    base = {
        0: "tram",
        1: "metro",
        2: "train",
        3: "bus",
        4: "ferry",
        5: "tram",
        6: "telepherique",
        7: "funiculaire",
        11: "bus",
        12: "train",
    }
    etendu = {
        1: "train",
        2: "bus",
        4: "metro",
        7: "bus",
        9: "tram",
        10: "ferry",
        13: "telepherique",
        14: "funiculaire",
    }
    return base.get(t) or etendu.get(t // 100, "autre")


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


def boite(anneaux):
    """[lon_min, lat_min, lon_max, lat_max] du contour d'une commune."""
    sommets = np.concatenate(anneaux)
    return [*sommets.min(axis=0), *sommets.max(axis=0)]


# Rectangle qui entoure chaque commune : on ne teste le contour que des communes dont le
# rectangle contient le point.
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


def touche_la_zone(jeu):
    """Vrai si la couverture déclarée du jeu touche une commune, une intercommunalité, un département ou la région de la zone."""
    return any(
        str(z.get("insee")) in couverture_zone.get(z.get("type"), set())
        for z in jeu.get("covered_area") or []
    )


catalogue = session.get(CATALOGUE, timeout=300).json()
GTFS = {}
for jeu in catalogue:
    if jeu.get("type") != "public-transit" or not touche_la_zone(jeu):
        continue
    ressources = [
        r
        for r in jeu.get("resources", [])
        if r.get("format") == "GTFS" and r.get("is_available", True)
    ]
    if not ressources:
        print(f"Sans GTFS, écarté : {jeu['title']}")
        continue
    reseau = nom_court(jeu["title"])
    while reseau in GTFS:
        reseau += "_2"
    # Un jeu peut publier plusieurs GTFS (périodes, exports) : on prend le plus récent.
    GTFS[reseau] = max(ressources, key=lambda r: r.get("updated") or "")["url"]
GTFS.update(GTFS_NATIONAUX)
print(f"{len(GTFS)} réseaux : {', '.join(sorted(GTFS))}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

gtfs, erreurs = {}, []
for reseau, url in GTFS.items():
    try:
        archive = telecharger(reseau, url)
        g = {
            "stops": table_gtfs(archive, "stops.txt"),
            "routes": table_gtfs(archive, "routes.txt"),
            "trips": table_gtfs(
                archive, "trips.txt", ["trip_id", "route_id", "service_id"]
            ),
            "stop_times": table_gtfs(archive, "stop_times.txt", ["trip_id", "stop_id"]),
            "calendar": table_gtfs(archive, "calendar.txt"),
            "calendar_dates": table_gtfs(archive, "calendar_dates.txt"),
        }
        manquants = [
            nom for nom in ("stops", "routes", "trips", "stop_times") if g[nom] is None
        ]
        if manquants:
            raise ValueError(f"GTFS sans {', '.join(manquants)}")
        if g["stops"].empty or g["trips"].empty:
            print(f"{reseau} : GTFS publié sans arrêt ni course, écarté")
            continue
        if reseau in FILTRE_QUAIS:
            g["stop_times"] = g["stop_times"][
                g["stop_times"]["stop_id"].str.contains(
                    FILTRE_QUAIS[reseau], regex=False
                )
            ]
            g["trips"] = g["trips"][
                g["trips"]["trip_id"].isin(g["stop_times"]["trip_id"])
            ]
        gtfs[reseau] = g
        print(
            f"{reseau} : {len(g['stops'])} arrêts et quais, {len(g['routes'])} lignes, {len(g['trips'])} courses"
        )
    except Exception as e:
        erreurs.append(f"{reseau} : {e!r}")
        print(f"{reseau} écarté : {e!r}")
if not gtfs:
    raise RuntimeError("Aucun GTFS chargé : " + " ; ".join(erreurs))

aujourd_hui = dt.date.today()
mardis = [
    aujourd_hui + dt.timedelta(days=(1 - aujourd_hui.weekday()) % 7 + 7 * k)
    for k in range(SEMAINES)
]
courses = {
    m: sum(
        g["trips"]["service_id"].isin(services_actifs(g, m)).sum()
        for g in gtfs.values()
    )
    for m in mardis
}
jour_reference = max(mardis, key=courses.get)
print("Courses par mardi :", {m.isoformat(): int(n) for m, n in courses.items()})
print(f"Jour de référence : mardi {jour_reference.isoformat()}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def arrets_et_lignes(reseau, g):
    """Arrêts dédoublonnés d'un réseau et lignes qui s'y arrêtent, avec leurs passages du jour."""
    stops = g["stops"].copy()
    type_lieu = colonne(stops, "location_type", "0").fillna("0").replace("", "0")
    # Un quai (location_type 0) est rattaché à sa zone d'arrêt (location_type 1) si elle
    # existe ; sinon il forme un arrêt à lui seul.
    quais = stops[type_lieu == "0"].copy()
    zones_arret = stops[type_lieu == "1"].set_index("stop_id")
    parent = colonne(quais, "parent_station")
    quais["arret"] = parent.where(parent.isin(zones_arret.index), quais["stop_id"])

    # Identifiant de ligne : réseau, exploitant et nom commercial, pour qu'une ligne ne
    # compte qu'une fois quels que soient ses variantes et ses sens.
    routes = g["routes"].copy()
    routes["ligne"] = colonne(routes, "route_short_name", "").fillna("").str.strip()
    exploitant = colonne(routes, "agency_id", "").fillna("")
    connu = (routes["ligne"] != "") & (routes["ligne"].str.upper() != "INCONNU")
    routes["ligne_id"] = np.where(
        connu,
        reseau + ":" + exploitant + ":" + routes["ligne"],
        reseau + ":" + routes["route_id"],
    )
    routes["libelle"] = colonne(routes, "route_long_name")
    routes["couleur"] = colonne(routes, "route_color")
    routes["mode"] = routes["route_type"].map(mode)

    passages = g["stop_times"].merge(g["trips"], on="trip_id")
    passages["arret"] = passages["stop_id"].map(quais.set_index("stop_id")["arret"])
    passages["ligne_id"] = passages["route_id"].map(
        routes.set_index("route_id")["ligne_id"]
    )
    passages = passages.dropna(subset=["arret", "ligne_id"])
    du_jour = passages[passages["service_id"].isin(services_actifs(g, jour_reference))]
    lignes = (
        passages[["arret", "ligne_id"]]
        .drop_duplicates()
        .merge(
            du_jour.groupby(["arret", "ligne_id"])["trip_id"]
            .nunique()
            .rename("passages_jour")
            .reset_index(),
            on=["arret", "ligne_id"],
            how="left",
        )
    )
    lignes["passages_jour"] = lignes["passages_jour"].fillna(0).astype("int64")
    attributs = routes.drop_duplicates("ligne_id").set_index("ligne_id")
    for champ in ("ligne", "libelle", "mode", "couleur"):
        lignes[champ] = lignes["ligne_id"].map(attributs[champ])
    lignes["reseau"] = reseau
    lignes["arret_id"] = reseau + ":" + lignes.pop("arret")

    # L'arrêt prend le nom et la position de sa zone d'arrêt, ou de son quai s'il est seul.
    arrets = quais.groupby("arret").agg(
        nb_quais=("stop_id", "size"),
        nom=("stop_name", "first"),
        lat=("stop_lat", "first"),
        lon=("stop_lon", "first"),
    )
    connus = arrets.index.isin(zones_arret.index)
    for champ, source in (
        ("nom", "stop_name"),
        ("lat", "stop_lat"),
        ("lon", "stop_lon"),
    ):
        arrets.loc[connus, champ] = zones_arret.loc[
            arrets.index[connus], source
        ].to_numpy()
    arrets = arrets.reset_index()
    arrets["arret_id"] = reseau + ":" + arrets.pop("arret")
    arrets["reseau"] = reseau
    arrets[["lat", "lon"]] = arrets[["lat", "lon"]].astype(float)
    # Seuls les arrêts desservis par au moins une ligne sont gardés.
    return arrets[arrets["arret_id"].isin(lignes["arret_id"])], lignes


tous_arrets, toutes_lignes = [], []
for reseau, g in gtfs.items():
    try:
        arrets_reseau, lignes_reseau = arrets_et_lignes(reseau, g)
        tous_arrets.append(arrets_reseau)
        toutes_lignes.append(lignes_reseau)
    except Exception as e:
        erreurs.append(f"{reseau} : {e!r}")
        print(f"{reseau} écarté : {e!r}")
arrets = placer(pd.concat(tous_arrets, ignore_index=True))
arrets_lignes = pd.concat(toutes_lignes, ignore_index=True)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def homonymes_proches(arrets, distance_m):
    """Zones d'arrêt d'un même réseau, au même nom et à moins de distance_m : un seul arrêt.

    Certains producteurs ne donnent pas de parent commun aux deux sens d'un arrêt. Renvoie
    {arret_id fusionné: arret_id gardé}, le gardé étant celui qui a le plus de quais.
    """
    representant = {}
    for _, groupe in arrets.groupby(["reseau", "nom"]):
        if len(groupe) < 2:
            continue
        groupe = groupe.sort_values("nb_quais", ascending=False)
        ids, xy = groupe["arret_id"].tolist(), groupe[["x_3035", "y_3035"]].to_numpy()
        chef = list(range(len(ids)))

        def trouver(i):
            while chef[i] != i:
                i = chef[i]
            return i

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if math.dist(xy[i], xy[j]) < distance_m:
                    a, b = trouver(i), trouver(j)
                    chef[max(a, b)] = min(a, b)
        representant.update(
            {ids[i]: ids[trouver(i)] for i in range(len(ids)) if trouver(i) != i}
        )
    return representant


representant = homonymes_proches(arrets, FUSION_M)
print(
    f"Second dédoublonnage : {len(representant)} zones d'arrêt fusionnées avec un homonyme à moins de {FUSION_M} m"
)
arrets["arret_id"] = arrets["arret_id"].replace(representant)
arrets = (
    arrets.sort_values("nb_quais", ascending=False)
    .groupby("arret_id", as_index=False, sort=False)
    .agg(
        reseau=("reseau", "first"),
        nom=("nom", "first"),
        nb_quais=("nb_quais", "sum"),
        lat=("lat", "first"),
        lon=("lon", "first"),
        x_3035=("x_3035", "first"),
        y_3035=("y_3035", "first"),
        idcar_200m=("idcar_200m", "first"),
    )
)
arrets_lignes["arret_id"] = arrets_lignes["arret_id"].replace(representant)
arrets_lignes = arrets_lignes.groupby(["arret_id", "ligne_id"], as_index=False).agg(
    reseau=("reseau", "first"),
    ligne=("ligne", "first"),
    libelle=("libelle", "first"),
    mode=("mode", "first"),
    couleur=("couleur", "first"),
    passages_jour=("passages_jour", "sum"),
)

arrets = garder_zone(arrets)
arrets_lignes = arrets_lignes[
    arrets_lignes["arret_id"].isin(arrets["arret_id"])
].reset_index(drop=True)
arrets_lignes["jour_reference"] = pd.Timestamp(jour_reference)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

resume = arrets_lignes.groupby("arret_id").agg(
    modes=("mode", lambda m: ",".join(sorted(set(m)))),
    nb_lignes=("ligne_id", "nunique"),
    passages_jour=("passages_jour", "sum"),
)
arrets = arrets.merge(resume, left_on="arret_id", right_index=True)
arrets = arrets[
    [
        "arret_id",
        "reseau",
        "nom",
        "modes",
        "nb_lignes",
        "passages_jour",
        "nb_quais",
        "dans_zone",
        "lat",
        "lon",
        "x_3035",
        "y_3035",
        "idcar_200m",
    ]
]
arrets_lignes = arrets_lignes[
    [
        "arret_id",
        "ligne_id",
        "reseau",
        "ligne",
        "libelle",
        "mode",
        "couleur",
        "passages_jour",
        "jour_reference",
    ]
]

# Contrôles : ils arrêtent le notebook si les tables n'ont pas la forme attendue.
assert arrets["arret_id"].is_unique
assert not arrets_lignes.duplicated(["arret_id", "ligne_id"]).any()
assert arrets_lignes["arret_id"].isin(arrets["arret_id"]).all()
ecrire("arrets", arrets)
ecrire("arrets_lignes", arrets_lignes)
print(
    arrets.groupby("reseau")
    .agg(
        arrets=("arret_id", "size"),
        dans_zone=("dans_zone", "sum"),
        quais=("nb_quais", "sum"),
    )
    .to_string()
)
print(
    arrets_lignes.groupby("mode")
    .agg(lignes=("ligne_id", "nunique"), passages=("passages_jour", "sum"))
    .to_string()
)
synchroniser_point_sql()
# Un réseau en échec est signalé après l'écriture : les tables gardent les autres, et
# l'exécution apparaît en échec dans le suivi.
if erreurs:
    raise RuntimeError("Réseaux en échec : " + " ; ".join(erreurs))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
