"""Lecture du classeur Excel des coûts (« Coût citiz.xlsx »).

Le classeur désigne lui-même la ligne à utiliser : « Coût annuel complet par station
(thermique ou hybride) », onglet Calcul, colonnes Bas / Défaut / Haut. On la cherche par son
libellé, pas par son numéro de ligne, pour qu'un ajout de ligne dans le classeur ne casse rien.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

LIBELLES = {
    False: "Coût annuel complet par station (thermique ou hybride)",
    True: "Coût annuel complet par station (électrique)",
}


class ErreurClasseur(ValueError):
    """Le classeur n'a pas la forme attendue."""


def lire_classeur(source: str | Path | bytes, nom: str = "", electrique: bool = False) -> pd.DataFrame:
    """Une ligne `citiz` au format de la table `couts` (coût complet d'une station et par an)."""
    fichier = io.BytesIO(source) if isinstance(source, bytes) else source
    calcul = pd.read_excel(fichier, sheet_name="Calcul", header=0)
    libelle = LIBELLES[electrique]
    ligne = calcul[calcul.iloc[:, 0].astype(str).str.strip() == libelle]
    if len(ligne) != 1:
        raise ErreurClasseur(f"ligne « {libelle} » introuvable dans l'onglet Calcul")
    ligne = ligne.iloc[0]
    bas, defaut, haut = (float(ligne[c]) for c in ("Bas", "Défaut", "Haut"))
    if not 0 < bas <= defaut <= haut:
        raise ErreurClasseur(f"valeurs incohérentes : bas {bas}, défaut {defaut}, haut {haut}")
    nom = nom or (Path(source).name if not isinstance(source, bytes) else "classeur")
    return pd.DataFrame([{"type": "citiz", "cout_bas": bas, "cout_defaut": defaut, "cout_haut": haut,
                          "budget": "citiz", "source": f"{nom}, « {libelle} »"}])
