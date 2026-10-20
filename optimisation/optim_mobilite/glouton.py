"""Couverture maximale sous budget : glouton paresseux, et garde-fou du meilleur candidat seul.

Le glouton, en une phrase : tant qu'il reste du budget, on pose la station qui apporte le
plus de valeur nouvelle par euro, puis on retire les habitants qu'elle couvre.

La valeur nouvelle d'un candidat i (décision 7) :
    gain_i = score_i × Σ poids des habitants qu'il couvre et que personne ne couvre encore

Pourquoi « paresseux » : le gain d'un candidat ne peut que baisser quand on pose d'autres
stations (ses habitants peuvent être pris, jamais rendus ; son score ne bouge pas). On garde
donc dans un tas les gains de la dernière fois, qui sont des majorants. On ne recalcule que
le candidat du haut du tas : si son gain à jour reste au-dessus du majorant suivant, c'est
le meilleur, et les milliers d'autres n'ont pas été touchés. Même résultat que le glouton
naïf, en beaucoup moins de calculs.

Pourquoi le meilleur seul : le glouton au ratio peut se faire piéger par une petite station
très rentable qui « bloque » une grosse. Prendre le meilleur des deux (glouton ou meilleur
candidat seul qui rentre dans le budget) garantit au moins ½ (1 − 1/e) ≈ 32 % de l'optimum
quand les scores sont égaux (Khuller, Moss et Naor, 1999 ; Leskovec et al., 2007). En
pratique on est bien plus haut : la version exacte (exact.py) mesure l'écart.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
from scipy import sparse

TOLERANCE = 1e-9


@dataclass
class Choix:
    candidats: list[int]  # dans l'ordre de sélection
    gains: list[float]  # valeur nouvelle apportée par chacun, au moment où il est choisi
    couverts: np.ndarray  # booléen par élément
    cout_total: float
    valeur_totale: float
    recalculs: int  # nombre de gains recalculés (pour montrer l'intérêt du paresseux)
    strategie: str  # 'glouton' ou 'meilleur seul'


def _elements(couverture: sparse.csr_matrix, i: int) -> np.ndarray:
    return couverture.indices[couverture.indptr[i] : couverture.indptr[i + 1]]


def _scores(couverture: sparse.csr_matrix, score: np.ndarray | None) -> np.ndarray:
    return np.ones(couverture.shape[0]) if score is None else np.asarray(score, dtype=float)


def glouton_paresseux(couverture: sparse.csr_matrix, poids: np.ndarray, couts: np.ndarray, budget: float,
                      score: np.ndarray | None = None) -> Choix:
    score = _scores(couverture, score)
    couverts = np.zeros(couverture.shape[1], dtype=bool)
    gains_initiaux = score * (couverture @ poids)
    tas = [(-g / c, i) for i, (g, c) in enumerate(zip(gains_initiaux, couts)) if g > 0 and c <= budget + TOLERANCE]
    heapq.heapify(tas)
    restant = budget
    choisis, gains, recalculs = [], [], 0
    while tas:
        _, i = heapq.heappop(tas)
        if couts[i] > restant + TOLERANCE:
            continue  # le budget ne fait que baisser : il ne rentrera plus jamais
        elems = _elements(couverture, i)
        nouveaux = elems[~couverts[elems]]
        gain = float(score[i] * poids[nouveaux].sum())
        recalculs += 1
        if gain <= TOLERANCE:
            continue
        ratio = gain / couts[i]
        if tas and ratio < -tas[0][0] - TOLERANCE:
            heapq.heappush(tas, (-ratio, i))  # périmé : on le remet à sa vraie place
            continue
        couverts[nouveaux] = True  # un habitant n'est compté qu'une fois
        restant -= couts[i]
        choisis.append(i)
        gains.append(gain)
    return Choix(choisis, gains, couverts, float(budget - restant), float(sum(gains)), recalculs, "glouton")


def glouton_naif(couverture: sparse.csr_matrix, poids: np.ndarray, couts: np.ndarray, budget: float,
                 score: np.ndarray | None = None) -> Choix:
    """Même règle sans le tas : recalcule tout à chaque étape. Sert de référence aux tests."""
    score = _scores(couverture, score)
    couverts = np.zeros(couverture.shape[1], dtype=bool)
    restant, choisis, gains, recalculs = budget, [], [], 0
    while True:
        gains_courants = score * (couverture @ (poids * ~couverts))
        recalculs += couverture.shape[0]
        ratio = np.where((couts <= restant + TOLERANCE) & (gains_courants > TOLERANCE), gains_courants / couts, -1)
        if ratio.size == 0 or ratio.max() < 0:
            break
        # même départage que le tas en cas d'égalité : le plus petit indice
        i = int(np.flatnonzero(ratio >= ratio.max() - TOLERANCE)[0])
        couverts[_elements(couverture, i)] = True
        restant -= couts[i]
        choisis.append(i)
        gains.append(float(gains_courants[i]))
    return Choix(choisis, gains, couverts, float(budget - restant), float(sum(gains)), recalculs, "glouton")


def meilleur_seul(couverture: sparse.csr_matrix, poids: np.ndarray, couts: np.ndarray, budget: float,
                  score: np.ndarray | None = None) -> Choix | None:
    gains = _scores(couverture, score) * (couverture @ poids)
    possibles = np.flatnonzero(couts <= budget + TOLERANCE)
    if possibles.size == 0:
        return None
    i = int(possibles[np.argmax(gains[possibles])])
    couverts = np.zeros(couverture.shape[1], dtype=bool)
    couverts[_elements(couverture, i)] = True
    return Choix([i], [float(gains[i])], couverts, float(couts[i]), float(gains[i]), 0, "meilleur seul")


def optimiser(couverture: sparse.csr_matrix, poids: np.ndarray, couts: np.ndarray, budget: float,
              score: np.ndarray | None = None) -> Choix:
    """Le meilleur du glouton paresseux et du meilleur candidat seul."""
    glouton = glouton_paresseux(couverture, poids, couts, budget, score)
    seul = meilleur_seul(couverture, poids, couts, budget, score)
    if seul is not None and seul.valeur_totale > glouton.valeur_totale + TOLERANCE:
        return seul
    return glouton
