"""Les 8 critères de « l'emplacement idéal » de Citiz, mesurés sur chaque carreau habité.

Le calcul est fait dans Fabric par le notebook 08_criteres_citiz, qui écrit deux tables :

- `criteres_citiz` : une ligne par carreau (`idcar_200m`). Pour chaque critère, sa valeur brute
  dans son unité et sa note de 0 à 100, le rang centile du carreau dans la zone (100 = le
  meilleur, retourné quand « moins = mieux ») ; quand un critère a deux valeurs brutes, sa note
  est la moyenne de leurs deux rangs. L'indice Citiz est la moyenne des 8 notes. Là où aucun
  inventaire ne recense les arbres, `arbres_mesures` est faux et la note des arbres vaut 50,
  la note neutre.
- `places_candidates` : dans un carreau sur quatre environ, une place précise, le point d'un
  parking public OpenStreetMap le plus éloigné des arbres (au moins 10 m), avec son adresse
  (Base adresse nationale). Là où les arbres ne sont pas mesurés, le plus grand parking public
  du carreau, sans distance aux arbres.

Ce module ne recalcule rien : il lit ces deux tables dans les données déjà chargées, les
vérifie, et prépare ce que le site affiche (le radar d'un carreau, sa place, la comparaison
avec les stations Citiz existantes).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

NOTE_NEUTRE = 50.0


@dataclass(frozen=True)
class Critere:
    cle: str
    libelle: str  # tel que Citiz l'écrit (présentation du 19/10/2026, « L'emplacement idéal »)
    colonne: str  # valeur brute principale dans criteres_citiz
    unite: str
    sens: str  # « croissant » : plus = mieux ; « decroissant » : moins = mieux (valeur brute principale)
    source: str  # d'où vient la valeur, en une ligne

    @property
    def colonne_note(self) -> str:
        return f"note_{self.cle}"


CRITERES: tuple[Critere, ...] = (
    Critere("transports", "Transports collectifs", "passages_jour_400m", "passages par jour", "croissant",
            "GTFS des réseaux (arrets_lignes) : passages par jour des lignes qui s'arrêtent à 400 m, chacune une fois"),
    Critere("densite", "Densité urbaine", "habitants_400m", "habitants", "croissant",
            "INSEE Filosofi 2021, carreaux de 200 m : habitants à moins de 400 m"),
    Critere("mixite", "Mixité habitat/activité", "equilibre_emplois_habitants", "0 à 1", "croissant",
            "Sirene (emplois) et BPE 2025 (équipements) à 400 m : équilibre emplois/habitants, et équipements"),
    Critere("accessibilite", "Accessibilité/circulation", "dist_route_m", "m", "decroissant",
            "OpenStreetMap : distance à la route principale (primary, secondary, tertiary) la plus proche"),
    Critere("stationnement", "Simple pour stationner", "parkings_200m", "parkings", "croissant",
            "OpenStreetMap : parkings publics à moins de 200 m, nombre et surface"),
    Critere("motorisation", "Taux de motorisation faible", "part_menages_sans_voiture", "part des ménages", "croissant",
            "Recensement 2023 par IRIS : part des ménages sans voiture"),
    Critere("visibilite", "Visible", "equipements_200m", "équipements", "croissant",
            "BPE 2025 à moins de 200 m, et distance à l'axe passant (OSM primary, secondary) le plus proche"),
    Critere("arbres", "Arbres à distance", "part_sans_arbre_10m", "part du carreau", "croissant",
            "Arbres de Toulouse Métropole (open data) et d'OpenStreetMap : part du carreau à plus de 10 m d'un arbre"),
)
COLONNES_CRITERES = ("idcar_200m", "indice_citiz", "arbres_mesures",
                     *(c.colonne_note for c in CRITERES), *(c.colonne for c in CRITERES))
COLONNES_PLACES = ("idcar_200m", "lat", "lon", "dist_arbre_m")


class ErreurCriteres(ValueError):
    """Une des deux tables ne respecte pas ce que le notebook 08_criteres_citiz écrit."""


@dataclass
class CriteresCitiz:
    """Les deux tables, vérifiées et indexées par `idcar_200m`."""

    criteres: pd.DataFrame
    places: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLONNES_PLACES[1:]))


def lire_criteres(tables: Mapping[str, pd.DataFrame]) -> CriteresCitiz | None:
    """Les critères Citiz pris dans les tables chargées (lecture Fabric ou copie locale).

    Renvoie None si `criteres_citiz` n'y est pas encore : le notebook n'a pas tourné, et le site
    n'affiche pas le mode « Critères Citiz ». `places_candidates` est facultative.
    """
    if tables.get("criteres_citiz") is None:
        return None
    criteres = _verifier(tables["criteres_citiz"], COLONNES_CRITERES, "criteres_citiz")
    notes = [c.colonne_note for c in CRITERES] + ["indice_citiz"]
    criteres[notes] = criteres[notes].apply(pd.to_numeric, errors="raise").astype(float)
    if criteres[notes].isna().any().any() or not criteres[notes].stack().between(0, 100).all():
        raise ErreurCriteres("criteres_citiz : notes vides ou hors de [0, 100]")
    criteres["arbres_mesures"] = criteres["arbres_mesures"].astype(bool)
    resultat = CriteresCitiz(criteres.set_index("idcar_200m"))
    if tables.get("places_candidates") is not None:
        places = _verifier(tables["places_candidates"], COLONNES_PLACES, "places_candidates")
        resultat.places = places.set_index("idcar_200m")
    return resultat


def lire_dossier(dossier: Path | str, sous_dossier: str = "citiz") -> CriteresCitiz | None:
    """Les critères depuis une copie locale (fichiers parquet `<dossier>/<sous_dossier>/<table>.parquet`)."""
    tables = {}
    for nom in ("criteres_citiz", "places_candidates"):
        chemin = Path(dossier) / sous_dossier / f"{nom}.parquet"
        if chemin.exists():
            tables[nom] = pd.read_parquet(chemin)
    return lire_criteres(tables)


def _verifier(df: pd.DataFrame, colonnes: tuple[str, ...], nom: str) -> pd.DataFrame:
    manquantes = [c for c in colonnes if c not in df.columns]
    if manquantes:
        raise ErreurCriteres(f"{nom} : colonnes manquantes {manquantes}")
    if df["idcar_200m"].duplicated().any():
        raise ErreurCriteres(f"{nom}.idcar_200m : identifiants en double")
    df = df.copy()
    df["idcar_200m"] = df["idcar_200m"].astype(str)
    return df


def notes_radar(donnees: CriteresCitiz, idcar: str) -> pd.DataFrame:
    """Les 8 notes d'un carreau, dans l'ordre de Citiz, prêtes pour un graphique en radar.

    Une ligne par critère : cle, libelle, note (0 à 100), valeur (brute, vide si inconnue), unite, mesure (faux
    pour les arbres hors des communes inventoriées : la note est alors la note neutre).
    KeyError si le carreau n'est pas dans la table.
    """
    if idcar not in donnees.criteres.index:
        raise KeyError(f"carreau {idcar} absent de criteres_citiz")
    ligne = donnees.criteres.loc[idcar]
    return pd.DataFrame([
        {
            "cle": c.cle,
            "libelle": c.libelle,
            "note": float(ligne[c.colonne_note]),
            "valeur": None if pd.isna(ligne[c.colonne]) else float(ligne[c.colonne]),
            "unite": c.unite,
            "mesure": bool(ligne["arbres_mesures"]) if c.cle == "arbres" else True,
        }
        for c in CRITERES
    ])


def place_du_carreau(donnees: CriteresCitiz, idcar: str) -> dict | None:
    """La place proposée dans un carreau (lat, lon, dist_arbre_m, adresse...), ou None s'il n'y en a pas."""
    if idcar not in donnees.places.index:
        return None
    place = donnees.places.loc[idcar]
    return {cle: (None if not isinstance(v, str) and pd.isna(v) else v) for cle, v in place.items()}


def place_la_plus_proche(donnees: CriteresCitiz, idcar: str, x: float, y: float, rayon: float = 300.0) -> dict | None:
    """La place du carreau ; à défaut, la place la plus proche de son centre (x, y en EPSG:3035) à moins
    de `rayon` mètres. `distance_centre_m` dit à quelle distance du centre du carreau elle se trouve."""
    place = place_du_carreau(donnees, idcar)
    if place is not None:
        return place | {"distance_centre_m": 0.0}
    p = donnees.places
    if not len(p) or not {"x_3035", "y_3035"} <= set(p.columns):
        return None
    d2 = (p.x_3035.astype(float) - x) ** 2 + (p.y_3035.astype(float) - y) ** 2
    proche = d2.idxmin()
    if d2[proche] > rayon ** 2:
        return None
    return place_du_carreau(donnees, proche) | {"distance_centre_m": float(np.sqrt(d2[proche]))}


def comparer_stations(donnees: CriteresCitiz) -> dict | None:
    """Indice moyen des carreaux qui ont déjà une station Citiz, contre celui des autres, et l'AUC :
    la probabilité qu'un carreau avec station ait un indice plus haut qu'un carreau sans (0,5 =
    le hasard). None si la table ne dit pas où sont les stations, ou s'il n'y a qu'un des deux cas."""
    c = donnees.criteres
    if "station_citiz" not in c:
        return None
    avec = c["station_citiz"].astype(bool).to_numpy()
    n1, n0 = int(avec.sum()), int((~avec).sum())
    if n1 == 0 or n0 == 0:
        return None
    rangs = c["indice_citiz"].rank(method="average").to_numpy()
    auc = (rangs[avec].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    return {
        "carreaux_avec_station": n1,
        "indice_avec_station": float(c.loc[avec, "indice_citiz"].mean()),
        "indice_sans_station": float(c.loc[~avec, "indice_citiz"].mean()),
        "auc": float(np.round(auc, 3)),
    }
