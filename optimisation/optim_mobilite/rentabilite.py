"""Ce que rapporte une station Citiz, à partir de l'usage réel de ses voitures.

Citiz ne publie pas les recettes de ses stations. On connaît en revanche ce que rapporte une voiture
Citiz en Occitanie, et l'occupation de chacune de ses voitures, relevée toutes les 10 minutes dans le
flux GBFS (table `citiz_releves`). On répartit donc la recette réelle selon l'usage :

    recette d'une voiture = recette moyenne × occupation de la voiture / occupation moyenne

Une voiture occupée comme la moyenne du réseau rapporte la moyenne, 10 000 € par an (repère du
classeur du MBA : 2 M€ pour 200 voitures en 2024 ; le chiffre d'affaires 2025, 2 376 658 € pour
220 à 255 voitures, donne 9 300 à 10 800 €) ; chaque point d'occupation vaut environ 350 € par
voiture et par an.

Le résultat d'une station compare cette recette au coût complet annuel du MBA (amortissements
compris) ; le délai de retour divise l'investissement d'ouverture par ce que la station dégage
chaque année avant amortissements. Investissement et amortissements viennent du classeur du MBA
(« Coût citiz (2).xlsx », onglet Calcul) : à reporter ici si le classeur change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contrat import FOURCHETTES

RECETTE_VOITURE = 10_000  # € par voiture et par an : Citiz Occitanie, 2 M€ pour 200 voitures (repère R1 du MBA)
OCCUPATION_RESEAU = 0.285  # occupation mesurée des 255 voitures du réseau occitan, pondérée par voiture
VOITURES_PAR_STATION = 2  # « 2 voitures pour que le service soit attractif » (convention Citiz)

# recette annuelle d'une voiture à partir de laquelle elle est rentable, selon Citiz (700 à 900 € par mois)
SEUIL_CITIZ = {"bas": 8_400, "defaut": 9_600, "haut": 10_800}
# investissement d'ouverture d'une station de 2 voitures (place, boîtiers, voitures) : « Total investissement »
INVESTISSEMENT = {"bas": 32_000, "defaut": 58_180, "haut": 62_200}
# amortissements annuels compris dans le coût complet : 2 voitures et 2 boîtiers sur 5 ans, aménagement
AMORTISSEMENTS = {"bas": 6_400, "defaut": 11_636, "haut": 12_440}


def recette_voiture(occupation) -> np.ndarray:
    """Recette annuelle d'une voiture selon son occupation (part du temps où elle est réservée)."""
    return RECETTE_VOITURE * np.asarray(occupation, dtype=float) / OCCUPATION_RESEAU


def occupation_equilibre(cout_annuel: float, voitures: int = VOITURES_PAR_STATION) -> float:
    """Occupation à partir de laquelle la recette couvre le coût complet de la station."""
    return cout_annuel / (voitures * RECETTE_VOITURE) * OCCUPATION_RESEAU


def comptes(occupation, cout_annuel: float, fourchette: str = "defaut",
            voitures: int = VOITURES_PAR_STATION) -> pd.DataFrame:
    """Le compte annuel de chaque station : recette, résultat, flux avant amortissements, délai de retour.

    `occupation` donne une valeur par station ; `cout_annuel` est le coût complet d'une station
    (table `couts`, même fourchette). Une station qui ne dégage rien n'est jamais remboursée :
    son délai vaut l'infini.
    """
    if fourchette not in FOURCHETTES:
        raise ValueError(f"fourchette inconnue : {fourchette}")
    occupation = np.atleast_1d(np.asarray(occupation, dtype=float))
    recette = voitures * recette_voiture(occupation)
    resultat = recette - cout_annuel
    flux = resultat + AMORTISSEMENTS[fourchette]
    with np.errstate(divide="ignore"):
        delai = np.where(flux > 0, INVESTISSEMENT[fourchette] / np.where(flux > 0, flux, 1), np.inf)
    return pd.DataFrame({"occupation": occupation, "recette": recette, "resultat": resultat, "flux": flux,
                         "delai_ans": delai, "rentable": resultat >= 0})


def tresorerie(flux_par_station, fourchette: str = "defaut", annees: int = 6) -> pd.DataFrame:
    """Trésorerie cumulée d'un plan où toutes les stations ouvrent l'année 0 : la courbe du point mort."""
    flux = float(np.sum(flux_par_station))
    depart = -INVESTISSEMENT[fourchette] * len(np.atleast_1d(flux_par_station))
    return pd.DataFrame({"annee": np.arange(annees + 1), "cumul": depart + flux * np.arange(annees + 1)})
