"""Candidats et couverture précalculée.

Le problème ne dépend ni du budget, ni de α, ni de la fourchette de coûts pour sa partie
géométrique : qui couvre qui se calcule une fois, puis chaque scénario ne change que des
poids (α) et des coûts. C'est ce qui rend les curseurs instantanés.

Vocabulaire du code :
- un **élément** est un couple (carreau, type) pas encore desservi pour ce type. Pour le
  budget collectivité, un même carreau donne deux éléments (vélo et bus) : un habitant qui
  gagne un vélo et un bus compte une fois pour chaque type, jamais deux fois pour le même ;
- un **candidat** est un couple (carreau, type) où l'on peut poser une station ; il porte le
  score de potentiel de son carreau (décision 7 : la valeur d'un emplacement est sa population
  nouvellement desservie × son score) ;
- la **matrice de couverture** A (creuse, candidats × éléments) vaut 1 si le centre de
  l'élément est à 400 m ou moins du candidat.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree

from .contrat import BUDGETS, Donnees

RAYON = 400.0
DEMI_DIAGONALE = 100 * np.sqrt(2)  # un point est dans un carreau s'il est à moins de ça de son centre
PAS_DENSIFICATION = 50.0  # m, pour ne sauter aucun carreau le long d'une ligne de bus


@dataclass
class Structure:
    """Tout ce qui ne change pas d'un scénario à l'autre pour un budget donné."""

    budget: str  # 'citiz' ou 'collectivite'
    types: tuple[str, ...]
    candidats: pd.DataFrame  # type, idx_carreau, score
    elements: pd.DataFrame  # type, idx_carreau, population, nb_options_total
    couverture: sparse.csr_matrix  # candidats × éléments


def carreaux_sur_lignes(carreaux: pd.DataFrame, lignes: pd.DataFrame) -> np.ndarray:
    """Indices des carreaux traversés par une ligne de bus existante.

    Chaque ligne (points ordonnés) est redécoupée tous les 50 m ; chaque point tombe dans
    le carreau dont le centre est le plus proche, s'il est à moins d'une demi-diagonale.
    """
    morceaux = []
    for _, ligne in lignes.groupby("id_ligne", sort=False):
        xy = ligne[["x_3035", "y_3035"]].to_numpy()
        if len(xy) < 2:
            morceaux.append(xy)
            continue
        longueurs = np.hypot(*np.diff(xy, axis=0).T)
        abscisses = np.concatenate([[0], np.cumsum(longueurs)])
        s = np.arange(0, abscisses[-1] + PAS_DENSIFICATION, PAS_DENSIFICATION).clip(max=abscisses[-1])
        morceaux.append(np.column_stack([np.interp(s, abscisses, xy[:, 0]), np.interp(s, abscisses, xy[:, 1])]))
    if not morceaux:
        return np.array([], dtype=np.int64)
    points = np.concatenate(morceaux)
    d, idx = cKDTree(carreaux[["x_3035", "y_3035"]].to_numpy()).query(points, distance_upper_bound=DEMI_DIAGONALE + 1e-6)
    return np.unique(idx[np.isfinite(d)])


def candidats_du_type(donnees: Donnees, type_: str) -> np.ndarray:
    """Carreaux où une station `type_` est envisageable.

    Habité, au-dessus du seuil de diffusion, sans station de ce type à 400 m ; pour le bus,
    en plus, traversé par une ligne existante.
    """
    c = donnees.carreaux
    masque = (c.population > 0) & ~c.sous_seuil & ~c[f"a_option_{type_}"]
    if type_ == "bus":
        sur_ligne = np.zeros(len(c), dtype=bool)
        sur_ligne[carreaux_sur_lignes(c, donnees.lignes_bus)] = True
        masque &= sur_ligne
    return np.flatnonzero(masque.to_numpy())


def construire(donnees: Donnees, budget: str, types: tuple[str, ...] | None = None) -> Structure:
    """Précalcule candidats, éléments et matrice de couverture pour un budget."""
    types = types or BUDGETS[budget]
    c = donnees.carreaux
    xy = c[["x_3035", "y_3035"]].to_numpy()
    arbre = cKDTree(xy)  # un seul index spatial pour tous les types

    candidats, elements, lignes, colonnes = [], [], [], []
    n_cand = n_elem = 0
    for t in types:
        # éléments : carreaux habités pas encore desservis pour ce type (sous le seuil compris :
        # leurs habitants comptent dans les totaux, ils ne sont simplement jamais montrés seuls)
        idx_elem = np.flatnonzero(((c.population > 0) & ~c[f"a_option_{t}"]).to_numpy())
        position = np.full(len(c), -1)
        position[idx_elem] = np.arange(idx_elem.size) + n_elem
        elements.append(
            pd.DataFrame(
                {
                    "type": t,
                    "idx_carreau": idx_elem,
                    "population": c.population.to_numpy()[idx_elem],
                    "nb_options_total": c.nb_options_total.to_numpy()[idx_elem],
                }
            )
        )

        idx_cand = candidats_du_type(donnees, t)
        candidats.append(pd.DataFrame({"type": t, "idx_carreau": idx_cand,
                                       "score": c[f"score_{t}"].to_numpy()[idx_cand]}))
        # la boule de 400 m autour de chaque candidat (le + 1e-6 garde la frontière : un carreau
        # à 400 m pile est dedans, comme le veut « cercle de 400 m »)
        voisins = arbre.query_ball_point(xy[idx_cand], RAYON + 1e-6) if idx_cand.size else []
        for i, v in enumerate(voisins):
            v = position[np.asarray(v, dtype=np.int64)]
            v = v[v >= 0]  # on ne garde que les voisins encore à desservir
            lignes.append(np.full(v.size, n_cand + i))
            colonnes.append(v)
        n_cand += idx_cand.size
        n_elem += idx_elem.size

    lignes = np.concatenate(lignes) if lignes else np.array([], dtype=np.int64)
    colonnes = np.concatenate(colonnes) if colonnes else np.array([], dtype=np.int64)
    couverture = sparse.csr_matrix(
        (np.ones(lignes.size, dtype=np.float64), (lignes, colonnes)), shape=(n_cand, n_elem)
    )
    couverture.sort_indices()
    return Structure(
        budget=budget,
        types=tuple(types),
        candidats=pd.concat(candidats, ignore_index=True),
        elements=pd.concat(elements, ignore_index=True),
        couverture=couverture,
    )


def restreindre(structure: Structure, garder: np.ndarray) -> Structure:
    """Même problème avec une partie des candidats seulement (ex. quelques communes).

    Les éléments ne changent pas : ceux qu'aucun candidat gardé ne couvre n'apportent rien.
    """
    garder = np.flatnonzero(garder)
    return Structure(
        budget=structure.budget,
        types=structure.types,
        candidats=structure.candidats.iloc[garder].reset_index(drop=True),
        elements=structure.elements,
        couverture=structure.couverture[garder],
    )
