"""Curseur équité : combien pèse un habitant selon l'offre de transport qu'il a déjà.

    poids = population × (1 + α × bonus)      bonus = 1 / (1 + nb_options_total)

Le score de potentiel n'entre pas ici : il appartient à l'emplacement, pas à l'habitant
(décision 7), et c'est le glouton qui l'applique au gain de chaque candidat.

Le bonus vaut 1 pour un carreau sans aucun transport à 400 m, 1/2 avec une option, 1/3
avec deux... Il est continu : pas d'effet de seuil entre 0 et 1 option. α va de 0
(efficacité pure, chaque habitant pèse pareil) à ALPHA_MAX (un habitant sans transport
pèse 4 fois plus qu'un habitant déjà très bien desservi).
"""

import numpy as np
import pandas as pd

ALPHA_MAX = 3.0


def bonus(nb_options_total) -> np.ndarray:
    return 1.0 / (1.0 + np.asarray(nb_options_total, dtype=float))


def poids(elements: pd.DataFrame, alpha: float) -> np.ndarray:
    """Poids d'un habitant nouvellement desservi, élément par élément."""
    if not 0 <= alpha <= ALPHA_MAX:
        raise ValueError(f"α doit être entre 0 et {ALPHA_MAX}")
    return elements.population.to_numpy() * (1.0 + alpha * bonus(elements.nb_options_total))
