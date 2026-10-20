"""Un scénario = (budget Citiz ou collectivité, montant, α, fourchette de coûts).

Ce module transforme le résultat brut du glouton en ce que lit un décideur : la liste
priorisée, les indicateurs, la courbe budget -> habitants, la comparaison des α, la
robustesse aux coûts et la phrase-choc. L'application, les exports Power BI et le
notebook Fabric passent tous par ici.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import equite, glouton, impact, rentabilite
from .contrat import FOURCHETTES, Donnees, cout_station  # noqa: F401 (réexportés pour l'application)
from .couverture import Structure

NOMS_TYPES = {"citiz": "Citiz", "velo": "Station vélo", "bus": "Arrêt de bus"}


@dataclass
class Resultat:
    budget_type: str
    budget: float
    alpha: float
    fourchette: str
    liste: pd.DataFrame  # une ligne par station proposée, dans l'ordre de priorité
    indicateurs: dict
    couverts: np.ndarray  # booléen par élément de la structure
    choix: glouton.Choix


def couts_candidats(donnees: Donnees, structure: Structure, fourchette: str) -> np.ndarray:
    par_type = {t: cout_station(donnees.couts, t, fourchette) for t in structure.types}
    return structure.candidats.type.map(par_type).to_numpy(dtype=float)


def arrondi(population) -> np.ndarray:
    """Populations affichées à la dizaine : aucun chiffre ne trahit un petit carreau."""
    return (np.round(np.asarray(population, dtype=float) / 10) * 10).astype(np.int64)


def score_candidats(structure: Structure, score_carreaux: np.ndarray | None) -> np.ndarray:
    """Le score de chaque candidat : celui du modèle (par défaut), ou un score par carreau imposé
    (les critères choisis à l'écran, criteres.py), qui vaut alors pour tous les types d'équipement."""
    if score_carreaux is None:
        return structure.candidats.score.to_numpy()
    return np.asarray(score_carreaux, dtype=float)[structure.candidats.idx_carreau.to_numpy()]


def resoudre(donnees: Donnees, structure: Structure, budget: float, alpha: float, fourchette: str,
             score_carreaux: np.ndarray | None = None) -> Resultat:
    poids = equite.poids(structure.elements, alpha)
    couts = couts_candidats(donnees, structure, fourchette)
    score = score_candidats(structure, score_carreaux)
    choix = glouton.optimiser(structure.couverture, poids, couts, budget, score)

    el = structure.elements
    pop = el.population.to_numpy()
    sans_transport = (el.nb_options_total == 0).to_numpy()
    deja = np.zeros(len(el), dtype=bool)
    lignes = []
    for rang, i in enumerate(choix.candidats, start=1):
        elems = structure.couverture.indices[structure.couverture.indptr[i] : structure.couverture.indptr[i + 1]]
        nouveaux = elems[~deja[elems]]
        deja[nouveaux] = True
        t, idx = structure.candidats.type.iat[i], structure.candidats.idx_carreau.iat[i]
        carreau = donnees.carreaux.iloc[idx]
        lignes.append(
            {
                "rang": rang,
                "type": t,
                "equipement": NOMS_TYPES[t],
                "idcar_200m": carreau.idcar_200m,
                "commune": carreau.commune,
                "iris": carreau.iris,
                "lon": carreau.lon,
                "lat": carreau.lat,
                "score": score[i],
                "cout_bas": cout_station(donnees.couts, t, "bas"),
                "cout_haut": cout_station(donnees.couts, t, "haut"),
                "cout": couts[i],
                "population_nouvelle": pop[nouveaux].sum(),
                "dont_sans_transport": pop[nouveaux][sans_transport[nouveaux]].sum(),
                "valeur": score[i] * poids[nouveaux].sum(),
                "occupation_prevue": carreau.get("occupation_prevue", np.nan) if t == "citiz" else np.nan,
            }
        )
    colonnes = ["rang", "type", "equipement", "idcar_200m", "commune", "iris", "lon", "lat", "score", "cout_bas",
                "cout_haut", "cout", "population_nouvelle", "dont_sans_transport", "valeur", "occupation_prevue"]
    liste = pd.DataFrame(lignes, columns=colonnes)
    liste["cout_cumule"] = liste.cout.cumsum()
    liste["population_cumulee"] = liste.population_nouvelle.cumsum()
    liste = ajouter_comptes(liste, fourchette)

    # Habitants distincts : pour le budget collectivité, un habitant qui gagne un vélo ET un
    # bus compte une fois ici (et une fois par type dans la liste).
    couverts = choix.couverts
    carreaux_gagnes = np.unique(el.idx_carreau.to_numpy()[couverts])
    c = donnees.carreaux
    pop_c = c.population.to_numpy()
    sans_c = (c.nb_options_total == 0).to_numpy()
    indicateurs = {
        "budget": budget,
        "nb_stations": len(liste),
        "cout_total": choix.cout_total,
        "habitants_nouveaux": float(pop_c[carreaux_gagnes].sum()),
        "habitants_sans_transport_nouveaux": float(pop_c[carreaux_gagnes][sans_c[carreaux_gagnes]].sum()),
        "carreaux_sans_transport_gagnes": int(sans_c[carreaux_gagnes].sum()),
        "valeur": choix.valeur_totale,
        "strategie": choix.strategie,
        "recalculs": choix.recalculs,
        "nb_candidats": int(structure.couverture.shape[0]),
        **{f"habitants_nouveaux_{t}": float(pop[couverts & (el.type == t).to_numpy()].sum()) for t in structure.types},
        **bilan(liste, c, carreaux_gagnes, fourchette),
    }
    return Resultat(structure.budget, budget, alpha, fourchette, liste, indicateurs, couverts, choix)


def ajouter_comptes(liste: pd.DataFrame, fourchette: str) -> pd.DataFrame:
    """Recette, résultat et délai de retour de chaque station Citiz proposée (rentabilite.py).

    Sans prévision d'usage pour un carreau, la station est supposée occupée comme la moyenne du
    réseau : `occupation_estimee` le dit, et l'écran aussi.
    """
    liste = liste.copy()
    citiz = (liste.type == "citiz").to_numpy()
    liste["occupation_estimee"] = citiz & liste.occupation_prevue.isna().to_numpy()
    liste.loc[liste.occupation_estimee, "occupation_prevue"] = rentabilite.OCCUPATION_RESEAU
    for colonne in ("recette", "resultat", "delai_ans"):
        liste[colonne] = np.nan
    if citiz.any():
        # toutes les stations Citiz d'un scénario ont le même coût complet (même type, même fourchette)
        comptes = rentabilite.comptes(liste.loc[citiz, "occupation_prevue"], float(liste.loc[citiz, "cout"].iat[0]),
                                      fourchette)
        for colonne in ("recette", "resultat", "delai_ans"):
            liste.loc[citiz, colonne] = comptes[colonne].to_numpy()
    return liste


def bilan(liste: pd.DataFrame, carreaux: pd.DataFrame, carreaux_gagnes: np.ndarray, fourchette: str) -> dict:
    """Ce que le scénario rapporte à Citiz, à la ville et aux ménages : les chiffres de l'en-tête."""
    citiz = liste[liste.type == "citiz"]
    voitures = rentabilite.VOITURES_PAR_STATION * len(citiz)
    return {
        "voitures_ajoutees": voitures,
        "recette_totale": float(citiz.recette.sum()),
        "resultat_total": float(citiz.resultat.sum()),
        "investissement": float(len(citiz) * rentabilite.INVESTISSEMENT[fourchette]),
        "occupation_moyenne_prevue": float(citiz.occupation_prevue.mean()) if len(citiz) else np.nan,
        "usage_estime": bool(citiz.occupation_estimee.any()) if len(citiz) else False,
        "environnement": impact.environnement(voitures),
        "social": impact.social(carreaux, carreaux_gagnes),
    }


def potentiel_candidats(donnees: Donnees, structure: Structure, alpha: float,
                        score_carreaux: np.ndarray | None = None) -> pd.DataFrame:
    """Zones à potentiel : la valeur de chaque emplacement candidat s'il était posé en premier.

    C'est exactement le gain du premier tour du glouton (score × habitants pas encore desservis
    à 400 m, pondérés par α) : la carte montre où l'outil irait chercher, avant tout arbitrage
    de budget.
    """
    poids = equite.poids(structure.elements, alpha)
    pop = structure.elements.population.to_numpy()
    c = donnees.carreaux.iloc[structure.candidats.idx_carreau]
    return pd.DataFrame({
        "type": structure.candidats.type.to_numpy(),
        "idx_carreau": structure.candidats.idx_carreau.to_numpy(),
        "commune": c.commune.to_numpy(),
        "valeur": score_candidats(structure, score_carreaux) * (structure.couverture @ poids),
        "habitants": structure.couverture @ pop,
    })


def courbe(donnees: Donnees, structure: Structure, alpha: float, fourchette: str, budgets,
           score_carreaux: np.ndarray | None = None) -> pd.DataFrame:
    """Habitants nouvellement desservis selon le budget : la courbe des rendements décroissants."""
    lignes = []
    for b in budgets:
        r = resoudre(donnees, structure, float(b), alpha, fourchette, score_carreaux)
        lignes.append({"budget": float(b), **{k: r.indicateurs[k] for k in
                       ("nb_stations", "cout_total", "habitants_nouveaux", "habitants_sans_transport_nouveaux")}})
    df = pd.DataFrame(lignes)
    # habitants gagnés par tranche de 10 000 € : la pente qui baisse
    df["habitants_par_10k"] = (df.habitants_nouveaux.diff() / df.budget.diff() * 10_000).round(0)
    return df


def comparer_alpha(donnees: Donnees, structure: Structure, budget: float, fourchette: str,
                   alpha_haut: float = equite.ALPHA_MAX, score_carreaux: np.ndarray | None = None) -> dict:
    """Ce que coûte et ce que rapporte l'équité : α = 0 contre α élevé, même budget."""
    a, b = (resoudre(donnees, structure, budget, al, fourchette, score_carreaux).indicateurs
            for al in (0.0, alpha_haut))
    return {
        "alpha_haut": alpha_haut,
        "habitants_alpha0": a["habitants_nouveaux"],
        "habitants_alpha_haut": b["habitants_nouveaux"],
        "habitants_en_moins": a["habitants_nouveaux"] - b["habitants_nouveaux"],
        "sans_transport_alpha0": a["habitants_sans_transport_nouveaux"],
        "sans_transport_alpha_haut": b["habitants_sans_transport_nouveaux"],
        "sans_transport_en_plus": b["habitants_sans_transport_nouveaux"] - a["habitants_sans_transport_nouveaux"],
        "zones_sans_transport_alpha0": a["carreaux_sans_transport_gagnes"],
        "zones_sans_transport_alpha_haut": b["carreaux_sans_transport_gagnes"],
    }


def robustesse(donnees: Donnees, structure: Structure, budget: float, alpha: float,
               score_carreaux: np.ndarray | None = None) -> dict:
    """La même recommandation tient-elle si les coûts réels sont ceux de la fourchette haute ?

    On compare les deux bouts de la fourchette du MBA ; le niveau « défaut » sert à la phrase-choc.
    """
    bas, defaut, haut = (resoudre(donnees, structure, budget, alpha, f, score_carreaux) for f in FOURCHETTES)
    cles_bas = set(zip(bas.liste.type, bas.liste.idcar_200m))
    cles_haut = set(zip(haut.liste.type, haut.liste.idcar_200m))
    communes = cles_bas & cles_haut
    tableau = bas.liste[["rang", "equipement", "commune", "iris", "idcar_200m", "type"]].rename(columns={"rang": "rang_bas"})
    tableau = tableau.merge(
        haut.liste[["rang", "type", "idcar_200m"]].rename(columns={"rang": "rang_haut"}), on=["type", "idcar_200m"], how="outer"
    )
    return {
        "bas": bas,
        "defaut": defaut,
        "haut": haut,
        "nb_bas": len(cles_bas),
        "nb_haut": len(cles_haut),
        "nb_communes": len(communes),
        # part des stations retenues en coûts hauts qui le sont aussi en coûts bas
        "part_haut_dans_bas": len(communes) / len(cles_haut) if cles_haut else 1.0,
        "tableau": tableau.sort_values(["rang_bas", "rang_haut"]).drop(columns=["type"]).reset_index(drop=True),
    }


def euros(montant: float) -> str:
    if montant >= 1_000_000:
        return f"{montant / 1_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " M€"
    return f"{montant / 1_000:.0f} k€"


def nombre(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def phrase_choc(rob: dict) -> str:
    """« Avec X € par an, Citiz touche Y habitants de plus » : coûts par défaut, et la fourchette
    des coûts bas et hauts entre parenthèses, donc honnête."""
    bas, defaut, haut = rob["bas"], rob["defaut"], rob["haut"]
    h = arrondi(defaut.indicateurs["habitants_nouveaux"])
    extremes = sorted(arrondi([haut.indicateurs["habitants_nouveaux"], bas.indicateurs["habitants_nouveaux"]]))
    s = arrondi(defaut.indicateurs["habitants_sans_transport_nouveaux"])
    if extremes[1] == 0:
        return f"Avec {euros(bas.budget)} par an, aucune station ne rentre dans le budget."
    fourchette = "" if extremes[0] == extremes[1] else \
        f" (de {nombre(extremes[0])} à {nombre(extremes[1])} selon les coûts)"
    if bas.budget_type == "citiz":
        debut = f"Avec {euros(bas.budget)} par an, Citiz touche {nombre(h)} habitants de plus{fourchette}"
    else:
        debut = (f"Avec {euros(bas.budget)} par an de la collectivité, {nombre(h)} habitants gagnent un vélo "
                 f"ou un bus à 5 minutes{fourchette}")
    if s == 0:
        return debut + "."
    return f"{debut}, dont {nombre(s)} qui n'ont aujourd'hui aucun transport."
