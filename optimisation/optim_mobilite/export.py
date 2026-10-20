"""Grille de scénarios précalculés, pour un rapport Power BI qui ne fait que filtrer.

Deux tables reliées par id_scenario (une ligne par scénario -> plusieurs stations) :
- scenarios  : budget_type, budget, alpha, fourchette, indicateurs, phrase-choc ;
- selections : la liste priorisée de chaque scénario, avec longitude et latitude pour la carte.
Les populations sont arrondies à la dizaine, comme dans l'application.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import couverture, scenarios
from .contrat import Donnees

GRILLE = {
    "citiz": np.arange(0, 1_000_001, 50_000),
    "collectivite": np.arange(0, 2_000_001, 100_000),
}
ALPHAS = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)


def grille(donnees: Donnees, grille_budgets: dict = GRILLE, alphas=ALPHAS) -> tuple[pd.DataFrame, pd.DataFrame]:
    lignes_sc, listes = [], []
    for budget_type, montants in grille_budgets.items():
        s = couverture.construire(donnees, budget_type)
        for alpha in alphas:
            for montant in montants:
                rob = scenarios.robustesse(donnees, s, float(montant), alpha)
                phrase = scenarios.phrase_choc(rob)
                for fourchette in scenarios.FOURCHETTES:
                    r = rob[fourchette]
                    id_sc = f"{budget_type}|{int(montant)}|{alpha:g}|{fourchette}"
                    k = r.indicateurs
                    lignes_sc.append({
                        "id_scenario": id_sc, "budget_type": budget_type, "budget": int(montant), "alpha": alpha,
                        "fourchette": fourchette, "nb_stations": k["nb_stations"], "cout_total": k["cout_total"],
                        "habitants_nouveaux": int(scenarios.arrondi(k["habitants_nouveaux"])),
                        "habitants_sans_transport_nouveaux": int(scenarios.arrondi(k["habitants_sans_transport_nouveaux"])),
                        "carreaux_sans_transport_gagnes": k["carreaux_sans_transport_gagnes"],
                        "valeur": round(k["valeur"], 1),
                        "part_stations_robustes": rob["part_haut_dans_bas"],
                        "phrase": phrase,
                    })
                    # retenue avec les coûts bas ET avec les coûts hauts du MBA
                    robustes = set(zip(rob["bas"].liste.type, rob["bas"].liste.idcar_200m)) & set(
                        zip(rob["haut"].liste.type, rob["haut"].liste.idcar_200m))
                    liste = r.liste.assign(
                        id_scenario=id_sc,
                        population_nouvelle=scenarios.arrondi(r.liste.population_nouvelle),
                        dont_sans_transport=scenarios.arrondi(r.liste.dont_sans_transport),
                        population_cumulee=scenarios.arrondi(r.liste.population_cumulee),
                        valeur=r.liste.valeur.round(1),
                        retenue_bas_et_haut=[(t, c) in robustes for t, c in zip(r.liste.type, r.liste.idcar_200m)],
                    )
                    listes.append(liste)
    selections = pd.concat([l for l in listes if len(l)], ignore_index=True)
    selections["retenue_bas_et_haut"] = selections.retenue_bas_et_haut.astype(bool)
    selections = selections[["id_scenario", *[c for c in selections.columns if c != "id_scenario"]]]
    return pd.DataFrame(lignes_sc), selections


def ecrire(donnees: Donnees, dossier: Path, **options) -> dict[str, Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    prefixe = "PROVISOIRE_" if donnees.est_provisoire else ""
    tables = dict(zip(("scenarios", "selections"), grille(donnees, **options)))
    chemins = {}
    for nom, df in tables.items():
        df.to_parquet(dossier / f"{prefixe}{nom}.parquet", index=False)
        # CSV : UTF-8 avec BOM, lu tel quel par Power BI et Excel
        df.to_csv(dossier / f"{prefixe}{nom}.csv", index=False, encoding="utf-8-sig")
        chemins[nom] = dossier / f"{prefixe}{nom}.csv"
    return chemins
