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

# # Projets de transport annoncés
# 
# Charge les stations des projets de transport décidés dans la zone, pour montrer comment
# l'offre va changer et où Citiz complète ou double le futur réseau. Deux tables :
# 
# - `projets_arrets` : une ligne par station future, au même format que `arrets` et
#   `arrets_lignes` réunis (`arret_id`, `ligne_id`, mode, position, carreau), avec le projet,
#   l'année de mise en service annoncée et l'arrêt existant le plus proche à moins de 150 m
#   (`correspondance_arret_id`). On peut l'ajouter à `arrets_lignes` pour compter les options
#   d'un carreau après la mise en service.
# - `projets_lignes` : une ligne par projet, avec sa source.
# 
# Aucun réseau ne publie ses projets en données ouvertes : les stations et leurs
# coordonnées viennent de Wikidata (licence CC0). Deux sources :
# 
# - les projets vérifiés à la main dans `PROJETS`, avec les dates des annonces officielles.
#   Le prolongement de la ligne B garde l'identifiant de la ligne B existante (`ligne_id`
#   de Tisséo) : un carreau déjà proche de la ligne B ne gagne pas d'option ;
# - partout ailleurs, les stations de métro, de tram, de bus et de train que Wikidata
#   marque « en construction » en France, avec leur ligne et leur date d'ouverture quand
#   Wikidata les donne. C'est une liste tenue par des bénévoles, sans garantie d'être
#   complète ; un projet décidé mais pas encore en chantier n'y figure pas.
# 
# Les notebooks 01 et 02 doivent avoir tourné avant, avec le même jeu de valeurs.

# CELL ********************

import json
import math

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

# Réglages partagés par les notebooks : bibliothèque de variables de l'espace.
parametres = notebookutils.variableLibrary.getLibrary("parametres_mobilite")
LAKEHOUSE = parametres.lakehouse
RAYON_M = int(parametres.rayon_m)
WIKIDATA = "https://query.wikidata.org/sparql"
# Distance sous laquelle une station future est en correspondance avec un arrêt existant.
CORRESPONDANCE_M = 150
# Projets décidés : la ligne Wikidata et ses stations (toutes, ou la liste des nouvelles
# stations pour un prolongement), le mode, l'année annoncée et la source de l'annonce.
PROJETS = [
    {
        "projet": "ligne_c",
        "nom": "Ligne C du métro de Toulouse",
        "ligne": "C",
        "wikidata": "Q110876443",
        "stations": None,
        "mode": "metro",
        "annee_mise_en_service": 2028,
        "ligne_existante": None,
        "source": "Wikidata Q110876443 ; Ville de Toulouse : 27 km, 21 stations, mise en service fin 2028",
    },
    {
        "projet": "connexion_ligne_b",
        "nom": "Prolongement de la ligne B jusqu'à Labège",
        "ligne": "B",
        "wikidata": "Q3239063",
        "stations": ["Q56309372", "Q56309366"],
        "mode": "metro",
        "annee_mise_en_service": 2028,
        "ligne_existante": ("tisseo", "B"),
        "source": "Wikidata Q56309372 et Q56309366 ; Ville de Toulouse : 2,7 km jusqu'à Labège, chantier mené avec la ligne C",
    },
]
# Stations en construction ailleurs en France : la famille Wikidata donne le mode ; une
# station de métro est aussi une gare, d'où l'ordre de priorité.
FAMILLES_STATIONS = {
    "Q928830": "metro",
    "Q2175765": "tram",
    "Q55488": "train",
    "Q953806": "bus",
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
# Quatre essais espacés de 2, 4 puis 8 s ; Wikidata demande un User-Agent qui se présente.
session = requests.Session()
session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
        )
    ),
)
session.headers["User-Agent"] = (
    "hackathon-mobility/1.0 (Epitech, données ouvertes de mobilité)"
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


def stations_wikidata(projet):
    """Stations d'un projet dans Wikidata : nom et coordonnées."""
    if projet["stations"]:
        selection = (
            "VALUES ?station { "
            + " ".join(f"wd:{q}" for q in projet["stations"])
            + " }"
        )
    else:
        ligne = f"wd:{projet['wikidata']}"
        selection = (
            f"{{ ?station wdt:P81 {ligne} }} UNION {{ ?station wdt:P361 {ligne} }} "
            f"UNION {{ {ligne} wdt:P527 ?station }}"
        )
    requete = (
        f"SELECT ?station ?nom ?coord WHERE {{ {selection} ?station wdt:P625 ?coord . "
        f'OPTIONAL {{ ?station rdfs:label ?nom . FILTER(LANG(?nom) = "fr") }} }}'
    )
    lignes = []
    for r in sparql(requete):
        lon, lat = r["coord"]["value"].removeprefix("Point(").removesuffix(")").split()
        lignes.append(
            {
                "wikidata": r["station"]["value"].rsplit("/", 1)[-1],
                "nom": r.get("nom", {}).get("value"),
                "lat": float(lat),
                "lon": float(lon),
            }
        )
    return pd.DataFrame(lignes).drop_duplicates("wikidata")


def sparql(requete):
    """Résultats d'une requête SPARQL sur Wikidata."""
    reponse = session.get(
        WIKIDATA,
        params={"query": requete},
        headers={"Accept": "application/sparql-results+json"},
        timeout=120,
    )
    reponse.raise_for_status()
    return reponse.json()["results"]["bindings"]


def qid(r, champ):
    """Identifiant Wikidata (Q...) d'un champ de résultat, ou None."""
    return r[champ]["value"].rsplit("/", 1)[-1] if champ in r else None


def stations_en_construction():
    """Stations que Wikidata marque « en construction » en France, une ligne par station et par ligne."""
    familles = " ".join(f"wd:{q}" for q in FAMILLES_STATIONS)
    requete = f"""
    SELECT ?station ?nom ?coord ?famille ?ligne ?nom_ligne ?ouverture ?ouverture_ligne WHERE {{
      VALUES ?famille {{ {familles} }}
      ?station wdt:P17 wd:Q142 ; wdt:P5817 wd:Q12377751 ; wdt:P625 ?coord ;
               wdt:P31/wdt:P279* ?famille .
      OPTIONAL {{ ?station rdfs:label ?nom . FILTER(LANG(?nom) = "fr") }}
      OPTIONAL {{ ?station wdt:P729 ?ouverture }}
      OPTIONAL {{
        ?station wdt:P81 ?ligne .
        OPTIONAL {{ ?ligne rdfs:label ?nom_ligne . FILTER(LANG(?nom_ligne) = "fr") }}
        OPTIONAL {{ ?ligne wdt:P729 ?ouverture_ligne }}
      }}
    }}"""
    priorite = list(FAMILLES_STATIONS)
    lignes = []
    for r in sparql(requete):
        lon, lat = r["coord"]["value"].removeprefix("Point(").removesuffix(")").split()
        ouverture = (r.get("ouverture") or r.get("ouverture_ligne") or {}).get("value")
        lignes.append(
            {
                "wikidata": qid(r, "station"),
                "nom": r.get("nom", {}).get("value"),
                "rang": priorite.index(qid(r, "famille")),
                "ligne_wikidata": qid(r, "ligne"),
                "nom_ligne": r.get("nom_ligne", {}).get("value"),
                "annee_mise_en_service": int(ouverture[:4]) if ouverture else None,
                "lat": float(lat),
                "lon": float(lon),
            }
        )
    if not lignes:
        return pd.DataFrame()
    trouvees = (
        pd.DataFrame(lignes)
        .sort_values(["rang", "annee_mise_en_service"])
        .drop_duplicates(["wikidata", "ligne_wikidata"])
    )
    trouvees["mode"] = trouvees["rang"].map(lambda k: FAMILLES_STATIONS[priorite[k]])
    return trouvees.drop(columns="rang")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

lakehouse_id, point_sql_id = lakehouse_cible(LAKEHOUSE)
racine = f"abfss://{espace}@{endpoint}/{lakehouse_id}"

# La zone, écrite par 01_carreaux : ses communes (contours) et les centres de ses carreaux.
communes_zone = lire("zone_communes", ["contour_geojson"])
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

# Les arrêts existants : pour les correspondances, et pour reprendre l'identifiant d'une
# ligne existante qu'un projet prolonge.
arrets = lire("arrets", ["arret_id", "nom", "modes", "x_3035", "y_3035"])
arrets_lignes = lire(
    "arrets_lignes", ["ligne_id", "reseau", "ligne", "mode"]
).drop_duplicates()

stations, lignes = [], []
for projet in PROJETS:
    ligne_id = f"projet:{projet['projet']}"
    if projet["ligne_existante"]:
        reseau, nom_ligne = projet["ligne_existante"]
        existantes = arrets_lignes.loc[
            (arrets_lignes["reseau"] == reseau)
            & (arrets_lignes["ligne"] == nom_ligne)
            & (arrets_lignes["mode"] == projet["mode"]),
            "ligne_id",
        ].unique()
        if len(existantes) == 1:
            ligne_id = existantes[0]
        else:
            print(
                f"{projet['projet']} : ligne existante {reseau} {nom_ligne} introuvable, identifiant {ligne_id}"
            )
    s = stations_wikidata(projet)
    s["arret_id"] = f"projet_{projet['projet']}:" + s["wikidata"]
    s["ligne_id"] = ligne_id
    for champ in ("projet", "ligne", "mode", "annee_mise_en_service"):
        s[champ] = projet[champ]
    stations.append(s)
    lignes.append(
        {
            "ligne_id": ligne_id,
            "projet": projet["projet"],
            "nom": projet["nom"],
            "ligne": projet["ligne"],
            "mode": projet["mode"],
            "annee_mise_en_service": projet["annee_mise_en_service"],
            "nouvelle_ligne": projet["ligne_existante"] is None,
            "source": projet["source"],
        }
    )
    print(f"{projet['projet']} : {len(s)} stations dans Wikidata, ligne {ligne_id}")

# Ailleurs en France : les stations en construction de Wikidata, hors des projets vérifiés.
# Une station sans ligne connue forme son propre projet.
connues = set(pd.concat(stations)["wikidata"])
autres = stations_en_construction()
if not autres.empty:
    autres = autres[~autres["wikidata"].isin(connues)].copy()
    autres["projet"] = "wikidata_" + autres["ligne_wikidata"].fillna(autres["wikidata"])
    autres["ligne_id"] = "projet:" + autres["projet"]
    autres["arret_id"] = "projet_" + autres["projet"] + ":" + autres["wikidata"]
    autres["nom"] = autres["nom"].fillna(autres["wikidata"])
    autres["ligne"] = autres["nom_ligne"].fillna(autres["nom"])
    stations.append(autres.drop(columns=["ligne_wikidata", "nom_ligne"]))
    for projet, groupe in autres.groupby("projet"):
        lignes.append(
            {
                "ligne_id": f"projet:{projet}",
                "projet": projet,
                "nom": groupe["ligne"].iloc[0],
                "ligne": groupe["ligne"].iloc[0],
                "mode": groupe["mode"].iloc[0],
                "annee_mise_en_service": groupe["annee_mise_en_service"].min(),
                # Wikidata ne dit pas si la ligne existe déjà (prolongement) ou non.
                "nouvelle_ligne": None,
                "source": "Wikidata : stations en construction (P5817), ligne (P81), ouverture (P729)",
            }
        )
    print(
        f"Wikidata : {autres['wikidata'].nunique()} autres stations en construction en France, sur {autres['projet'].nunique()} projets"
    )

projets_arrets = garder_zone(placer(pd.concat(stations, ignore_index=True)))
projets_arrets["annee_mise_en_service"] = projets_arrets[
    "annee_mise_en_service"
].astype("Int64")


def correspondances(candidats):
    """Pour chaque station future, l'arrêt candidat le plus proche s'il est à moins de CORRESPONDANCE_M."""
    if candidats.empty:
        return np.full(len(projets_arrets), None, dtype=object)
    ecarts = np.hypot(
        projets_arrets["x_3035"].to_numpy()[:, None]
        - candidats["x_3035"].to_numpy()[None, :],
        projets_arrets["y_3035"].to_numpy()[:, None]
        - candidats["y_3035"].to_numpy()[None, :],
    )
    return np.where(
        ecarts.min(axis=1) <= CORRESPONDANCE_M,
        candidats["arret_id"].to_numpy()[ecarts.argmin(axis=1)],
        None,
    )


# Correspondance : d'abord avec un mode lourd (métro, tram, train, téléphérique), sinon avec
# n'importe quel arrêt.
lourds = arrets[arrets["modes"].str.contains("metro|tram|train|telepherique")]
projets_arrets["correspondance_arret_id"] = [
    lourd if lourd is not None else autre
    for lourd, autre in zip(correspondances(lourds), correspondances(arrets))
]
projets_arrets = projets_arrets[
    [
        "arret_id",
        "ligne_id",
        "projet",
        "nom",
        "ligne",
        "mode",
        "annee_mise_en_service",
        "correspondance_arret_id",
        "dans_zone",
        "lat",
        "lon",
        "x_3035",
        "y_3035",
        "idcar_200m",
        "wikidata",
    ]
]
projets_lignes = pd.DataFrame(lignes)
projets_lignes["nb_stations"] = (
    projets_lignes["projet"].map(projets_arrets.groupby("projet").size()).fillna(0)
)
projets_lignes["nb_stations"] = projets_lignes["nb_stations"].astype("int64")
# Seuls les projets qui ont une station dans la zone ou près.
projets_lignes = projets_lignes[projets_lignes["nb_stations"] > 0].reset_index(
    drop=True
)
projets_lignes = projets_lignes.astype(
    {"annee_mise_en_service": "Int64", "nouvelle_ligne": "boolean"}
)

# Contrôles : ils arrêtent le notebook si les tables n'ont pas la forme attendue.
assert projets_arrets["arret_id"].is_unique
assert projets_arrets["nom"].notna().all(), "station sans nom dans Wikidata"
ecrire("projets_arrets", projets_arrets)
ecrire("projets_lignes", projets_lignes)
print(projets_arrets[["projet", "nom", "correspondance_arret_id"]].to_string())
synchroniser_point_sql()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
