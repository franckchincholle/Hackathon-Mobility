"""Rentabilité d'une station et impact : petits cas où l'on sait d'avance la bonne réponse."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from optim_mobilite import impact, rentabilite, scenarios  # noqa: E402

COUT = 20_986.0  # coût complet d'une station de 2 voitures, fourchette par défaut du MBA


def test_les_stations_citiz_proposees_recoivent_leur_compte():
    liste = pd.DataFrame({"type": ["citiz", "citiz", "velo"], "cout": [COUT, COUT, 24_495.0],
                          "occupation_prevue": [0.40, np.nan, np.nan]})
    c = scenarios.ajouter_comptes(liste, "defaut")
    # sans prévision, la station est supposée moyenne, et c'est signalé
    assert c.occupation_estimee.tolist() == [False, True, False]
    assert c.occupation_prevue.iat[1] == rentabilite.OCCUPATION_RESEAU
    assert c.resultat.iat[0] == pytest.approx(rentabilite.comptes(0.40, COUT).resultat.iat[0])
    assert c.delai_ans.iat[0] == pytest.approx(3.11, abs=0.01)
    assert np.isnan(c.recette.iat[2])  # une station vélo n'a pas de recette Citiz


def test_classeur_velo_bus_lu_par_libelle(tmp_path):
    from optim_mobilite.couts_mba import ErreurClasseur, lire_classeur_collectivite

    lignes = [["Poste", "Bas", "Défaut", "Haut"], ["1. ARRÊT DE BUS", None, None, None],
              ["Coût annuel d’un arrêt (investissement amorti)", 275, 547.5, 1575.5],
              ["Coût annuel complet d’une station de 10 vélos", 21_133, 24_495, 30_000]]
    chemin = tmp_path / "Cout_bus_velo.xlsx"
    with pd.ExcelWriter(chemin) as ecrivain:
        pd.DataFrame(lignes[1:], columns=lignes[0]).to_excel(ecrivain, sheet_name="Calcul", index=False)
    couts = lire_classeur_collectivite(chemin).set_index("type")
    assert couts.loc["bus", "cout_defaut"] == 547.5 and couts.loc["velo", "cout_haut"] == 30_000
    assert set(couts.budget) == {"collectivite"} and "Cout_bus_velo.xlsx" in couts.loc["bus", "source"]
    with pd.ExcelWriter(chemin) as ecrivain:
        pd.DataFrame(lignes[1:3], columns=lignes[0]).to_excel(ecrivain, sheet_name="Calcul", index=False)
    with pytest.raises(ErreurClasseur):
        lire_classeur_collectivite(chemin)


def test_bilan_du_scenario():
    liste = scenarios.ajouter_comptes(pd.DataFrame({"type": ["citiz"] * 3, "cout": [COUT] * 3,
                                                    "occupation_prevue": [0.5, 0.4, 0.3]}), "defaut")
    carreaux = pd.DataFrame({"population": [100.0, 200.0], "menages": [50.0, 80.0],
                             "part_menages_sans_voiture": [0.2, 0.5], "niveau_vie_moyen": [20_000.0, 30_000.0]})
    b = scenarios.bilan(liste, carreaux, np.array([0, 1]), "defaut")
    assert b["voitures_ajoutees"] == 6 and b["investissement"] == 3 * 58_180
    assert b["recette_totale"] == pytest.approx(liste.recette.sum())
    assert b["environnement"]["voitures_en_moins"] == pytest.approx((6 * 4.6, 6 * 7.9))
    assert b["social"]["menages_sans_voiture"] == pytest.approx(50)
    assert not b["usage_estime"]


def test_une_voiture_moyenne_rapporte_la_recette_moyenne():
    assert rentabilite.recette_voiture(rentabilite.OCCUPATION_RESEAU) == pytest.approx(rentabilite.RECETTE_VOITURE)
    assert rentabilite.recette_voiture(0.0) == 0


def test_a_l_equilibre_le_resultat_est_nul():
    occ = rentabilite.occupation_equilibre(COUT)
    assert 0.29 < occ < 0.31  # une station moyenne couvre tout juste son coût complet
    assert rentabilite.comptes(occ, COUT).resultat.iat[0] == pytest.approx(0, abs=1e-6)


def test_une_station_bien_placee_se_rembourse_plus_vite():
    c = rentabilite.comptes([0.30, 0.40, 0.50], COUT)
    assert c.recette.is_monotonic_increasing and c.delai_ans.is_monotonic_decreasing
    # 40 % d'occupation : 28 070 € de recette, 7 084 € de résultat, 18 720 € de flux, 3,1 ans
    assert c.delai_ans.iat[1] == pytest.approx(58_180 / (2 * 10_000 * 0.40 / 0.285 - COUT + 11_636), rel=1e-6)


def test_une_station_qui_ne_degage_rien_n_est_jamais_remboursee():
    c = rentabilite.comptes(0.0, COUT)
    assert np.isinf(c.delai_ans.iat[0]) and not c.rentable.iat[0]


def test_fourchette_inconnue_refusee():
    with pytest.raises(ValueError):
        rentabilite.comptes(0.3, COUT, fourchette="moyen")


def test_tresorerie_part_de_l_investissement_et_monte_du_flux():
    t = rentabilite.tresorerie([10_000.0, 20_000.0], annees=3)
    assert t.cumul.tolist() == [-116_360.0, -86_360.0, -56_360.0, -26_360.0]


def test_impact_proportionnel_au_nombre_de_voitures():
    deux = impact.environnement(2)
    assert deux["voitures_en_moins"] == pytest.approx((9.2, 15.8))
    assert deux["m2_liberes"] == pytest.approx((18.0, 60.0))
    assert deux["tonnes_co2_evitees"] == pytest.approx((5.12, 9.728))
    assert impact.environnement(4)["km_evites"] == pytest.approx(tuple(2 * k for k in deux["km_evites"]))


def test_mediane_des_habitants_et_pas_des_carreaux():
    # trois carreaux : un très peuplé et modeste, deux peu peuplés et aisés
    assert impact.mediane_ponderee([15_000, 40_000, 45_000], [1_000, 10, 10]) == 15_000
    assert impact.mediane_ponderee([15_000, np.nan, 45_000], [10, 10, 1_000]) == 45_000


def test_social_compte_les_menages_sans_voiture_des_carreaux_gagnes():
    carreaux = pd.DataFrame({
        "population": [1_000.0, 500.0, 500.0], "menages": [400.0, 200.0, 250.0],
        "part_menages_sans_voiture": [0.5, 0.1, 0.0], "niveau_vie_moyen": [15_000.0, 30_000.0, 40_000.0],
        "logements_sociaux": [100.0, 0.0, np.nan],
    })
    s = impact.social(carreaux, [0, 1, 1])
    assert s["habitants"] == 1_500 and s["menages_sans_voiture"] == pytest.approx(220)
    assert s["part_sous_mediane"] == pytest.approx(0.0)  # la médiane des habitants est 15 000 € : personne en dessous
    assert s["logements_sociaux"] == 100
    sans_colonnes = impact.social(carreaux[["population"]], [0])
    assert np.isnan(sans_colonnes["menages_sans_voiture"]) and np.isnan(sans_colonnes["part_sous_mediane"])
