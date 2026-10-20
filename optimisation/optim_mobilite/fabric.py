"""Lecture en direct du Lakehouse `Mobilite` (espace « Hackathon Mobi »), en lecture seule.

Chaque lecture prend la dernière version des tables : une mise à jour faite dans Fabric se
voit à la lecture suivante. Les tables s'ouvrent comme dans les notebooks de l'équipe
(`deltalake` sur `Tables/dbo/...`), avec le jeton du compte Azure CLI connecté (`az login`).

Lu à chaque fois :
- les tables du territoire et de l'offre : carreaux, zone_communes, arrets, arrets_lignes,
  stations_partagees, et le code IRIS des carreaux (carreaux_variables, iris) ;
- le tracé des lignes Tisséo, dans le GTFS brut le plus récent (Files/brut/gtfs/<jour>/),
  téléchargé seulement quand un nouveau jour apparaît ;
- dès qu'elles existent : accessibilite (ou acces_carreau, la carte de MSc 2), population_servie,
  le score de potentiel, la table couts ou un classeur de coûts déposé dans Files/mba/, et les
  tables de Citiz : arbres, criteres_citiz, places_candidates, usage_stations, scores_potentiel_v2.

Rien n'est jamais écrit dans Fabric.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
import requests
from deltalake import DeltaTable
from deltalake.exceptions import DeltaProtocolError, TableNotFoundError

from .couts_mba import ErreurClasseur, lire_classeur

ESPACE = "94ef609e-283d-424d-9252-6d83b219c77d"  # Hackathon Mobi
LAKEHOUSE = "e3b26cda-daa2-4b1c-8fe1-828c20b1b836"  # Mobilite
ONELAKE = "onelake.dfs.fabric.microsoft.com"

# nom dans le Lakehouse -> (nom dans le contrat, colonnes lues ; None = toutes)
OBLIGATOIRES = {
    "carreaux": ("carreaux", ["idcar_200m", "codes_communes", "a_cheval_limite", "x_3035", "y_3035", "lat", "lon",
                              "population", "valeurs_imputees", "menages", "niveau_vie_moyen", "part_menages_pauvres",
                              "logements_sociaux", "menages_1_personne", "menages_logement_collectif", "age_25_39"]),
    "zone_communes": ("zone_communes", ["code_commune", "nom", "contour_geojson"]),
    "arrets": ("arrets", None),
    "arrets_lignes": ("arrets_lignes", None),
    "stations_partagees": ("stations_partagees", None),
}
FACULTATIVES = {
    "carreaux_variables": ("carreaux_variables", ["idcar_200m", "code_iris", "part_menages_sans_voiture",
                                                  "voitures_par_menage", "commerces_alimentaires_5min", "sante_5min",
                                                  "enseignement_5min", "services_5min", "gares_5min"]),
    "iris": ("iris", ["code_iris", "nom_iris", "type_iris"]),
    "arbres": ("arbres", ["lat", "lon", "x_3035", "y_3035"]),  # demande de Citiz : une ligne par arbre
    "accessibilite": ("accessibilite", None),
    # la carte de MSc 2, livrée sous ce nom et avec ses propres noms de colonnes (RENOMMAGES)
    "acces_carreau": ("accessibilite", ["idcar_200m", "options", "grise", "options_1000_hab"]),
    "population_servie": ("population_servie", None),
    "scores_potentiel_msc3": ("scores_potentiel", ["idcar_200m", "score_potentiel"]),
    "scores_potentiel": ("scores_potentiel", ["idcar_200m", "score_potentiel"]),
    "scores_potentiel_v2": ("scores_v2", None),  # usage prévu et raisons du score (modèle v2)
    "criteres_citiz": ("criteres_citiz", None),  # les 8 critères de « l'emplacement idéal » de Citiz
    "places_candidates": ("places_candidates", None),  # une place de parking loin des arbres par carreau
    "usage_stations": ("usage_stations", None),  # occupation mesurée des stations Citiz existantes
    "couts": ("couts", None),
}
RENOMMAGES = {"acces_carreau": {"options": "nb_options", "grise": "sous_seuil", "options_1000_hab": "options_pour_1000"}}
# où ranger chaque table dans la copie locale (sous-dossiers de data/reel/)
RANGEMENT = {"accessibilite": "msc2", "population_servie": "msc2", "scores_potentiel": "msc3", "scores_v2": "msc3",
             "couts": "mba", "arbres": "citiz", "criteres_citiz": "citiz", "places_candidates": "citiz",
             "usage_stations": "citiz"}


class FabricInjoignable(RuntimeError):
    """Pas de jeton, pas de réseau ou Lakehouse inaccessible."""


def jeton(ressource: str = "https://storage.azure.com") -> str:
    """Jeton du compte `az` connecté ; jamais affiché."""
    try:
        sortie = subprocess.run(
            ["az", "account", "get-access-token", "--resource", ressource, "--query", "accessToken", "-o", "tsv"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise FabricInjoignable(f"Azure CLI indisponible ({e})") from e
    if sortie.returncode != 0 or not sortie.stdout.strip():
        raise FabricInjoignable("Azure CLI non connecté : lancer az login")
    return sortie.stdout.strip()


def _table(racine: str, nom: str, acces: dict, colonnes: list[str] | None) -> pd.DataFrame:
    """Une table Delta. Celles écrites par Spark avec des « deletion vectors » (que deltalake ne
    lit pas encore) passent par DuckDB, qui les lit directement sur OneLake. Des colonnes demandées
    absentes de la table sont simplement ignorées : le critère qui en dépend sera indisponible."""
    try:
        table = DeltaTable(f"{racine}/{nom}", storage_options=acces)
        if colonnes:
            presentes = {champ.name for champ in table.schema().fields}
            colonnes = [c for c in colonnes if c in presentes]
        return table.to_pandas(columns=colonnes)
    except DeltaProtocolError:
        import duckdb

        # sous WSL, le client HTTP de DuckDB ne trouve pas seul les certificats du système
        if Path("/etc/ssl/certs/ca-certificates.crt").exists():
            os.environ.setdefault("CURL_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")
        con = duckdb.connect()
        for extension in ("azure", "delta"):
            con.install_extension(extension)
            con.load_extension(extension)
        con.execute("SET azure_transport_option_type = 'curl'")
        # CREATE SECRET n'accepte pas de paramètre « ? » dans toutes les versions de DuckDB : le jeton est
        # écrit tel quel, après avoir vérifié qu'il n'est fait que de caractères de jeton (aucune injection)
        jeton_texte = acces["bearer_token"]
        if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", jeton_texte):
            raise FabricInjoignable("jeton de stockage inattendu")
        con.execute(f"CREATE SECRET onelake (TYPE azure, PROVIDER access_token, ACCESS_TOKEN '{jeton_texte}', "
                    "ACCOUNT_NAME 'onelake')")
        df = con.execute(f"SELECT * FROM delta_scan('{racine}/{nom}')").df()
        return df[[c for c in colonnes if c in df]] if colonnes else df


def _lister(dossier: str, entetes: dict) -> list[dict]:
    reponse = requests.get(f"https://{ONELAKE}/{ESPACE}",
                           params={"resource": "filesystem", "recursive": "false",
                                   "directory": f"{LAKEHOUSE}/{dossier}"},
                           headers=entetes, timeout=60)
    if reponse.status_code == 404:
        return []
    reponse.raise_for_status()
    return reponse.json().get("paths", [])


def _fichier(chemin: str, entetes: dict) -> bytes:
    reponse = requests.get(f"https://{ONELAKE}/{ESPACE}/{LAKEHOUSE}/{chemin}", headers=entetes, timeout=600)
    reponse.raise_for_status()
    return reponse.content


def _gtfs_tisseo(entetes: dict, cache: Path) -> dict[str, pd.DataFrame]:
    """routes, trips et shapes du GTFS Tisséo le plus récent ; retéléchargé seulement s'il a changé."""
    jours = sorted(p["name"].rsplit("/", 1)[-1] for p in _lister("Files/brut/gtfs", entetes)
                   if p.get("isDirectory") == "true")
    if not jours:
        raise FabricInjoignable("aucun GTFS dans Files/brut/gtfs")
    jour = jours[-1]
    marque = cache / "tisseo_jour.txt"
    if marque.exists() and marque.read_text().strip() == jour and all(
            (cache / f"tisseo_{n}.parquet").exists() for n in ("routes", "trips", "shapes")):
        return {f"tisseo_{n}": pd.read_parquet(cache / f"tisseo_{n}.parquet") for n in ("routes", "trips", "shapes")}
    colonnes = {"routes": ["route_id", "route_short_name", "route_type"],
                "trips": ["route_id", "trip_id", "shape_id"], "shapes": None}
    tables = {}
    with zipfile.ZipFile(io.BytesIO(_fichier(f"Files/brut/gtfs/{jour}/tisseo.zip", entetes))) as archive:
        for nom, cols in colonnes.items():
            with archive.open(f"{nom}.txt") as f:
                tables[f"tisseo_{nom}"] = pd.read_csv(f, dtype=str, encoding="utf-8-sig",
                                                      usecols=(lambda c: c in cols) if cols else None)
    cache.mkdir(parents=True, exist_ok=True)
    for nom, df in tables.items():
        df.to_parquet(cache / f"{nom}.parquet", index=False)
    marque.write_text(jour)
    return tables


def _classeur_couts(entetes: dict) -> pd.DataFrame | None:
    """Le classeur de coûts le plus récent déposé dans Files/mba/, s'il y en a un."""
    classeurs = [p for p in _lister("Files/mba", entetes) if p["name"].lower().endswith(".xlsx")]
    if not classeurs:
        return None
    dernier = max(classeurs, key=lambda p: p.get("lastModified", ""))
    nom = dernier["name"].rsplit("/", 1)[-1]
    try:
        return lire_classeur(_fichier(f"Files/mba/{nom}", entetes), nom=nom)
    except ErreurClasseur:
        return None


def lire(cache: Path, jeton_stockage: str | None = None) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Toutes les tables utiles, lues en direct. Renvoie (tables, noms des livraisons trouvées).

    Hors de Fabric, le jeton vient d'Azure CLI ; dans un notebook Fabric, on passe
    `notebookutils.credentials.getToken("storage")`.
    """
    j = jeton_stockage or jeton()
    acces = {"bearer_token": j, "use_fabric_endpoint": "true"}
    entetes = {"Authorization": f"Bearer {j}", "x-ms-version": "2023-11-03"}
    racine = f"abfss://{ESPACE}@{ONELAKE}/{LAKEHOUSE}/Tables/dbo"
    tables, trouvees = {}, []
    try:
        for nom, (cle, colonnes) in OBLIGATOIRES.items():
            tables[cle] = _table(racine, nom, acces, colonnes)
        for nom, (cle, colonnes) in FACULTATIVES.items():
            if cle in tables:
                continue
            try:
                tables[cle] = _table(racine, nom, acces, colonnes).rename(columns=RENOMMAGES.get(nom, {}))
            except TableNotFoundError:
                continue
            trouvees.append(nom)
        tables.update(_gtfs_tisseo(entetes, cache / "msc1"))
        if "couts" not in tables:
            classeur = _classeur_couts(entetes)
            if classeur is not None:
                tables["couts"] = classeur
                trouvees.append("Files/mba")
    except FabricInjoignable:
        raise
    except Exception as e:  # réseau, droits, jeton expiré...
        raise FabricInjoignable(f"{type(e).__name__} : {e}") from e
    return tables, trouvees


def sauvegarder(tables: dict[str, pd.DataFrame], dossier: Path, horodatage: str) -> None:
    """Copie locale de la dernière lecture réussie : le secours si Fabric devient injoignable."""
    for cle, df in tables.items():
        sous = RANGEMENT.get(cle, "msc1")
        (dossier / sous).mkdir(parents=True, exist_ok=True)
        df.to_parquet(dossier / sous / f"{cle}.parquet", index=False)
    (dossier / "derniere_lecture.json").write_text(json.dumps({"date": horodatage, "source": "Fabric"}))
