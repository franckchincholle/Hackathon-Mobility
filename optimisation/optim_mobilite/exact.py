"""Version exacte : la couverture maximale sous budget en programme linéaire en nombres entiers.

Chaque habitant est rattaché à une seule station choisie (il ne compte qu'une fois) et vaut
le score de cette station (décision 7 : valeur = population nouvellement desservie × score
de l'emplacement) :

    maximiser   Σ_(i,e)  score_i × poids_e × y_ie
    sous        Σ_i y_ie ≤ 1              pour chaque élément e   (un habitant compté une fois)
                y_ie ≤ x_i                pour chaque lien (i, e)  (rattaché à une station posée)
                Σ_i coût_i × x_i ≤ budget                          (le budget)
                x_i ∈ {0, 1},  0 ≤ y_ie ≤ 1

Quand tous les scores sont égaux (score = 1 en attendant MSc 3), c'est exactement le
« Maximal Covering Location Problem » (Church et ReVelle, 1974) avec un budget, qu'on écrit
sous sa forme compacte :  y_e ≤ Σ_(i couvre e) x_i.

Le solveur (HiGHS, libre) trouve l'optimum, ou s'arrête au temps limite avec un
encadrement : on connaît alors une borne qu'aucune solution ne dépasse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pulp
from scipy import sparse


@dataclass
class SolutionExacte:
    candidats: list[int]
    valeur: float
    borne: float  # aucune solution ne fait mieux ; égale à valeur si l'optimum est prouvé
    statut: str
    secondes: float


def valeur_ensemble(couverture: sparse.csr_matrix, poids: np.ndarray, score: np.ndarray, choisis) -> float:
    """Valeur d'un ensemble de stations : chaque habitant compte une fois, au meilleur score."""
    meilleur = np.zeros(couverture.shape[1])
    for i in choisis:
        elems = couverture.indices[couverture.indptr[i] : couverture.indptr[i + 1]]
        meilleur[elems] = np.maximum(meilleur[elems], score[i])
    return float((poids * meilleur).sum())


def resoudre_exact(couverture: sparse.csr_matrix, poids: np.ndarray, couts: np.ndarray, budget: float,
                   score: np.ndarray | None = None, limite_secondes: float = 120,
                   ecart_relatif: float = 1e-4) -> SolutionExacte:
    debut = time.perf_counter()
    score = np.ones(couverture.shape[0]) if score is None else np.asarray(score, dtype=float)
    utiles = np.flatnonzero((couts <= budget) & (score > 0))  # trop cher ou sans valeur : inutile
    sous = couverture[utiles].tocoo()
    garder = poids[sous.col] > 0
    lignes, cols = sous.row[garder], sous.col[garder]

    modele = pulp.LpProblem("couverture_maximale_sous_budget", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in utiles]
    modele += pulp.lpSum(float(couts[i]) * x[j] for j, i in enumerate(utiles)) <= budget
    if np.allclose(score[utiles], score[utiles][0] if utiles.size else 1):
        # scores égaux : forme compacte, une variable par élément
        s = float(score[utiles][0]) if utiles.size else 1.0
        elements = np.unique(cols)
        y = {e: pulp.LpVariable(f"y_{e}", lowBound=0, upBound=1) for e in elements}
        modele += pulp.lpSum(s * float(poids[e]) * y[e] for e in elements)
        qui = {}
        for j, e in zip(lignes, cols):
            qui.setdefault(e, []).append(j)
        for e, js in qui.items():
            modele += y[e] <= pulp.lpSum(x[j] for j in js)
    else:
        # scores différents : chaque habitant rattaché à une seule station
        y = [pulp.LpVariable(f"y_{k}", lowBound=0, upBound=1) for k in range(lignes.size)]
        modele += pulp.lpSum(float(score[utiles[j]] * poids[e]) * y[k] for k, (j, e) in enumerate(zip(lignes, cols)))
        par_element = {}
        for k, (j, e) in enumerate(zip(lignes, cols)):
            par_element.setdefault(e, []).append(k)
            modele += y[k] <= x[j]
        for ks in par_element.values():
            if len(ks) > 1:
                modele += pulp.lpSum(y[k] for k in ks) <= 1

    solveur = pulp.getSolver("HiGHS", msg=False, timeLimit=limite_secondes, gapRel=ecart_relatif)
    modele.solve(solveur)
    choisis = [int(i) for j, i in enumerate(utiles) if (x[j].value() or 0) > 0.5]
    # valeur recalculée depuis les stations choisies : ne dépend pas des arrondis du solveur
    valeur = valeur_ensemble(couverture, poids, score, choisis)
    try:
        borne = float(modele.solverModel.getInfo().mip_dual_bound)
        if not np.isfinite(borne):
            borne = valeur
    except AttributeError:
        borne = valeur
    return SolutionExacte(choisis, valeur, max(borne, valeur), pulp.LpStatus[modele.status],
                          time.perf_counter() - debut)
