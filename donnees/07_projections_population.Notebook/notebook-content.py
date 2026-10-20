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

# # Projections de population (Omphale)
# 
# Charge les projections de population de l'INSEE par département, de 2018 à 2070, dans le
# scénario central, et construit la table `projections_population` : une ligne par
# département et par année, avec la population totale et trois grandes tranches d'âge
# (0-19 ans, 20-64 ans, 65 ans ou plus). Elle donne une tendance pour le pitch : le
# département gagne-t-il des habitants, vieillit-il ? Elle ne sert pas de variable au
# carreau : une projection départementale ne dit rien d'un quartier.
# 
# Source : Omphale 2022, dernière édition départementale de l'INSEE (totaux sur
# https://www.insee.fr/fr/statistiques/6652134, détail par âge sur
# https://www.insee.fr/fr/statistiques/7747107). Ses hypothèses datent de 2021 : les
# projections nationales publiées en juin 2026 prévoient moins de naissances (1,45 enfant
# par femme au lieu de 1,8), sans déclinaison par département à ce jour. La part des moins
# de 20 ans est donc sans doute surestimée à long terme.
# 
# Le Lakehouse où écrire vient de la bibliothèque de variables `parametres_mobilite`.

# CELL ********************

import importlib.util
import os
import subprocess
import sys
import tempfile
import time

import notebookutils
import pandas as pd
import requests
from deltalake import DeltaTable, write_deltalake
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if importlib.util.find_spec("openpyxl") is None:  # lu par pandas pour les .xlsx
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True
    )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Réglages partagés par les notebooks : bibliothèque de variables de l'espace.
parametres = notebookutils.variableLibrary.getLibrary("parametres_mobilite")
LAKEHOUSE = parametres.lakehouse
RETELECHARGER = str(parametres.retelecharger_insee).lower() == "true"
URL_TOTAUX = "https://www.insee.fr/fr/statistiques/fichier/6652134/projections_scenario_central.xlsx"
URL_DETAIL = (
    "https://www.insee.fr/fr/statistiques/fichier/7747107/donnees_det_Central.xlsx"
)
# Grandes tranches d'âge : bornes [début, fin[ des âges, sur les tranches de 5 ans de l'INSEE.
TRANCHES = {
    "population_0_19": (0, 20),
    "population_20_64": (20, 65),
    "population_65_plus": (65, 200),
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


def source(url, chemin):
    """Copie locale d'un classeur de l'INSEE, gardée brute dans Files/ ; relue pour vérifier qu'il est complet.

    Le site de l'INSEE coupe parfois un téléchargement sans le signaler : un classeur
    illisible est retéléchargé, jusqu'à trois fois.
    """
    distant = f"{racine}/Files/{chemin}"
    copie = os.path.join(dossier_local, os.path.basename(chemin))
    if not RETELECHARGER and notebookutils.fs.exists(distant):
        notebookutils.fs.cp(distant, f"file:{copie}")
        pd.ExcelFile(copie)
        return copie
    for essai in range(3):
        try:
            with session.get(
                url, stream=True, timeout=600, headers={"User-Agent": "Mozilla/5.0"}
            ) as reponse:
                reponse.raise_for_status()
                with open(copie, "wb") as fichier:
                    for bloc in reponse.iter_content(chunk_size=1 << 20):
                        fichier.write(bloc)
            pd.ExcelFile(copie)
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

# Totaux par département, en milliers d'habitants : ils donnent le code du département.
totaux = pd.read_excel(
    source(URL_TOTAUX, "brut/insee/projections_scenario_central.xlsx"),
    sheet_name="Population_DEP",
    header=5,
    dtype={"DEP": str},
)
# Détail par sexe et tranche de 5 ans, en habitants arrondis à la dizaine. Il nomme les
# départements sans les coder : on les code par leur libellé, le même dans les deux fichiers.
detail = pd.read_excel(
    source(URL_DETAIL, "brut/insee/donnees_det_Central.xlsx"),
    sheet_name="Population",
    header=5,
)
detail = detail.merge(
    totaux[["DEP", "LIBDEP"]], left_on="ZONE", right_on="LIBDEP", validate="many_to_one"
)
long = detail.melt(
    id_vars=["DEP", "LIBDEP", "TRAGE"],
    value_vars=[c for c in detail.columns if str(c).startswith("POP_")],
    var_name="annee",
    value_name="habitants",
)
long["annee"] = long["annee"].str.removeprefix("POP_").astype(int)
age_min = long["TRAGE"].str.extract(r"\[(\d+);")[0].astype(int)
long["tranche"] = None
for nom, (debut, fin) in TRANCHES.items():
    long.loc[age_min.between(debut, fin - 1), "tranche"] = nom
assert long["tranche"].notna().all(), "tranche d'âge inconnue dans le fichier INSEE"

projections = long.pivot_table(
    index=["DEP", "LIBDEP", "annee"],
    columns="tranche",
    values="habitants",
    aggfunc="sum",
).reset_index()
projections.columns.name = None
projections["population"] = projections[list(TRANCHES)].sum(axis=1)
regions = {
    d["code"]: d["codeRegion"]
    for d in session.get("https://geo.api.gouv.fr/departements", timeout=120).json()
}
projections["code_region"] = projections["DEP"].map(regions)
projections = projections.rename(
    columns={"DEP": "code_departement", "LIBDEP": "departement"}
)[
    [
        "code_departement",
        "departement",
        "code_region",
        "annee",
        "population",
        *TRANCHES,
    ]
]
for colonne in ["population", *TRANCHES]:
    projections[colonne] = projections[colonne].round().astype("int64")

# Contrôles : 101 départements de 2018 à 2070, et le détail retombe sur les totaux publiés.
assert len(projections) == 101 * (2070 - 2018 + 1)
assert projections["code_region"].notna().all()
ecart = (
    projections.pivot(index="code_departement", columns="annee", values="population")
    / 1000
    - totaux.set_index("DEP")[[f"POP_{a}" for a in range(2018, 2071)]].set_axis(
        range(2018, 2071), axis=1
    )
).abs()
assert ecart.max().max() <= 1, (
    f"détail et totaux s'écartent de {ecart.max().max():.1f} millier"
)
ecrire("projections_population", projections)
synchroniser_point_sql()

# Évolution des départements de la zone, écrite par 01_carreaux.
zone = DeltaTable(
    f"{racine}/Tables/dbo/zone_communes", storage_options=acces
).to_pandas(columns=["code_departement"])
evolution = projections[
    projections["code_departement"].isin(zone["code_departement"])
    & projections["annee"].isin([2021, 2030, 2040])
].pivot(index="departement", columns="annee", values="population")
evolution["2021-2040"] = (evolution[2040] / evolution[2021] - 1).map("{:+.1%}".format)
print(evolution.sort_values(2021, ascending=False).head(15).to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
