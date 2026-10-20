"""Contrat d'interface : ce que l'optimisation lit chez les autres rôles, et sa vérification.

Les tables de MSc 1 sont lues telles qu'il les a écrites dans le Lakehouse (copie locale par
scripts/telecharger_lakehouse.py) : mêmes noms, mêmes colonnes, coordonnées en EPSG:3035.
Ce que MSc 2, MSc 3 et le MBA n'ont pas encore livré est remplacé, en attendant, par un
calcul provisoire, un score de 1 ou des coûts MOCK, et l'interface le dit. Le détail est
dans docs/CONTRAT.md.

Arborescence d'un dossier de données (config.toml) :
    msc1/   carreaux, zone_communes, arrets, arrets_lignes, stations_partagees,
            tisseo_routes, tisseo_trips, tisseo_shapes          (obligatoire)
    msc2/   accessibilite                                       (facultatif)
    msc3/   scores_potentiel                                    (facultatif)
    mba/    couts                                               (facultatif)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

TYPES = ("citiz", "velo", "bus")
BUDGETS = {"citiz": ("citiz",), "collectivite": ("velo", "bus")}
RACINE = Path(__file__).resolve().parent.parent
COUTS_MOCK = RACINE / "data" / "mock" / "MOCK_couts.parquet"

# nom de colonne -> type attendu ("str", "float", "int", "bool")
COLONNES = {
    # MSc 1 (notebooks 01_carreaux, 02_arrets, 03_stations)
    "carreaux": {
        "idcar_200m": "str", "codes_communes": "str", "x_3035": "float", "y_3035": "float",
        "lat": "float", "lon": "float", "population": "float",
    },
    "zone_communes": {"code_commune": "str", "nom": "str"},
    "arrets": {
        "arret_id": "str", "modes": "str", "nb_lignes": "int", "lat": "float", "lon": "float",
        "x_3035": "float", "y_3035": "float",
    },
    "arrets_lignes": {"arret_id": "str", "ligne_id": "str", "mode": "str"},
    "stations_partagees": {
        "station_id": "str", "operateur": "str", "type": "str", "lat": "float", "lon": "float",
        "x_3035": "float", "y_3035": "float",
    },
    "tisseo_routes": {"route_id": "str", "route_type": "str"},
    "tisseo_trips": {"route_id": "str", "shape_id": "str"},
    "tisseo_shapes": {"shape_id": "str", "shape_pt_lat": "float", "shape_pt_lon": "float", "shape_pt_sequence": "int"},
    # code et nom IRIS de chaque carreau (facultatif)
    "carreaux_variables": {"idcar_200m": "str", "code_iris": "str"},
    "iris": {"code_iris": "str", "nom_iris": "str"},
    # demande de Citiz : les arbres (une ligne par arbre), pour le critère « stationnement dégagé »
    "arbres": {},
    # MSc 2 : accessibilité par carreau (décisions 3 à 5) ; facultatif : iris, options_pour_1000
    # (la carte de chaleur de l'objectif 1)
    "accessibilite": {"idcar_200m": "str", "nb_options": "int", "sous_seuil": "bool"},
    # MSc 2 : population servie par chaque station existante (carte de l'objectif 2)
    "population_servie": {"station_id": "str", "population_servie": "float"},
    # MSc 3 : score de potentiel de chaque carreau sans station (décision 7)
    "scores_potentiel": {"idcar_200m": "str", "score_potentiel": "float"},
    # MBA : coût complet d'une station et par an, trois niveaux (classeur « Coût citiz.xlsx »)
    "couts": {"type": "str", "cout_bas": "float", "cout_defaut": "float", "cout_haut": "float", "budget": "str"},
}
FOURCHETTES = ("bas", "defaut", "haut")
# Ancien format (installation + 1 an de fonctionnement, deux niveaux), encore accepté.
ANCIEN_FORMAT_COUTS = ("cout_install_bas", "cout_install_haut", "cout_fonct_1an_bas", "cout_fonct_1an_haut")
TABLES = {
    "msc1": ("carreaux", "zone_communes", "arrets", "arrets_lignes", "stations_partagees",
             "tisseo_routes", "tisseo_trips", "tisseo_shapes", "carreaux_variables", "iris"),
    "msc2": ("accessibilite", "population_servie"),
    "msc3": ("scores_potentiel",),
    "mba": ("couts",),
    "citiz": ("arbres",),
}
FACULTATIVES_MSC1 = ("carreaux_variables", "iris")
# Emprise de la France métropolitaine en EPSG:3035 : au-delà, les coordonnées sont sûrement
# en degrés ou dans un autre système.
EMPRISE_3035 = (3_200_000, 2_000_000, 4_300_000, 3_200_000)


class ErreurContrat(ValueError):
    """Une table ne respecte pas le contrat ; le message dit quoi corriger."""


@dataclass
class Donnees:
    """Ce que consomme l'optimisation, une fois les tables de l'équipe assemblées.

    carreaux : idcar_200m, x_3035, y_3035, lat, lon, population, commune, iris (vide tant
        que MSc 2 ne l'a pas livré), a_option_citiz/velo/bus, nb_options_total, sous_seuil,
        score_citiz/velo/bus (score de l'emplacement, décision 7)
    stations : id, type (citiz, velo, bus), nom, x_3035, y_3035, lat, lon
    lignes_bus : id_ligne, ordre, x_3035, y_3035 (tracés des lignes de bus Tisséo)
    couts : indexé par type
    communes : code_commune, nom, contour_geojson (si MSc 1 l'a copié) ; arrets : la table de MSc 1
    population_servie : station_id, population_servie (carte de l'objectif 2 de MSc 2), ou None
    sources : d'où vient chaque brique ; provisoires : celles qui attendent un autre rôle
    """

    carreaux: pd.DataFrame
    stations: pd.DataFrame
    lignes_bus: pd.DataFrame
    couts: pd.DataFrame
    dossier: Path
    communes: pd.DataFrame | None = None
    arrets: pd.DataFrame | None = None  # tous les arrêts de MSc 1 (modes, nom), pour la carte
    population_servie: pd.DataFrame | None = None
    lecture: str = ""  # d'où et quand les données ont été lues
    sources: dict[str, str] = field(default_factory=dict)
    provisoires: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    @property
    def est_provisoire(self) -> bool:
        return bool(self.provisoires)


def _config() -> dict:
    with open(RACINE / "config.toml", "rb") as f:
        return tomllib.load(f)


def dossier_par_defaut() -> Path:
    """Le dossier de données : OPTIM_DONNEES, sinon config.toml."""
    chemin = Path(os.environ.get("OPTIM_DONNEES") or _config()["dossier_donnees"])
    return chemin if chemin.is_absolute() else RACINE / chemin


def source_par_defaut() -> str:
    """« fabric » (lecture en direct, copie locale en secours) ou « local » : OPTIM_SOURCE, sinon config.toml."""
    return os.environ.get("OPTIM_SOURCE") or _config().get("source", "local")


def lire(chemin: Path) -> pd.DataFrame:
    if chemin.suffix == ".parquet":
        return pd.read_parquet(chemin)
    return pd.read_csv(chemin, dtype=str)


def trouver(dossier: Path, sous_dossier: str, nom: str) -> Path | None:
    for extension in (".parquet", ".csv"):
        if (dossier / sous_dossier / f"{nom}{extension}").exists():
            return dossier / sous_dossier / f"{nom}{extension}"
    return None


def verifier_colonnes(nom: str, df: pd.DataFrame) -> pd.DataFrame:
    """Vérifie et convertit les colonnes obligatoires de la table `nom` ; garde les autres."""
    manquantes = [c for c in COLONNES[nom] if c not in df.columns]
    if manquantes:
        raise ErreurContrat(f"{nom} : colonnes manquantes {manquantes}")
    df = df.copy()
    for col, genre in COLONNES[nom].items():
        if genre != "str" and df[col].isna().any():
            raise ErreurContrat(f"{nom}.{col} : {int(df[col].isna().sum())} valeurs vides")
        try:
            if genre == "str":
                df[col] = df[col].astype("string").fillna("").astype(str)
            elif genre == "float":
                df[col] = pd.to_numeric(df[col]).astype(float)
            elif genre == "int":
                df[col] = pd.to_numeric(df[col]).astype(np.int64)
            elif genre == "bool":
                df[col] = _en_booleen(df[col])
        except (ValueError, TypeError) as e:
            raise ErreurContrat(f"{nom}.{col} : type {genre} attendu ({e})") from e
    return df


def _en_booleen(serie: pd.Series) -> pd.Series:
    if serie.dtype == bool:
        return serie
    texte = serie.astype(str).str.strip().str.lower()
    vrai, faux = {"true", "1", "vrai", "oui"}, {"false", "0", "faux", "non"}
    inconnues = set(texte) - vrai - faux
    if inconnues:
        raise ValueError(f"valeurs non booléennes {sorted(inconnues)[:5]}")
    return texte.isin(vrai)


def verifier_emprise(nom: str, df: pd.DataFrame) -> None:
    xmin, ymin, xmax, ymax = EMPRISE_3035
    dehors = ~(df.x_3035.between(xmin, xmax) & df.y_3035.between(ymin, ymax))
    if dehors.mean() > 0.01:
        raise ErreurContrat(f"{nom} : {int(dehors.sum())} points hors de France en EPSG:3035 (mètres)")


def charger_donnees(dossier: Path | str | None = None, source: str | None = None) -> Donnees:
    """Lit les données, les vérifie et les assemble.

    Avec la source « fabric », les tables sont lues en direct dans le Lakehouse, et la lecture
    réussie est gardée dans `dossier` ; si Fabric est injoignable, on repart de cette copie et
    on le signale. Avec « local », on lit seulement la copie.
    """
    dossier = Path(dossier) if dossier else dossier_par_defaut()
    if (source or source_par_defaut()) == "fabric":
        from . import fabric  # import tardif : deltalake et requests ne servent qu'ici

        try:
            tables, _ = fabric.lire(dossier)
        except fabric.FabricInjoignable as e:
            d = charger_local(dossier)
            d.avertissements.insert(0, f"Lecture en direct impossible ({e}) : affichage de {d.lecture}.")
            return d
        if "couts" not in tables:  # coûts importés d'un classeur local, s'il y en a
            chemin = trouver(dossier, "mba", "couts")
            if chemin is not None:
                tables["couts"] = lire(chemin)
        horodatage = dt.datetime.now().strftime("%d/%m/%Y à %H:%M")
        fabric.sauvegarder(tables, dossier, horodatage)
        d = depuis_tables(tables, dossier)
        d.lecture = f"données lues en direct sur Fabric le {horodatage}"
        return d
    return charger_local(dossier)


def charger_local(dossier: Path) -> Donnees:
    """Lit la copie locale des tables (dernière lecture de Fabric, ou dépôt à la main)."""
    tables = {}
    for sous_dossier, noms in TABLES.items():
        for nom in noms:
            chemin = trouver(dossier, sous_dossier, nom)
            if chemin is None and sous_dossier == "msc1" and nom not in FACULTATIVES_MSC1:
                raise ErreurContrat(f"{sous_dossier}/{nom} introuvable dans {dossier} : "
                                    "lancer scripts/telecharger_lakehouse.py")
            if chemin is not None:
                tables[nom] = lire(chemin)
    d = depuis_tables(tables, dossier)
    marque = dossier / "derniere_lecture.json"
    quand = json.loads(marque.read_text())["date"] if marque.exists() else "date inconnue"
    d.lecture = f"la copie locale des données (dernière lecture de Fabric : {quand})"
    return d


def depuis_tables(brut: dict[str, pd.DataFrame], dossier: Path | str = ".") -> Donnees:
    """Vérifie et assemble des tables déjà en mémoire (ex. lues par Spark dans Fabric).

    Les tables de MSc 1 sont obligatoires ; `accessibilite`, `scores_potentiel` et `couts`
    sont facultatives et remplacées, en leur absence, par leur version provisoire.
    """
    from .preparation import assembler  # import tardif : preparation importe ce module

    manquantes = [nom for nom in TABLES["msc1"] if nom not in brut and nom not in FACULTATIVES_MSC1]
    if manquantes:
        raise ErreurContrat(f"tables de MSc 1 manquantes {manquantes}")
    tables = {nom: verifier_colonnes(nom, df) for nom, df in brut.items() if nom in COLONNES and nom != "couts"}
    for nom in ("carreaux", "arrets", "stations_partagees"):
        verifier_emprise(nom, tables[nom])
    if tables["carreaux"].idcar_200m.duplicated().any():
        raise ErreurContrat("carreaux.idcar_200m : identifiants en double")
    if "scores_potentiel" in tables:
        s = tables["scores_potentiel"]
        if not s.score_potentiel.between(0, 1).all():
            raise ErreurContrat("scores_potentiel.score_potentiel : valeurs hors de [0, 1]")
        if s.idcar_200m.duplicated().any():
            raise ErreurContrat("scores_potentiel.idcar_200m : identifiants en double")
    tables["couts"] = completer_couts(brut.get("couts"))
    verifier_couts(tables["couts"])
    return assembler(tables, Path(dossier))


def completer_couts(livres: pd.DataFrame | None) -> pd.DataFrame:
    """Coûts livrés par le MBA, complétés par la ligne MOCK de chaque type qu'il n'a pas encore chiffré.

    La colonne `mock` dit, type par type, d'où vient le coût.
    """
    mock = verifier_colonnes("couts", pd.read_parquet(COUTS_MOCK)).assign(mock=True)
    if livres is None:
        return mock
    livres = livres.copy()
    if all(c in livres for c in ANCIEN_FORMAT_COUTS) and "cout_bas" not in livres:
        livres["cout_bas"] = livres.cout_install_bas + livres.cout_fonct_1an_bas
        livres["cout_haut"] = livres.cout_install_haut + livres.cout_fonct_1an_haut
        livres["cout_defaut"] = (livres.cout_bas + livres.cout_haut) / 2
    livres = verifier_colonnes("couts", livres).assign(mock=False)
    manquants = mock[~mock.type.isin(livres.type)]
    return pd.concat([livres, manquants], ignore_index=True)


def verifier_couts(couts: pd.DataFrame) -> None:
    if set(couts.type) != set(TYPES) or couts.type.duplicated().any():
        raise ErreurContrat(f"couts : une ligne par type attendue {TYPES}, reçu {list(couts.type)}")
    for t, budget in couts[["type", "budget"]].itertuples(index=False):
        if t not in BUDGETS.get(budget, ()):
            raise ErreurContrat(f"couts : le type {t} ne relève pas du budget {budget}")
    if ((couts.cout_bas > couts.cout_defaut) | (couts.cout_defaut > couts.cout_haut) | (couts.cout_bas <= 0)).any():
        raise ErreurContrat("couts : il faut 0 < cout_bas ≤ cout_defaut ≤ cout_haut")


def cout_station(couts: pd.DataFrame, type_: str, fourchette: str) -> float:
    """Coût complet d'une station et par an, niveau 'bas', 'defaut' ou 'haut'."""
    return float(couts.loc[type_, f"cout_{fourchette}"])
