"""Lecture des classeurs Excel des coûts du MBA (« Coût citiz.xlsx » et « Cout_bus_velo.xlsx »).

Chaque classeur désigne lui-même la ligne à utiliser, onglet Calcul, colonnes Bas / Défaut / Haut :
« Coût annuel complet par station (thermique ou hybride) » pour Citiz, « Coût annuel d'un arrêt
(investissement amorti) » et « Coût annuel complet d'une station de 10 vélos » pour la
collectivité. On la cherche par son libellé, pas par son numéro de ligne, pour qu'un ajout de
ligne dans le classeur ne casse rien.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

LIBELLES = {
    False: "Coût annuel complet par station (thermique ou hybride)",
    True: "Coût annuel complet par station (électrique)",
}
LIBELLES_COLLECTIVITE = {
    "bus": "Coût annuel d'un arrêt (investissement amorti)",
    "velo": "Coût annuel complet d'une station de 10 vélos",
}


class ErreurClasseur(ValueError):
    """Le classeur n'a pas la forme attendue."""


def _ligne(calcul: pd.DataFrame, libelle: str) -> tuple[float, float, float]:
    """Bas, défaut et haut de la ligne au libellé donné (apostrophes droites ou typographiques)."""
    libelles = calcul.iloc[:, 0].astype(str).str.strip().str.replace("’", "'")
    ligne = calcul[libelles == libelle]
    if len(ligne) != 1:
        raise ErreurClasseur(f"ligne « {libelle} » introuvable dans l'onglet Calcul")
    bas, defaut, haut = (float(ligne.iloc[0][c]) for c in ("Bas", "Défaut", "Haut"))
    if not 0 < bas <= defaut <= haut:
        raise ErreurClasseur(f"valeurs incohérentes : bas {bas}, défaut {defaut}, haut {haut}")
    return bas, defaut, haut


def _calcul(source: str | Path | bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(source) if isinstance(source, bytes) else source, sheet_name="Calcul", header=0)


def _nom(source: str | Path | bytes, nom: str) -> str:
    return nom or (Path(source).name if not isinstance(source, bytes) else "classeur")


def lire_classeur(source: str | Path | bytes, nom: str = "", electrique: bool = False) -> pd.DataFrame:
    """Une ligne `citiz` au format de la table `couts` (coût complet d'une station et par an)."""
    libelle = LIBELLES[electrique]
    bas, defaut, haut = _ligne(_calcul(source), libelle)
    return pd.DataFrame([{"type": "citiz", "cout_bas": bas, "cout_defaut": defaut, "cout_haut": haut,
                          "budget": "citiz", "source": f"{_nom(source, nom)}, « {libelle} »"}])


def lire_classeur_collectivite(source: str | Path | bytes, nom: str = "") -> pd.DataFrame:
    """Les lignes `velo` et `bus` au format de la table `couts`, depuis le classeur vélo et bus."""
    calcul = _calcul(source)
    lignes = []
    for type_, libelle in LIBELLES_COLLECTIVITE.items():
        bas, defaut, haut = _ligne(calcul, libelle)
        lignes.append({"type": type_, "cout_bas": bas, "cout_defaut": defaut, "cout_haut": haut,
                       "budget": "collectivite", "source": f"{_nom(source, nom)}, « {libelle} »"})
    return pd.DataFrame(lignes)
