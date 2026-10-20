"""Ce que les voitures partagées changent pour la ville et pour les ménages.

Effets par voiture partagée : enquête nationale sur l'autopartage de l'ADEME et de 6t (2022), la
plus récente. Ce sont des fourchettes (bas, haut) et on les affiche comme telles. Émissions :
ADEME Base Empreinte, voiture moyenne du parc sur tout son cycle de vie.

Effets sociaux : calculés sur les carreaux nouvellement desservis par le scénario, avec les
données de MSc 1 (ménages sans voiture par IRIS, niveau de vie Filosofi, logements sociaux).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VOITURES_REMPLACEES = (4.6, 7.9)  # voitures personnelles par voiture en boucle, ADEME 2022 p. 77
PLACES_LIBEREES = (0.9, 3.0)  # places de stationnement en voirie par voiture partagée, p. 79
KM_EVITES = (10_000, 19_000)  # km en voiture évités par voiture partagée et par an, p. 83
CO2_KG_KM = 0.256  # kg CO2e par km, voiture moyenne du parc (Base Empreinte, identifiant 43791)
M2_PAR_PLACE = 10  # surface d'une place en voirie (étude Adetec, Banque des Territoires, 2023)


def environnement(voitures_partagees: float) -> dict[str, tuple[float, float]]:
    """Fourchettes (bas, haut) pour un nombre de voitures partagées ajoutées."""
    v = float(voitures_partagees)
    km = tuple(v * k for k in KM_EVITES)
    places = tuple(v * p for p in PLACES_LIBEREES)
    return {
        "voitures_en_moins": tuple(v * r for r in VOITURES_REMPLACEES),
        "places_liberees": places,
        "m2_liberes": tuple(p * M2_PAR_PLACE for p in places),
        "km_evites": km,
        "tonnes_co2_evitees": tuple(k * CO2_KG_KM / 1000 for k in km),
    }


def mediane_ponderee(valeurs, poids) -> float:
    """Médiane des habitants (et non des carreaux) : la moitié des habitants est en dessous."""
    v, w = np.asarray(valeurs, dtype=float), np.asarray(poids, dtype=float)
    garde = ~np.isnan(v) & (w > 0)
    v, w = v[garde], w[garde]
    ordre = np.argsort(v)
    cumul = np.cumsum(w[ordre])
    return float(v[ordre][np.searchsorted(cumul, cumul[-1] / 2)])


def social(carreaux: pd.DataFrame, idx_gagnes) -> dict[str, float]:
    """Qui gagne une station à 5 minutes : ménages sans voiture, quartiers modestes, logements sociaux.

    `idx_gagnes` : positions des carreaux nouvellement desservis dans `carreaux`. Une colonne
    absente donne une valeur manquante (NaN), jamais une erreur.
    """
    g = carreaux.iloc[np.unique(np.asarray(idx_gagnes, dtype=int))]
    sortie = {"habitants": float(g.population.sum()), "menages": float(g.get("menages", pd.Series(dtype=float)).sum())}
    if {"menages", "part_menages_sans_voiture"} <= set(g.columns):
        sortie["menages_sans_voiture"] = float((g.menages.fillna(0) * g.part_menages_sans_voiture.fillna(0)).sum())
    else:
        sortie["menages_sans_voiture"] = np.nan
    if "niveau_vie_moyen" in g.columns and g.population.sum() > 0:
        mediane = mediane_ponderee(carreaux.niveau_vie_moyen, carreaux.population)
        sortie["part_sous_mediane"] = float(g.population[g.niveau_vie_moyen < mediane].sum() / g.population.sum())
    else:
        sortie["part_sous_mediane"] = np.nan
    sortie["logements_sociaux"] = float(g.logements_sociaux.fillna(0).sum()) if "logements_sociaux" in g else np.nan
    return sortie
