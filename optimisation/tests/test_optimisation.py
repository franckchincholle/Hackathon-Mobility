"""Tests sur de petits cas faits main, où l'on sait d'avance la bonne réponse.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from optim_mobilite import couverture, equite, glouton, scenarios  # noqa: E402
from optim_mobilite.contrat import Donnees, ErreurContrat, depuis_tables  # noqa: E402
from optim_mobilite.exact import resoudre_exact, valeur_ensemble  # noqa: E402
from optim_mobilite.geo import vers_wgs84  # noqa: E402
from optim_mobilite.mock import COUTS_MOCK  # noqa: E402

X0, Y0 = 3_618_100.0, 2_306_100.0  # centre d'un carreau à Toulouse, en EPSG:3035 comme MSc 1


def donnees_main(carreaux: list[dict], stations=(), lignes=()) -> Donnees:
    """Construit des données en mémoire : chaque carreau donné par (i, j) en pas de 200 m."""
    lignes_c = []
    for k, c in enumerate(carreaux):
        lignes_c.append({
            "idcar_200m": f"C{k}", "x_3035": X0 + 200 * c["i"], "y_3035": Y0 + 200 * c["j"], "lat": 0.0, "lon": 0.0,
            "population": c.get("pop", 100.0), "nb_options_total": c.get("options", 0),
            "a_option_citiz": c.get("citiz", False), "a_option_velo": c.get("velo", False),
            "a_option_bus": c.get("bus", False), "sous_seuil": c.get("sous_seuil", False),
            "commune": "Toulouse", "iris": "IRIS", "score_citiz": c.get("score", 1.0),
            "score_velo": 1.0, "score_bus": 1.0,
        })
    stations = pd.DataFrame(list(stations), columns=["id", "type", "x_3035", "y_3035"])
    lignes = pd.DataFrame(list(lignes), columns=["id_ligne", "ordre", "x_3035", "y_3035"])
    return Donnees(pd.DataFrame(lignes_c), stations, lignes, COUTS_MOCK.set_index("type"), Path("."))


def grille(n: int, **attributs) -> list[dict]:
    return [{"i": i, "j": j, **attributs} for i in range(-n, n + 1) for j in range(-n, n + 1)]


def instance_aleatoire(graine: int, n_cand=40, n_elem=120):
    rng = np.random.default_rng(graine)
    a = sparse.random(n_cand, n_elem, density=0.08, random_state=graine, format="csr")
    a.data[:] = 1.0
    a.sort_indices()
    return a, rng.uniform(1, 100, n_elem), rng.uniform(5, 30, n_cand)


# ---------- couverture ----------

def test_cercle_de_400_m_couvre_13_carreaux():
    # sur une grille de 200 m, le cercle de 400 m autour d'un centre touche 13 centres :
    # lui-même, 4 à 200 m, 4 à 283 m, 4 à 400 m pile (la frontière compte)
    d = donnees_main(grille(3))
    s = couverture.construire(d, "citiz")
    centre = int(np.flatnonzero((d.carreaux.x_3035 == X0) & (d.carreaux.y_3035 == Y0))[0])
    ligne = int(np.flatnonzero(s.candidats.idx_carreau == centre)[0])
    assert s.couverture[ligne].nnz == 13


def test_candidats_exclut_sous_seuil_deja_desservis_et_inhabites():
    d = donnees_main([
        {"i": 0, "j": 0},
        {"i": 5, "j": 0, "sous_seuil": True},
        {"i": 10, "j": 0, "citiz": True},
        {"i": 15, "j": 0, "pop": 0.0},
    ])
    assert list(couverture.candidats_du_type(d, "citiz")) == [0]


def test_arrets_de_bus_uniquement_sur_les_lignes():
    d = donnees_main(
        grille(4),
        lignes=[{"id_ligne": "L1", "ordre": k, "x_3035": X0 - 1_000 + 2_000 * k, "y_3035": Y0} for k in range(2)],
    )
    candidats = couverture.candidats_du_type(d, "bus")
    assert set(d.carreaux.y_3035.iloc[candidats]) == {Y0}  # la ligne horizontale y = Y0, et elle seule
    assert len(candidats) == 9


# ---------- glouton ----------

@pytest.mark.parametrize("graine", range(20))
def test_budget_jamais_depasse(graine):
    a, poids, couts = instance_aleatoire(graine)
    for budget in (0, 5, 17, 50, 120, 1_000):
        choix = glouton.optimiser(a, poids, couts, budget)
        assert choix.cout_total <= budget + 1e-9
        assert np.isclose(choix.cout_total, couts[choix.candidats].sum())


@pytest.mark.parametrize("graine", range(20))
def test_un_habitant_compte_une_seule_fois(graine):
    a, poids, couts = instance_aleatoire(graine)
    choix = glouton.glouton_paresseux(a, poids, couts, 120)
    # la somme des gains annoncés est exactement la valeur des éléments couverts, sans doublon
    assert np.isclose(sum(choix.gains), poids[choix.couverts].sum())
    assert np.isclose(choix.valeur_totale, poids[choix.couverts].sum())


def test_recouvrement_retire_les_habitants_deja_pris():
    # deux stations voisines partagent des carreaux : la seconde ne compte que les nouveaux
    d = donnees_main([{"i": i, "j": 0} for i in range(0, 6)])
    s = couverture.construire(d, "citiz")
    r = scenarios.resoudre(d, s, 50_000, 0.0, "bas")  # 2 stations Citiz à 25 k€
    assert len(r.liste) == 2
    assert np.isclose(r.liste.population_nouvelle.sum(), 600)  # les 6 carreaux, une seule fois chacun
    assert np.isclose(r.indicateurs["habitants_nouveaux"], 600)


@pytest.mark.parametrize("graine", range(20))
def test_paresseux_identique_au_naif(graine):
    a, poids, couts = instance_aleatoire(graine)
    for budget in (20, 60, 150):
        p = glouton.glouton_paresseux(a, poids, couts, budget)
        n = glouton.glouton_naif(a, poids, couts, budget)
        assert p.candidats == n.candidats
        assert p.recalculs <= n.recalculs


def test_meilleur_seul_evite_le_piege_du_ratio():
    # A : 1 € pour 2 (ratio 2) ; B : 10 € pour 10 (ratio 1). Budget 10 € :
    # le glouton prend A, B ne rentre plus (valeur 2) ; B seul vaut 10.
    a = sparse.csr_matrix(np.array([[1, 0], [0, 1]], dtype=float))
    choix = glouton.optimiser(a, np.array([2.0, 10.0]), np.array([1.0, 10.0]), 10)
    assert choix.strategie == "meilleur seul" and choix.candidats == [1]


# ---------- équité ----------

def test_alpha_zero_donne_le_glouton_pur():
    d = donnees_main(grille(6, pop=50.0) + [{"i": 20, "j": 0, "pop": 300.0, "options": 2}])
    s = couverture.construire(d, "citiz")
    np.testing.assert_allclose(equite.poids(s.elements, 0.0), s.elements.population)
    r = scenarios.resoudre(d, s, 75_000, 0.0, "bas")
    pur = glouton.optimiser(s.couverture, s.elements.population.to_numpy(),
                            scenarios.couts_candidats(d, s, "bas"), 75_000)
    assert r.choix.candidats == pur.candidats


# ---------- score de l'emplacement (décision 7) ----------

def test_score_departage_a_population_egale():
    # deux zones isolées de 100 habitants ; la seconde a un meilleur score : c'est elle
    d = donnees_main([{"i": 0, "j": 0, "score": 0.4}, {"i": 30, "j": 0, "score": 0.9}])
    s = couverture.construire(d, "citiz")
    r = scenarios.resoudre(d, s, 25_000, 0.0, "bas")
    assert r.liste.idcar_200m.tolist() == ["C1"]
    assert np.isclose(r.liste.valeur.iat[0], 0.9 * 100)


@pytest.mark.parametrize("graine", range(10))
def test_paresseux_identique_au_naif_avec_scores(graine):
    a, poids, couts = instance_aleatoire(graine)
    score = np.random.default_rng(graine + 100).uniform(0.1, 1, a.shape[0])
    p = glouton.glouton_paresseux(a, poids, couts, 80, score)
    n = glouton.glouton_naif(a, poids, couts, 80, score)
    assert p.candidats == n.candidats


@pytest.mark.parametrize("graine", range(5))
def test_exact_avec_scores_au_moins_aussi_bon(graine):
    a, poids, couts = instance_aleatoire(graine, n_cand=15, n_elem=40)
    score = np.random.default_rng(graine + 7).uniform(0.1, 1, a.shape[0])
    g = glouton.optimiser(a, poids, couts, 40, score)
    e = resoudre_exact(a, poids, couts, 40, score, limite_secondes=30)
    assert e.statut == "Optimal"
    assert couts[e.candidats].sum() <= 40 + 1e-6
    # la valeur du glouton (chaque habitant au score de la station qui l'a pris en premier)
    # ne dépasse ni celle de son propre ensemble (meilleur score) ni l'optimum
    assert g.valeur_totale <= valeur_ensemble(a, poids, score, g.candidats) + 1e-6
    assert e.valeur >= valeur_ensemble(a, poids, score, g.candidats) - 1e-6


def test_alpha_favorise_les_zones_sans_transport():
    # deux zones isolées : A (130 hab., déjà 2 options) et B (100 hab., aucun transport) ; budget pour une
    d = donnees_main([{"i": 0, "j": 0, "pop": 130.0, "options": 2}, {"i": 30, "j": 0, "pop": 100.0}])
    s = couverture.construire(d, "citiz")
    choix = {al: scenarios.resoudre(d, s, 25_000, al, "bas").liste.idcar_200m.tolist() for al in (0.0, 3.0)}
    assert choix[0.0] == ["C0"]  # efficacité pure : la zone la plus peuplée
    assert choix[3.0] == ["C1"]  # équité forte : 100 × 4 = 400 > 130 × 2 = 260


def test_bonus_continu():
    np.testing.assert_allclose(equite.bonus([0, 1, 3]), [1, 0.5, 0.25])
    with pytest.raises(ValueError):
        equite.poids(pd.DataFrame({"population": [1.0], "score": [1.0], "nb_options_total": [0]}), 5)


# ---------- exact ----------

@pytest.mark.parametrize("graine", range(5))
def test_exact_au_moins_aussi_bon_que_le_glouton(graine):
    a, poids, couts = instance_aleatoire(graine, n_cand=15, n_elem=40)
    g = glouton.optimiser(a, poids, couts, 40)
    e = resoudre_exact(a, poids, couts, 40, limite_secondes=30)
    assert e.statut == "Optimal"
    assert couts[e.candidats].sum() <= 40 + 1e-6
    assert e.valeur >= g.valeur_totale - 1e-6
    # la garantie théorique du meilleur des deux : ½ (1 − 1/e) de l'optimum
    assert g.valeur_totale >= 0.5 * (1 - 1 / np.e) * e.valeur - 1e-6


# ---------- contrat ----------

def tables_msc1() -> dict[str, pd.DataFrame]:
    """Un mini-jeu au format des tables de MSc 1 : 3 carreaux, 3 arrêts, 2 lignes, 2 stations."""
    xs = [X0, X0 + 200, X0 + 2_000]
    lon, lat = vers_wgs84(xs, [Y0] * 3)
    carreaux = pd.DataFrame({
        "idcar_200m": ["A", "B", "C"], "codes_communes": ["31555", "31555,31069", "31069"],
        "x_3035": xs, "y_3035": [Y0] * 3, "lat": lat, "lon": lon, "population": [500.0, 5.0, 300.0],
    })
    # deux arrêts de la ligne L1 près de A et B, un arrêt de métro M près de A ; rien près de C
    ax = [X0 + 50, X0 + 250, X0 - 100]
    alon, alat = vers_wgs84(ax, [Y0] * 3)
    arrets = pd.DataFrame({"arret_id": ["a1", "a2", "a3"], "modes": ["bus", "bus", "metro"], "nb_lignes": [1, 1, 1],
                           "lat": alat, "lon": alon, "x_3035": ax, "y_3035": [Y0] * 3})
    arrets_lignes = pd.DataFrame({"arret_id": ["a1", "a2", "a3"], "ligne_id": ["L1", "L1", "M"],
                                  "mode": ["bus", "bus", "metro"]})
    sx = [X0 + 100, X0 + 2_100]
    slon, slat = vers_wgs84(sx, [Y0] * 2)
    stations = pd.DataFrame({"station_id": ["v1", "c1"], "operateur": ["VélôToulouse", "Citiz"],
                             "type": ["velo", "autopartage"], "lat": slat, "lon": slon,
                             "x_3035": sx, "y_3035": [Y0] * 2})
    slon2, slat2 = vers_wgs84([X0 - 1_000, X0 + 3_000], [Y0, Y0])
    return {
        "carreaux": carreaux,
        "zone_communes": pd.DataFrame({"code_commune": ["31555", "31069"], "nom": ["Toulouse", "Blagnac"],
                                       "contour_geojson": ['{"type": "Polygon", "coordinates": [[[1.4, 43.6], [1.5, 43.6], [1.5, 43.7], [1.4, 43.6]]]}'] * 2}),
        "arrets": arrets, "arrets_lignes": arrets_lignes, "stations_partagees": stations,
        "tisseo_routes": pd.DataFrame({"route_id": ["r1", "r2"], "route_type": ["3", "1"]}),
        "tisseo_trips": pd.DataFrame({"route_id": ["r1", "r2"], "shape_id": ["s1", "s2"]}),
        "tisseo_shapes": pd.DataFrame({"shape_id": ["s1", "s1", "s2"], "shape_pt_lat": [slat2[0], slat2[1], 0.0],
                                       "shape_pt_lon": [slon2[0], slon2[1], 0.0], "shape_pt_sequence": [1, 2, 1]}),
    }


def test_preparation_compte_une_ligne_une_seule_fois():
    d = depuis_tables(tables_msc1())
    c = d.carreaux.set_index("idcar_200m")
    # A : ligne L1 (deux arrêts, comptée une fois) + métro M + vélo v1 = 3 options (décision 3)
    assert c.loc["A", "nb_options_total"] == 3
    assert c.loc["A", "a_option_bus"] and c.loc["A", "a_option_velo"] and not c.loc["A", "a_option_citiz"]
    # C : la station Citiz c1 à 100 m, rien d'autre
    assert c.loc["C", "nb_options_total"] == 1 and c.loc["C", "a_option_citiz"]
    # B : 5 habitants, sous le seuil provisoire ; à cheval, il prend la commune de la zone listée en premier
    assert c.loc["B", "sous_seuil"] and c.loc["B", "commune"] == "Toulouse"
    # seule la ligne de bus (route_type 3) est gardée pour poser des arrêts
    assert set(d.lignes_bus.id_ligne) == {"s1"}
    assert d.provisoires == ["accessibilité", "score de potentiel", "coûts Citiz, vélo et bus"]
    assert (d.carreaux.score_citiz == 1).all()


def test_livraisons_de_l_equipe_remplacent_le_provisoire():
    t = tables_msc1()
    t["accessibilite"] = pd.DataFrame({"idcar_200m": ["A", "B", "C"], "nb_options": [7, 0, 2],
                                       "sous_seuil": [False, False, True]})
    t["scores_potentiel"] = pd.DataFrame({"idcar_200m": ["A", "B", "C"], "score_potentiel": [0.2, 0.5, 0.9]})
    t["couts"] = COUTS_MOCK.copy()
    d = depuis_tables(t)
    assert d.provisoires == []
    c = d.carreaux.set_index("idcar_200m")
    assert c.loc["A", "nb_options_total"] == 7 and c.loc["C", "sous_seuil"]
    assert c.loc["C", "score_citiz"] == 0.9


def test_contrat_signale_une_colonne_manquante():
    t = tables_msc1()
    t["carreaux"] = t["carreaux"].drop(columns="population")
    with pytest.raises(ErreurContrat, match="population"):
        depuis_tables(t)


def test_contrat_refuse_des_coordonnees_hors_3035():
    t = tables_msc1()
    t["carreaux"]["x_3035"] = t["carreaux"].lon  # des degrés à la place des mètres
    with pytest.raises(ErreurContrat, match="EPSG:3035"):
        depuis_tables(t)


# ---------- coûts du MBA ----------

def test_cout_citiz_livre_et_velo_bus_en_mock():
    t = tables_msc1()
    t["couts"] = pd.DataFrame({"type": ["citiz"], "cout_bas": [12_437.08], "cout_defaut": [19_486.12],
                               "cout_haut": [24_143.52], "budget": ["citiz"]})
    d = depuis_tables(t)
    assert scenarios.cout_station(d.couts, "citiz", "defaut") == pytest.approx(19_486.12)
    assert scenarios.cout_station(d.couts, "velo", "bas") == COUTS_MOCK.set_index("type").loc["velo", "cout_bas"]
    assert d.couts.loc["citiz", "mock"] == False and d.couts.loc["bus", "mock"] == True  # noqa: E712
    assert "coûts vélo et bus" in d.provisoires


def test_ancien_format_de_couts_accepte():
    t = tables_msc1()
    t["couts"] = pd.DataFrame({"type": ["citiz"], "cout_install_bas": [10_000], "cout_install_haut": [20_000],
                               "cout_fonct_1an_bas": [15_000], "cout_fonct_1an_haut": [25_000], "budget": ["citiz"]})
    d = depuis_tables(t)
    assert [scenarios.cout_station(d.couts, "citiz", f) for f in ("bas", "defaut", "haut")] == [25_000, 35_000, 45_000]


def test_couts_incoherents_refuses():
    t = tables_msc1()
    t["couts"] = pd.DataFrame({"type": ["citiz"], "cout_bas": [30_000], "cout_defaut": [20_000],
                               "cout_haut": [40_000], "budget": ["citiz"]})
    with pytest.raises(ErreurContrat, match="cout_bas"):
        depuis_tables(t)


def test_robustesse_compare_bas_et_haut():
    d = donnees_main(grille(8, pop=40.0))
    s = couverture.construire(d, "citiz")
    rob = scenarios.robustesse(d, s, 100_000, 1.0)
    assert rob["nb_bas"] == 4 and rob["nb_haut"] == 2  # 100 k€ : 4 stations à 25 k€, 2 à 45 k€
    assert rob["part_haut_dans_bas"] == 1.0
    assert "selon les coûts" in scenarios.phrase_choc(rob)


# ---------- carte à calques ----------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import carte  # noqa: E402


def test_zones_a_potentiel_egal_au_premier_tour_du_glouton():
    d = donnees_main(grille(5, pop=60.0) + [{"i": 20, "j": 0, "pop": 500.0, "score": 0.5}])
    s = couverture.construire(d, "citiz")
    pot = scenarios.potentiel_candidats(d, s, 1.0)
    attendu = s.candidats.score.to_numpy() * (s.couverture @ equite.poids(s.elements, 1.0))
    np.testing.assert_allclose(pot.valeur, attendu)
    premier = glouton.glouton_paresseux(s.couverture, equite.poids(s.elements, 1.0),
                                        scenarios.couts_candidats(d, s, "bas"), 25_000, s.candidats.score.to_numpy())
    assert np.isclose(premier.gains[0], pot.valeur.max())


def _donnees_pour_carte(**livraisons):
    t = tables_msc1()
    t.update(livraisons)
    d = depuis_tables(t)
    x, y = d.carreaux.x_3035.to_numpy(), d.carreaux.y_3035.to_numpy()
    coins = [vers_wgs84(x + dx, y + dy) for dx, dy in ((-100, -100), (100, -100), (100, 100), (-100, 100))]
    d.carreaux["carre"] = list(np.stack([np.stack([c[0] for c in coins], 1), np.stack([c[1] for c in coins], 1)], 2).tolist())
    d.lignes_bus["lon"], d.lignes_bus["lat"] = vers_wgs84(d.lignes_bus.x_3035, d.lignes_bus.y_3035)
    return d


def test_aucun_calque_ne_detaille_un_carreau_sous_le_seuil():
    d = _donnees_pour_carte()
    s = couverture.construire(d, "citiz")
    r = scenarios.resoudre(d, s, 100_000, 1.0, "defaut")
    choix = {c.cle for c in carte.CALQUES if not c.indisponible(d)}
    sous_seuil = {tuple(map(tuple, c)) for c in d.carreaux.loc[d.carreaux.sous_seuil, "carre"]}
    assert sous_seuil  # le carreau B (5 habitants) est sous le seuil
    for couche in carte.couches(d, choix, r, s, scenarios.potentiel_candidats(d, s, 1.0), None):
        # pydeck range les données en liste d'enregistrements ; seuls les calques survolables informent
        lignes = couche.data if isinstance(couche.data, list) else []
        if getattr(couche, "pickable", False):
            montres = {tuple(map(tuple, ligne["carre"])) for ligne in lignes if "carre" in ligne}
            assert not montres & sous_seuil


def test_calques_de_l_equipe_s_activent_a_la_livraison():
    d = _donnees_pour_carte()
    indispo = {c.cle for c in carte.CALQUES if c.indisponible(d)}
    assert {"chaleur", "servie", "score"} <= indispo
    d = _donnees_pour_carte(
        accessibilite=pd.DataFrame({"idcar_200m": ["A", "B", "C"], "nb_options": [3, 0, 1],
                                    "sous_seuil": [False, True, False], "options_pour_1000": [6.0, 0.0, 3.3]}),
        population_servie=pd.DataFrame({"station_id": ["v1"], "population_servie": [480.0]}),
        scores_potentiel=pd.DataFrame({"idcar_200m": ["A", "B", "C"], "score_potentiel": [0.2, 0.5, 0.9]}),
    )
    assert not {c.cle for c in carte.CALQUES if c.indisponible(d) and not c.cle.startswith("crit_")}


# ---------- lecture en direct et copie de secours ----------

def test_fabric_injoignable_bascule_sur_la_copie_locale(tmp_path, monkeypatch):
    from optim_mobilite import contrat, fabric

    fabric.sauvegarder(tables_msc1(), tmp_path, "20/10/2026 à 15:00")

    def en_panne(_cache):
        raise fabric.FabricInjoignable("réseau coupé")

    monkeypatch.setattr(fabric, "lire", en_panne)
    d = contrat.charger_donnees(tmp_path, source="fabric")
    assert "copie locale" in d.lecture and "15:00" in d.lecture
    assert d.avertissements[0].startswith("Lecture en direct impossible (réseau coupé)")
    assert len(d.carreaux) == 3


def test_fabric_joignable_garde_une_copie(tmp_path, monkeypatch):
    from optim_mobilite import contrat, fabric

    monkeypatch.setattr(fabric, "lire", lambda _cache: (tables_msc1(), []))
    d = contrat.charger_donnees(tmp_path, source="fabric")
    assert d.lecture.startswith("données lues en direct sur Fabric")
    assert (tmp_path / "msc1" / "carreaux.parquet").exists() and (tmp_path / "derniere_lecture.json").exists()


def test_iris_nom_ou_commune_entiere():
    t = tables_msc1()
    t["carreaux_variables"] = pd.DataFrame({"idcar_200m": ["A", "B"], "code_iris": ["315550101", "310690000"]})
    t["iris"] = pd.DataFrame({"code_iris": ["315550101", "310690000"], "nom_iris": ["Capitole", None]})
    c = depuis_tables(t).carreaux.set_index("idcar_200m")
    assert (c.loc["A", "iris"], c.loc["B", "iris"], c.loc["C", "iris"]) == ("Capitole", "commune entière", "")


# ---------- critères au choix ----------

from optim_mobilite import criteres  # noqa: E402


def _carreaux_criteres():
    return pd.DataFrame({
        "population": [100.0, 200.0, 300.0, 400.0, 5.0],
        "sous_seuil": [False, False, False, False, True],
        "niveau_vie_moyen": [15_000, 30_000, 20_000, 25_000, 99_000],
        "part_menages_sans_voiture": [0.1, 0.4, np.nan, 0.2, 0.9],
        "type_iris": ["H", "A", "Z", "H", "H"],
        "commune": ["Toulouse", "Blagnac", "Toulouse", "Balma", "Toulouse"],
        "nb_options_total": [0, 3, 1, 5, 0],
    })


def test_un_critere_seul_classe_dans_l_ordre_de_sa_variable():
    c = _carreaux_criteres()
    s = criteres.score(c, criteres.Reglage({"niveau_vie": (1, "haut")}))
    assert list(np.argsort(s[:4])) == [0, 2, 3, 1]  # 15 k < 20 k < 25 k < 30 k
    s_bas = criteres.score(c, criteres.Reglage({"niveau_vie": (1, "bas")}))
    np.testing.assert_allclose(s_bas, 1 - s)  # le sens inversé retourne le classement


def test_le_rang_ignore_les_carreaux_sous_le_seuil_et_neutralise_les_inconnus():
    c = _carreaux_criteres()
    s = criteres.score(c, criteres.Reglage({"sans_voiture": (1, "haut")}))
    assert s[2] == 0.5  # quartier inconnu : neutre
    assert s[4] == 1.0  # au-dessus de toutes les valeurs de référence (le carreau sous le seuil n'en fait pas partie)


def test_poids_et_criteres_categoriels():
    c = _carreaux_criteres()
    quartier = criteres.score(c, criteres.Reglage({"type_quartier": (1, "haut")}))
    np.testing.assert_allclose(quartier, [1, 0, 0.5, 1, 1])
    communes = criteres.score(c, criteres.Reglage({"communes": (1, "haut")}, ("Blagnac", "Balma")))
    np.testing.assert_allclose(communes, [0, 1, 0, 1, 0])
    melange = criteres.score(c, criteres.Reglage({"type_quartier": (3, "haut"), "communes": (1, "haut")}, ("Blagnac",)))
    np.testing.assert_allclose(melange, (3 * quartier + communes_blagnac(c)) / 4)


def communes_blagnac(c):
    return c.commune.eq("Blagnac").astype(float).to_numpy()


def test_aucun_critere_donne_un_score_de_un():
    np.testing.assert_allclose(criteres.score(_carreaux_criteres(), criteres.Reglage()), 1.0)


def test_reglage_encode_et_decode():
    r = criteres.Reglage({"densite": (2, "haut"), "niveau_vie": (1, "bas"), "communes": (3, "haut")}, ("Blagnac", "Balma"))
    assert criteres.Reglage.decoder(r.encoder()) == r
    assert criteres.Reglage.decoder("inconnu:2,densite:9").actifs == {"densite": (3, "haut")}


def test_le_score_des_criteres_change_le_classement():
    # deux zones isolées de même population : le score imposé décide
    d = donnees_main([{"i": 0, "j": 0}, {"i": 30, "j": 0}])
    s = couverture.construire(d, "citiz")
    assert scenarios.resoudre(d, s, 25_000, 0.0, "bas", np.array([0.2, 0.9])).liste.idcar_200m.tolist() == ["C1"]
    assert scenarios.resoudre(d, s, 25_000, 0.0, "bas", np.array([0.9, 0.2])).liste.idcar_200m.tolist() == ["C0"]


def test_arbres_comptes_par_carreau():
    t = tables_msc1()
    lon, lat = vers_wgs84([X0 + 10, X0 + 20, X0 + 2_000], [Y0, Y0, Y0])
    t["arbres"] = pd.DataFrame({"lat": lat, "lon": lon})
    c = depuis_tables(t).carreaux.set_index("idcar_200m")
    assert (c.loc["A", "nb_arbres"], c.loc["B", "nb_arbres"], c.loc["C", "nb_arbres"]) == (2, 0, 1)
    assert criteres.disponibles(depuis_tables(t).carreaux)["arbres"]
    assert not criteres.disponibles(depuis_tables(tables_msc1()).carreaux)["arbres"]
