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

# # Collecte Citiz toutes les 10 minutes
#
# Relève l'état de toutes les voitures Citiz de France (flux GBFS `vehicle_status`) pour
# mesurer l'usage des stations pendant le hackathon et vérifier le score du modèle
# (décision 7). Le flux `station_status` n'est pas utilisé : une partie de ses relevés
# date de 2024, alors que `vehicle_status` suit les réservations en direct.
#
# Chaque passage garde le JSON brut dans `Files/brut/citiz/vehicle_status/<jour>/` et ajoute
# une ligne par voiture à la table `citiz_releves`. Le notebook est planifié toutes les
# 10 minutes jusqu'au mercredi 21 octobre au soir.

# CELL ********************

import datetime as dt

import notebookutils
import pandas as pd
import requests
from deltalake import write_deltalake
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Les 15 flux GBFS régionaux de Citiz publiés sur transport.data.gouv.fr. Ces adresses
# data.gouv.fr sont stables et redirigent vers le serveur de chaque réseau. La même liste
# sert au notebook 03_stations.
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

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

contexte = notebookutils.runtime.context
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "")
racine = f"abfss://{contexte['defaultLakehouseWorkspaceId']}@{endpoint}/{contexte['defaultLakehouseId']}"
acces = {
    "bearer_token": notebookutils.credentials.getToken("storage"),
    "use_fabric_endpoint": "true",
}

releve = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
dossier_brut = f"{racine}/Files/brut/citiz/vehicle_status/{releve:%Y-%m-%d}"


def adresse_flux(gbfs, nom):
    """Adresse d'un flux dans un gbfs.json, en GBFS 3.0 comme en 2.x."""
    donnees = gbfs["data"]
    flux = (
        donnees["feeds"]
        if "feeds" in donnees
        else next(iter(donnees.values()))["feeds"]
    )
    return next(f["url"] for f in flux if f["name"] == nom)


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
lignes, erreurs = [], []
for reseau, url in FLUX_CITIZ.items():
    try:
        reponse = session.get(
            adresse_flux(session.get(url, timeout=30).json(), "vehicle_status"),
            timeout=30,
        )
        reponse.raise_for_status()
        notebookutils.fs.put(
            f"{dossier_brut}/{releve:%H%M}_{reseau}.json", reponse.text, True
        )
        for v in reponse.json()["data"]["vehicles"]:
            lignes.append(
                {
                    "releve_utc": releve,
                    "reseau": reseau,
                    "vehicule_id": v.get("vehicle_id"),
                    "station_id": v.get("station_id"),
                    "station_rattachement_id": v.get("home_station_id"),
                    "reserve": bool(v.get("is_reserved")),
                    "desactive": bool(v.get("is_disabled")),
                    "dernier_signal": v.get("last_reported"),
                    "type_vehicule_id": v.get("vehicle_type_id"),
                    "carburant_pct": v.get("current_fuel_percent"),
                    "autonomie_m": v.get("current_range_meters"),
                    "lat": v.get("lat"),
                    "lon": v.get("lon"),
                }
            )
    except Exception as e:
        erreurs.append(f"{reseau} : {e!r}")

if not lignes:
    raise RuntimeError("Aucun flux Citiz n'a répondu : " + " ; ".join(erreurs))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************


def en_horodatage(valeurs):
    """GBFS 3.0 donne des dates ISO, GBFS 2.x des secondes depuis 1970 : tout passe en UTC."""
    numeriques = pd.to_numeric(valeurs, errors="coerce")
    if numeriques.notna().all():
        return pd.to_datetime(numeriques, unit="s", utc=True)
    return pd.to_datetime(valeurs, utc=True, format="ISO8601")


# Types fixés colonne par colonne : un passage où une colonne est vide ne doit pas
# changer le schéma de la table.
releves = pd.DataFrame(lignes)
releves["dernier_signal_utc"] = en_horodatage(releves.pop("dernier_signal"))
for colonne in ("releve_utc", "dernier_signal_utc"):
    releves[colonne] = pd.to_datetime(releves[colonne], utc=True).astype(
        "datetime64[us, UTC]"
    )
for colonne in (
    "reseau",
    "vehicule_id",
    "station_id",
    "station_rattachement_id",
    "type_vehicule_id",
):
    releves[colonne] = releves[colonne].astype("string")
for colonne in ("carburant_pct", "autonomie_m", "lat", "lon"):
    releves[colonne] = pd.to_numeric(releves[colonne], errors="coerce").astype(
        "float64"
    )

write_deltalake(
    f"{racine}/Tables/dbo/citiz_releves", releves, mode="append", storage_options=acces
)

print(
    f"{releve:%Y-%m-%d %H:%M} UTC : {len(releves)} voitures sur {releves['reseau'].nunique()} réseaux, "
    f"dont {int(releves['reserve'].sum())} réservées"
)
for erreur in erreurs:
    print("Flux en échec :", erreur)

# Le point SQL ne voit pas toujours seul les relevés ajoutés par deltalake : on le
# resynchronise, sans faire échouer la collecte s'il ne répond pas.
try:
    api = f"https://api.fabric.microsoft.com/v1/workspaces/{contexte['defaultLakehouseWorkspaceId']}"
    entete = {"Authorization": f"Bearer {notebookutils.credentials.getToken('pbi')}"}
    lakehouse = session.get(
        f"{api}/lakehouses/{contexte['defaultLakehouseId']}", headers=entete, timeout=60
    ).json()
    point_sql = lakehouse["properties"]["sqlEndpointProperties"]["id"]
    session.post(
        f"{api}/sqlEndpoints/{point_sql}/refreshMetadata",
        headers=entete,
        json={},
        timeout=120,
    ).raise_for_status()
    print("Point SQL resynchronisé")
except Exception as e:
    print(f"Point SQL non resynchronisé : {e!r}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
