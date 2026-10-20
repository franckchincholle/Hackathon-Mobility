"""Assemble les tables de l'équipe en entrées de l'optimisation.

Ce module ne refait pas le travail des autres : il lit ce qu'ils ont livré et, pour ce qui
manque encore, met une version **provisoire**, signalée à l'écran, qui sera remplacée telle
quelle par leur livraison.

- Accessibilité (MSc 2, pas encore livrée) : calcul provisoire minimal, avec les règles des
  décisions 3 et 4 appliquées telles quelles (une option = une ligne distincte qui s'arrête
  à 400 m ou moins du centre du carreau, ou une station vélo ou Citiz ; les scooters en
  free-floating ne comptent pas) et un seuil de population provisoire.
- Score de potentiel (MSc 3, pas encore livré) : 1 partout ; la valeur d'un emplacement est
  alors sa seule population nouvellement desservie.
- Coûts (MBA, pas encore livrés) : MOCK_couts.

Ce qui est propre à MSc 4 et reste ici : savoir, pour chaque carreau, s'il a déjà une
station de chaque type à 400 m (sans quoi on ne peut définir ni les candidats ni la
population nouvellement desservie), et le tracé des lignes de bus où l'on peut ajouter un
arrêt.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree

from .contrat import Donnees
from .geo import vers_3035

RAYON = 400.0
# Variables des carreaux qui servent aux critères au choix (criteres.py), quand elles existent.
VARIABLES_CARREAUX = ("menages", "niveau_vie_moyen", "part_menages_pauvres", "logements_sociaux",
                      "menages_1_personne", "menages_logement_collectif", "age_25_39")
VARIABLES_QUARTIER = ("part_menages_sans_voiture", "voitures_par_menage", "commerces_alimentaires_5min",
                      "sante_5min", "enseignement_5min", "services_5min", "gares_5min")
# Seuil de population sous lequel un carreau est grisé (décision 5). Provisoire : MSc 2 le
# fixe ; 10 est la plus basse des valeurs qu'il doit tester (10, 20, 50, 100).
SEUIL_PROVISOIRE = 10
OPERATEURS = {"Citiz": "citiz", "VélôToulouse": "velo"}


def _dans_le_rayon(carreaux: pd.DataFrame, points: pd.DataFrame) -> sparse.csr_matrix:
    """Matrice creuse carreaux × points : 1 si le point est à RAYON ou moins du centre du carreau."""
    if points.empty:
        return sparse.csr_matrix((len(carreaux), 0))
    voisins = cKDTree(points[["x_3035", "y_3035"]].to_numpy()).query_ball_point(
        carreaux[["x_3035", "y_3035"]].to_numpy(), RAYON + 1e-6
    )
    lignes = np.repeat(np.arange(len(voisins)), [len(v) for v in voisins])
    colonnes = np.concatenate([np.asarray(v, dtype=np.int64) for v in voisins]) if lignes.size else lignes
    return sparse.csr_matrix((np.ones(lignes.size), (lignes, colonnes)), shape=(len(carreaux), len(points)))


def stations_existantes(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Citiz et vélos (stations_partagees) et arrêts desservis par au moins un bus (arrets)."""
    partagees = t["stations_partagees"]
    partagees = partagees[partagees.operateur.isin(OPERATEURS)]
    stations = pd.DataFrame({
        "id": partagees.station_id, "type": partagees.operateur.map(OPERATEURS),
        "nom": partagees.get("nom", ""), "x_3035": partagees.x_3035, "y_3035": partagees.y_3035,
        "lat": partagees.lat, "lon": partagees.lon,
    })
    arrets = t["arrets"]
    bus = arrets[arrets.modes.str.split(",").map(lambda m: "bus" in m)]
    stations_bus = pd.DataFrame({
        "id": bus.arret_id, "type": "bus", "nom": bus.get("nom", ""), "x_3035": bus.x_3035,
        "y_3035": bus.y_3035, "lat": bus.lat, "lon": bus.lon,
    })
    return pd.concat([stations, stations_bus], ignore_index=True)


def accessibilite_provisoire(t: dict[str, pd.DataFrame], carreaux: pd.DataFrame) -> pd.DataFrame:
    """nb_options_total selon la décision 3, en attendant la table de MSc 2.

    Les lignes sont comptées une seule fois par carreau, même si plusieurs de leurs arrêts
    sont dans le cercle ; s'y ajoutent les stations vélo et Citiz du cercle.
    """
    arrets = t["arrets"].reset_index(drop=True)
    al = t["arrets_lignes"]
    al = al[al.arret_id.isin(arrets.arret_id)]
    rang_arret = pd.Series(np.arange(len(arrets)), index=arrets.arret_id)
    codes_lignes, lignes_uniques = pd.factorize(al.ligne_id)
    arret_ligne = sparse.csr_matrix(
        (np.ones(len(al)), (rang_arret[al.arret_id].to_numpy(), codes_lignes)),
        shape=(len(arrets), len(lignes_uniques)),
    )
    lignes_proches = (_dans_le_rayon(carreaux, arrets) @ arret_ligne) > 0
    partagees = t["stations_partagees"]
    partagees = partagees[partagees.operateur.isin(OPERATEURS)]
    stations_proches = _dans_le_rayon(carreaux, partagees)
    nb = np.asarray(lignes_proches.sum(axis=1)).ravel() + np.asarray(stations_proches.sum(axis=1)).ravel()
    return pd.DataFrame({
        "idcar_200m": carreaux.idcar_200m,
        "nb_options": nb.astype(np.int64),
        "sous_seuil": carreaux.population < SEUIL_PROVISOIRE,
    })


def lignes_bus_tisseo(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Tracés (shapes.txt) des lignes de bus Tisséo (route_type 3), en EPSG:3035."""
    routes = t["tisseo_routes"]
    bus = set(routes.loc[routes.route_type == "3", "route_id"])
    trips = t["tisseo_trips"]
    formes = set(trips.loc[trips.route_id.isin(bus) & (trips.shape_id != ""), "shape_id"])
    s = t["tisseo_shapes"]
    s = s[s.shape_id.isin(formes)].sort_values(["shape_id", "shape_pt_sequence"])
    x, y = vers_3035(s.shape_pt_lon.to_numpy(), s.shape_pt_lat.to_numpy())
    return pd.DataFrame({"id_ligne": s.shape_id.to_numpy(), "ordre": s.shape_pt_sequence.to_numpy(),
                         "x_3035": x, "y_3035": y})


def compter_arbres(arbres: pd.DataFrame, carreaux: pd.DataFrame, avertissements: list) -> np.ndarray:
    """Nombre d'arbres dans chaque carreau de 200 m (demande de Citiz : stationnement dégagé)."""
    if {"x_3035", "y_3035"} <= set(arbres.columns):
        x, y = pd.to_numeric(arbres.x_3035, errors="coerce"), pd.to_numeric(arbres.y_3035, errors="coerce")
    elif {"lat", "lon"} <= set(arbres.columns):
        x, y = vers_3035(pd.to_numeric(arbres.lon, errors="coerce").to_numpy(),
                         pd.to_numeric(arbres.lat, errors="coerce").to_numpy())
    else:
        avertissements.append("Table des arbres sans coordonnées (lat/lon ou x_3035/y_3035) : critère ignoré")
        return np.full(len(carreaux), np.nan)
    points = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    points = points[np.isfinite(points).all(axis=1)]
    # un arbre est dans le carreau dont le centre est le plus proche, à moins d'une demi-diagonale
    d, idx = cKDTree(carreaux[["x_3035", "y_3035"]].to_numpy()).query(points, distance_upper_bound=100 * np.sqrt(2))
    return np.bincount(idx[np.isfinite(d)], minlength=len(carreaux)).astype(float)


def _enumeration(mots: list[str]) -> str:
    """« vélo et bus », « Citiz, vélo et bus »."""
    return mots[0] if len(mots) == 1 else ", ".join(mots[:-1]) + " et " + mots[-1]


def _nom_commune(codes: str, zone: dict[str, str]) -> str:
    """Le carreau à cheval sur plusieurs communes prend la première qui est dans la zone."""
    liste = codes.split(",")
    return next((zone[c] for c in liste if c in zone), liste[0])


def assembler(t: dict[str, pd.DataFrame], dossier: Path) -> Donnees:
    sources, provisoires, avertissements = {}, [], []
    car = t["carreaux"]
    zone = dict(zip(t["zone_communes"].code_commune, t["zone_communes"].nom))
    carreaux = pd.DataFrame({
        "idcar_200m": car.idcar_200m, "x_3035": car.x_3035, "y_3035": car.y_3035,
        "lat": car.lat, "lon": car.lon, "population": car.population,
        "commune": car.codes_communes.map(lambda c: _nom_commune(c, zone)),
        **{v: pd.to_numeric(car[v], errors="coerce").to_numpy() for v in VARIABLES_CARREAUX if v in car},
    }).reset_index(drop=True)
    # Libellés affichés à l'écran : ils décrivent les données, pas qui les a produites.
    # code et nom IRIS de chaque carreau, s'ils sont disponibles
    if "carreaux_variables" in t:
        codes = dict(zip(t["carreaux_variables"].idcar_200m, t["carreaux_variables"].code_iris))
        noms_iris = {c: n for c, n in zip(t["iris"].code_iris, t["iris"].nom_iris) if n} if "iris" in t else {}

        def nom_iris(code: str) -> str:
            # une commune non découpée par l'INSEE forme un seul IRIS, au code en ...0000 et sans nom
            if not code:
                return ""
            return noms_iris.get(code) or ("commune entière" if code.endswith("0000") else code)

        carreaux["iris"] = [nom_iris(codes.get(i, "")) for i in carreaux.idcar_200m]
        variables = t["carreaux_variables"].drop_duplicates("idcar_200m").set_index("idcar_200m")
        for v in VARIABLES_QUARTIER:
            if v in variables:
                carreaux[v] = pd.to_numeric(carreaux.idcar_200m.map(variables[v]), errors="coerce").to_numpy()
        if "iris" in t and "type_iris" in t["iris"]:
            types = dict(zip(t["iris"].code_iris, t["iris"].type_iris.fillna("").astype(str)))
            carreaux["type_iris"] = [types.get(codes.get(i, ""), "") for i in carreaux.idcar_200m]
    arbres = None
    if "arbres" in t:
        carreaux["nb_arbres"] = compter_arbres(t["arbres"], carreaux, avertissements)
        if {"lat", "lon"} <= set(t["arbres"].columns):
            arbres = t["arbres"][["lat", "lon"]].apply(pd.to_numeric, errors="coerce").dropna()
            arbres["x_3035"], arbres["y_3035"] = vers_3035(arbres.lon.to_numpy(), arbres.lat.to_numpy())
    sources["population, arrêts, stations"] = "INSEE Filosofi 2021 (carreaux 200 m), GTFS Tisséo, liO et TER, GBFS VélôToulouse et Citiz"

    # Une station de chaque type à 400 m : de quoi définir candidats et population nouvellement desservie.
    stations = stations_existantes(t)
    for type_ in ("citiz", "velo", "bus"):
        proches = _dans_le_rayon(carreaux, stations[stations.type == type_])
        carreaux[f"a_option_{type_}"] = np.asarray(proches.sum(axis=1)).ravel() > 0

    if "accessibilite" in t:
        acc = t["accessibilite"]
        sources["accessibilité"] = "options à 5 min par carreau (version finale)"
    else:
        acc = accessibilite_provisoire(t, carreaux)
        sources["accessibilité"] = f"calcul provisoire (seuil de diffusion : {SEUIL_PROVISOIRE} habitants)"
        provisoires.append("accessibilité")
    colonnes_acc = ["idcar_200m", "nb_options", "sous_seuil"] + [c for c in ("iris", "options_pour_1000") if c in acc]
    if "iris" in acc and "iris" in carreaux:
        carreaux = carreaux.drop(columns="iris")  # l'IRIS livré avec l'accessibilité prime
    carreaux = carreaux.merge(acc[colonnes_acc], on="idcar_200m", how="left")
    if carreaux.nb_options.isna().any():
        avertissements.append(f"{int(carreaux.nb_options.isna().sum())} carreaux sans accessibilité : 0 option appliquée")
    carreaux["nb_options_total"] = carreaux.pop("nb_options").fillna(0).astype(np.int64)
    carreaux["sous_seuil"] = carreaux.sous_seuil.fillna(True).astype(bool)
    if "iris" not in carreaux:
        carreaux["iris"] = ""
    carreaux["iris"] = carreaux.iris.fillna("").astype(str)
    if "options_pour_1000" not in carreaux:
        carreaux["options_pour_1000"] = np.nan  # carte de chaleur de MSc 2, pas encore livrée

    # Score de l'emplacement (décision 7) ; 1 tant que MSc 3 n'a pas livré.
    if "scores_potentiel" in t:
        carreaux = carreaux.merge(t["scores_potentiel"][["idcar_200m", "score_potentiel"]], on="idcar_200m", how="left")
        manquants = carreaux.score_potentiel.isna() & ~carreaux.a_option_citiz
        if manquants.any():
            mediane = float(t["scores_potentiel"].score_potentiel.median())
            avertissements.append(f"{int(manquants.sum())} carreaux sans station Citiz et sans score : médiane {mediane:.2f}")
            carreaux["score_potentiel"] = carreaux.score_potentiel.fillna(mediane)
        carreaux["score_citiz"] = carreaux.pop("score_potentiel").fillna(0.0)
        carreaux["score_modele"] = carreaux.score_citiz  # pour en faire un critère au choix
        sources["score de potentiel"] = "modèle prédictif (ressemblance avec les carreaux équipés de Citiz)"
    else:
        carreaux["score_citiz"] = 1.0
        sources["score de potentiel"] = "pas encore intégré : la valeur d'un emplacement est sa population nouvellement desservie"
        provisoires.append("score de potentiel")
    carreaux["score_velo"] = carreaux["score_bus"] = 1.0  # décision 11 : sans modèle dédié

    # Ce que Citiz a demandé en plus : les raisons du score (modèle v2), ses 8 critères, l'usage mesuré.
    # L'occupation prévue par le modèle v2 n'est pas reprise : sur 30 h de relevés, elle ne prédit
    # presque rien (modele/RESULTATS.md) ; une nouvelle station compte avec l'usage moyen mesuré.
    if "scores_v2" in t:
        v2 = t["scores_v2"]
        garder = [c for c in ("classe", "raison_1", "raison_2", "raison_3") if c in v2]
        carreaux = carreaux.merge(v2.drop_duplicates("idcar_200m")[["idcar_200m", *garder]], on="idcar_200m", how="left")
        sources["raisons du score"] = "modèle v2, appris sur les 14 autres réseaux Citiz et testé à l'aveugle sur Toulouse"
    if "criteres_citiz" in t:
        cc = t["criteres_citiz"].drop_duplicates("idcar_200m")
        nouvelles = [c for c in cc.columns if c != "idcar_200m" and c not in carreaux]
        carreaux = carreaux.merge(cc[["idcar_200m", *nouvelles]], on="idcar_200m", how="left")
        sources["critères Citiz"] = "les 8 critères de l'emplacement idéal, mesurés par carreau (INSEE, GTFS, OSM, arbres)"
    if "usage_stations" in t:
        u = t["usage_stations"].drop_duplicates("station_cle")
        colonnes_u = [c for c in ("occupation_24h", "occupation_jour", "nb_voitures") if c in u]
        stations = stations.merge(u[["station_cle", *colonnes_u]].rename(columns={"station_cle": "id"}),
                                  on="id", how="left")
        sources["usage mesuré"] = "flux GBFS Citiz relevé toutes les 10 minutes (citiz_releves)"

    couts = t["couts"]
    noms = {"citiz": "Citiz", "velo": "vélo", "bus": "bus"}
    livres = [noms[c] for c in couts.loc[~couts.mock, "type"]]
    en_mock = [noms[c] for c in couts.loc[couts.mock, "type"]]
    sources["coûts"] = " ; ".join(
        ([f"{_enumeration(livres)} : coût complet par station et par an, sources publiques"] if livres else [])
        + ([f"{_enumeration(en_mock)} : estimation provisoire"] if en_mock else [])
    )
    if en_mock:
        provisoires.append(f"coûts {_enumeration(en_mock)}")

    return Donnees(
        carreaux=carreaux,
        stations=stations,
        lignes_bus=lignes_bus_tisseo(t),
        couts=couts.set_index("type"),
        dossier=dossier,
        communes=t["zone_communes"],
        arrets=t["arrets"],
        population_servie=t.get("population_servie"),
        places=t.get("places_candidates"),
        arbres=arbres,
        sources=sources,
        provisoires=provisoires,
        avertissements=avertissements,
    )
