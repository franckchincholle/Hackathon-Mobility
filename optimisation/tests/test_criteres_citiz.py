"""Tests du module des critères Citiz, sur un petit jeu fait main, sans réseau.

    python -m pytest tests/test_criteres_citiz.py -q
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from optim_mobilite import criteres_citiz as cc  # noqa: E402

LIBELLES_CITIZ = ["Transports collectifs", "Densité urbaine", "Mixité habitat/activité", "Accessibilité/circulation",
                  "Simple pour stationner", "Taux de motorisation faible", "Visible", "Arbres à distance"]


def table_criteres() -> pd.DataFrame:
    """Trois carreaux : A et B mesurés (A a une station Citiz), C hors des communes inventoriées."""
    lignes = []
    for idcar, indice, mesures, station in (("A", 80.0, True, True), ("B", 40.0, True, False), ("C", 60.0, False, False)):
        ligne = {"idcar_200m": idcar, "indice_citiz": indice, "arbres_mesures": mesures, "station_citiz": station}
        for k, c in enumerate(cc.CRITERES):
            ligne[c.colonne_note] = float(10 * (k + 1))
            ligne[c.colonne] = float(k)
        if not mesures:
            ligne["note_arbres"], ligne["part_sans_arbre_10m"] = 50.0, None
        lignes.append(ligne)
    return pd.DataFrame(lignes)


def table_places() -> pd.DataFrame:
    return pd.DataFrame([{"idcar_200m": "A", "lat": 43.6, "lon": 1.44, "dist_arbre_m": 23.5,
                          "adresse": "1 Place du Capitole 31000 Toulouse", "capacite": None}])


def test_les_8_criteres_de_citiz():
    assert [c.libelle for c in cc.CRITERES] == LIBELLES_CITIZ
    assert len({c.cle for c in cc.CRITERES}) == 8
    assert all(c.sens in ("croissant", "decroissant") and c.source for c in cc.CRITERES)
    assert {c.cle: c.sens for c in cc.CRITERES}["accessibilite"] == "decroissant"


def test_tables_absentes():
    assert cc.lire_criteres({}) is None
    assert cc.lire_criteres({"places_candidates": table_places()}) is None


def test_lecture_et_radar():
    d = cc.lire_criteres({"criteres_citiz": table_criteres(), "places_candidates": table_places()})
    radar = cc.notes_radar(d, "A")
    assert list(radar["libelle"]) == LIBELLES_CITIZ
    assert list(radar["note"]) == [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
    assert radar["mesure"].all()
    # hors des communes inventoriées : note neutre, valeur absente, critère signalé non mesuré
    arbres = cc.notes_radar(d, "C").set_index("cle").loc["arbres"]
    assert arbres["note"] == cc.NOTE_NEUTRE and pd.isna(arbres["valeur"]) and not arbres["mesure"]
    with pytest.raises(KeyError):
        cc.notes_radar(d, "Z")


def test_place_du_carreau():
    d = cc.lire_criteres({"criteres_citiz": table_criteres(), "places_candidates": table_places()})
    place = cc.place_du_carreau(d, "A")
    assert place["dist_arbre_m"] == 23.5 and place["adresse"].startswith("1 Place du Capitole")
    assert place["capacite"] is None
    assert cc.place_du_carreau(d, "B") is None
    # sans la table des places, aucun carreau n'a de place
    assert cc.place_du_carreau(cc.lire_criteres({"criteres_citiz": table_criteres()}), "A") is None


def test_place_la_plus_proche_a_defaut_de_place_dans_le_carreau():
    places = table_places().assign(x_3035=3_618_000.0, y_3035=2_306_000.0)
    d = cc.lire_criteres({"criteres_citiz": table_criteres(), "places_candidates": places})
    assert cc.place_la_plus_proche(d, "A", 0.0, 0.0)["distance_centre_m"] == 0.0  # la sienne d'abord
    voisine = cc.place_la_plus_proche(d, "B", 3_618_000.0 + 120, 2_306_000.0 + 160)
    assert voisine["adresse"].startswith("1 Place du Capitole") and voisine["distance_centre_m"] == pytest.approx(200)
    assert cc.place_la_plus_proche(d, "B", 3_618_000.0 + 400, 2_306_000.0) is None  # au-delà de 300 m


def test_comparaison_avec_les_stations():
    d = cc.lire_criteres({"criteres_citiz": table_criteres()})
    resume = cc.comparer_stations(d)
    assert resume == {"carreaux_avec_station": 1, "indice_avec_station": 80.0, "indice_sans_station": 50.0,
                      "auc": 1.0}
    sans = table_criteres().drop(columns="station_citiz")
    assert cc.comparer_stations(cc.lire_criteres({"criteres_citiz": sans})) is None


@pytest.mark.parametrize("abimer, message", [
    (lambda df: df.drop(columns="note_visibilite"), "colonnes manquantes"),
    (lambda df: pd.concat([df, df.head(1)]), "en double"),
    (lambda df: df.assign(indice_citiz=[80.0, 140.0, 60.0]), "hors de"),
])
def test_tables_abimees(abimer, message):
    with pytest.raises(cc.ErreurCriteres, match=message):
        cc.lire_criteres({"criteres_citiz": abimer(table_criteres())})


def test_lecture_d_une_copie_locale(tmp_path):
    (tmp_path / "citiz").mkdir()
    table_criteres().to_parquet(tmp_path / "citiz" / "criteres_citiz.parquet", index=False)
    d = cc.lire_dossier(tmp_path)
    assert list(d.criteres.index) == ["A", "B", "C"] and d.places.empty
    assert cc.lire_dossier(tmp_path / "vide") is None
