"""Les calques de la carte : chacun dit d'où il vient et s'il est disponible.

On superpose les données de l'équipe (MSc 1, et MSc 2 et MSc 3 dès qu'ils ont livré) et les
résultats de l'optimisation (MSc 4). Un calque dont la source n'est pas encore livrée reste
listé, désactivé, avec le nom du rôle qui doit le fournir : on ne le recalcule pas ici.

Vie privée (décision 5) : un carreau sous le seuil est toujours dessiné en gris, sans aucune
information au survol, et toutes les populations affichées sont arrondies à la dizaine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
import pydeck as pdk
from scipy.spatial import cKDTree

from optim_mobilite import criteres
from optim_mobilite.scenarios import arrondi, nombre

# Charte Citiz (citiz.coop) : bleu-vert #32b4b5 et sa variante #20A4B0, vert #2FAC66,
# orange #EC6745, jaune #FBBA43, rouge #E63329, prune #514E98, gris #616060 / #C3C3C3, texte #202020.
CITIZ, CITIZ_FONCE = [50, 180, 181], [32, 164, 176]
COULEURS = {"citiz": CITIZ, "velo": [47, 172, 102], "bus": [236, 103, 69]}
GAGNE, GAGNE_SANS_TRANSPORT, SOUS_SEUIL = CITIZ, [251, 186, 67], [195, 195, 195]
PRUNE, GRIS, TEXTE = [81, 78, 152], [97, 96, 96], [32, 32, 32]
# 5 classes de même taille, du froid au chaud (décision 5), dans la palette Citiz
RAMPE = [[219, 244, 244], [50, 180, 181], [251, 186, 67], [236, 103, 69], [230, 51, 41]]
NOMS = {"citiz": "Citiz", "velo": "station vélo", "bus": "arrêt de bus"}


@dataclass
class Calque:
    cle: str
    libelle: str
    groupe: str
    defaut: bool
    # renvoie None si le calque est disponible, sinon la raison (qui doit le livrer)
    indisponible: Callable[[object], str | None] = lambda d: None
    legende: str = ""


def _sans_msc2_chaleur(d):
    return None if d.carreaux.options_pour_1000.notna().any() else "carte d'accessibilité pas encore disponible"


def _sans_msc2_servie(d):
    return None if d.population_servie is not None else "population servie par station pas encore disponible"


def _sans_msc3(d):
    return "score de potentiel pas encore disponible" if "score de potentiel" in d.provisoires else None


def _sans_contours(d):
    return None if d.communes is not None and "contour_geojson" in d.communes else "contours non copiés"


def _sans_usage(d):
    mesure = "occupation_24h" in d.stations and d.stations.occupation_24h.notna().any()
    return None if mesure else "usage mesuré pas encore disponible"


def _sans_places(d):
    return None if d.places is not None and len(d.places) else "places proposées pas encore disponibles"


def _sans_arbres(d):
    return None if d.arbres is not None and len(d.arbres) else "carte des arbres pas encore disponible"


CALQUES = [
    Calque("proposees", "Stations proposées (cercles de 400 m)", "Recommandation", True,
           legende="numéro = rang de priorité ; cercle = 5 min à pied"),
    Calque("gagnes", "Habitants nouvellement desservis", "Recommandation", True,
           legende="bleu-vert : gagnés ; jaune : gagnés qui n'avaient aucun transport"),
    Calque("potentiel", "Zones à potentiel (valeur de chaque emplacement)", "Recommandation", False,
           legende="du turquoise clair (faible) au rouge (fort) : habitants qu'une station y gagnerait, "
                   "multipliés par le score choisi (modèle ou vos critères)"),
    Calque("places", "Places proposées (parking sans arbre à moins de 10 m)", "Recommandation", True, _sans_places,
           "losange prune : la place précise, avec son adresse"),
    Calque("arbres", "Arbres autour des stations proposées", "Recommandation", False, _sans_arbres,
           "point vert : un arbre à moins de 400 m d'une station proposée"),
    Calque("citiz", "Stations Citiz existantes", "Offre de transport existante", True),
    Calque("usage", "Usage mesuré des stations Citiz", "Offre de transport existante", False, _sans_usage,
           "part du temps où les voitures sont en location : gris sous 5 %, bleu-vert autour de la moyenne, "
           "rouge au-dessus de 70 %"),
    Calque("velo", "Stations VélôToulouse", "Offre de transport existante", False),
    Calque("bus", "Arrêts de bus", "Offre de transport existante", False),
    Calque("lourd", "Arrêts de métro, tram, téléphérique, train", "Offre de transport existante", False),
    Calque("lignes", "Lignes de bus Tisséo", "Offre de transport existante", False),
    Calque("population", "Population par carreau", "Territoire", False,
           legende="5 classes de même taille"),
    Calque("communes", "Limites des communes", "Territoire", True, _sans_contours),
    Calque("chaleur", "Options pour 1 000 habitants (carte de chaleur)", "Analyses", False,
           _sans_msc2_chaleur, "du froid au chaud, 5 classes"),
    Calque("servie", "Population servie par station", "Analyses", False, _sans_msc2_servie,
           "taille du disque = habitants à 5 min"),
    Calque("score", "Score de potentiel Citiz", "Analyses", False, _sans_msc3,
           "du turquoise clair (faible) au rouge (fort)"),
]


def _critere_indisponible(cle):
    return lambda d: None if criteres.disponibles(d.carreaux)[cle] else "pas encore disponible"


# Chaque critère au choix est aussi une carte (sauf les communes et le modèle, déjà affichés autrement).
CALQUES += [
    Calque(f"crit_{c.cle}", c.libelle, "Habitants et quartiers", False, _critere_indisponible(c.cle),
           c.explication + (" Valeur du quartier, attribuée à chacun de ses carreaux." if c.echelle == "quartier" else ""))
    for c in criteres.CRITERES if c.cle not in ("communes", "modele")
]
COULEURS_QUARTIER = {"H": [50, 180, 181], "Z": [251, 186, 67], "A": [81, 78, 152]}
NOMS_QUARTIER = {"H": "quartier d'habitation", "Z": "commune non découpée", "A": "zone d'activité"}


def _format(cle: str, valeurs: pd.Series) -> pd.Series:
    """La valeur d'un critère, lisible dans une infobulle."""
    c = criteres.PAR_CLE[cle]
    if cle == "niveau_vie":
        return (valeurs.round(-2)).map(lambda v: f"{nombre(v)} € par an" if pd.notna(v) else "inconnu")
    if c.unite:
        return valeurs.map(lambda v: f"{nombre(v)} {c.unite}" if pd.notna(v) else "inconnu")
    if valeurs.dropna().between(0, 1).all() and cle not in ("voitures_menage",):
        return valeurs.map(lambda v: f"{v:.0%}" if pd.notna(v) else "inconnu")
    return valeurs.map(lambda v: f"{v:.2f}".rstrip("0").rstrip(".") if pd.notna(v) else "inconnu")


def classes(valeurs: pd.Series) -> np.ndarray:
    """Rang de classe (0 à 4) en 5 classes de même effectif ; une seule classe si tout est égal."""
    v = valeurs.to_numpy(dtype=float)
    if v.size == 0 or np.nanmax(v) == np.nanmin(v):
        return np.full(v.size, 2)
    rangs = pd.Series(v).rank(method="first", pct=True).to_numpy()
    return np.minimum((rangs * 5).astype(int), 4)


def _carreaux_colores(c: pd.DataFrame, valeurs: pd.Series, info: pd.Series, alpha=170) -> list[pdk.Layer]:
    """Carrés colorés en 5 classes pour les carreaux au-dessus du seuil ; gris, muets, en dessous."""
    visibles = c[~c.sous_seuil].assign(valeur=valeurs[~c.sous_seuil].to_numpy(), info=info[~c.sous_seuil].to_numpy())
    visibles = visibles[visibles.valeur.notna()]
    visibles = visibles.assign(couleur=[RAMPE[k] + [alpha] for k in classes(visibles.valeur)])
    return [
        pdk.Layer("PolygonLayer", c[c.sous_seuil][["carre"]], get_polygon="carre",
                  get_fill_color=SOUS_SEUIL + [120], stroked=False, pickable=False),
        pdk.Layer("PolygonLayer", visibles[["carre", "couleur", "info"]], get_polygon="carre",
                  get_fill_color="couleur", stroked=False, pickable=True),
    ]


def _nom(df: pd.DataFrame) -> pd.Series:
    """Le nom d'un arrêt ou d'une station, s'il est connu."""
    return df["nom"].fillna("").astype(str) if "nom" in df else pd.Series("", index=df.index)


def _points(df: pd.DataFrame, couleur, rayon_m: float, rayon_px: float, info: pd.Series | str) -> pdk.Layer:
    return pdk.Layer("ScatterplotLayer", df.assign(info=info)[["lon", "lat", "info"]], get_position=["lon", "lat"],
                     get_fill_color=couleur, get_radius=rayon_m, radius_min_pixels=rayon_px,
                     stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=0.5, pickable=True)


def couches(d, choix: set[str], r, structure, potentiel: pd.DataFrame, commune: str | None,
            places_proposees: pd.DataFrame | None = None) -> list[pdk.Layer]:
    """Les calques choisis, du fond vers le dessus. `places_proposees` : la place de chaque station Citiz
    proposée (rang, lat, lon, adresse, dist_arbre_m), à défaut les places de son carreau seulement."""
    c = d.carreaux
    st = d.stations
    sortie = []

    if "population" in choix:
        sortie += _carreaux_colores(c, c.population, "Population : ≈ " + pd.Series(arrondi(c.population)).astype(str)
                                    .map(lambda n: nombre(int(n))) + " habitants · " + c.commune)
    if "chaleur" in choix:
        sortie += _carreaux_colores(c, c.options_pour_1000, c.options_pour_1000.round(1).astype(str)
                                    + " options pour 1 000 habitants · " + c.commune)
    if "score" in choix:
        sortie += _carreaux_colores(c, c.score_citiz, "Score de potentiel " + c.score_citiz.round(2).astype(str)
                                    + " · " + c.commune)
    for cle in sorted(k[5:] for k in choix if k.startswith("crit_")):
        libelle = criteres.PAR_CLE[cle].libelle
        if cle == "type_quartier":
            types = c.type_iris.where(c.type_iris.isin(COULEURS_QUARTIER.keys()))
            q = c.assign(couleur=[COULEURS_QUARTIER.get(t, [195, 195, 195]) + [150] for t in types.fillna("")],
                         info="Type de quartier : " + types.map(NOMS_QUARTIER).fillna("inconnu") + " · " + c.commune)
            sortie.append(pdk.Layer("PolygonLayer", q[~q.sous_seuil][["carre", "couleur", "info"]], get_polygon="carre",
                                    get_fill_color="couleur", stroked=False, pickable=True))
            continue
        valeurs = criteres.valeur_critere(c, cle)
        if valeurs is None:
            continue
        sortie += _carreaux_colores(c, valeurs, libelle + " : " + _format(cle, valeurs) + " · " + c.commune)
    if "potentiel" in choix and len(potentiel):
        # un carreau candidat pour plusieurs types prend sa meilleure valeur
        meilleur = potentiel[potentiel.valeur > 0].sort_values("valeur").drop_duplicates("idx_carreau", keep="last")
        zone = c.iloc[meilleur.idx_carreau].assign(
            valeur_zone=meilleur.valeur.to_numpy(),
            info_zone=("Zone à potentiel · " + meilleur.type.map(NOMS) + " · ≈ "
                       + pd.Series(arrondi(meilleur.habitants)).map(lambda n: nombre(int(n))).to_numpy()
                       + " habitants à gagner · " + c.commune.iloc[meilleur.idx_carreau].to_numpy()),
        )
        sortie += _carreaux_colores(zone, zone.valeur_zone, zone.info_zone, alpha=150)
    if "gagnes" in choix:
        gagnes = c.iloc[structure.elements.loc[r.couverts, "idx_carreau"].drop_duplicates()]
        visibles = gagnes[~gagnes.sous_seuil].assign(
            couleur=lambda g: [GAGNE_SANS_TRANSPORT if n == 0 else GAGNE for n in g.nb_options_total],
            info=lambda g: ("Gagné · ≈ " + pd.Series(arrondi(g.population), index=g.index).map(lambda n: nombre(int(n)))
                            + " habitants · " + np.where(g.nb_options_total == 0, "aucun transport aujourd'hui",
                                                          "déjà une autre option") + " · " + g.commune),
        )
        sortie += [
            pdk.Layer("PolygonLayer", gagnes[gagnes.sous_seuil][["carre"]], get_polygon="carre",
                      get_fill_color=SOUS_SEUIL + [150], stroked=False, pickable=False),
            pdk.Layer("PolygonLayer", visibles[["carre", "couleur", "info"]], get_polygon="carre",
                      get_fill_color="couleur", stroked=False, opacity=0.5, pickable=True),
        ]
    if "communes" in choix and not _sans_contours(d):
        entites = [{"type": "Feature", "geometry": json.loads(g),
                    "properties": {"info": f"Commune : {n}", "choisie": n == commune}}
                   for n, g in zip(d.communes.nom, d.communes.contour_geojson)]
        sortie.append(pdk.Layer("GeoJsonLayer", {"type": "FeatureCollection", "features": entites},
                                stroked=True, filled=False, get_line_color=GRIS + [170],
                                get_line_width="properties.choisie ? 4 : 1", line_width_min_pixels=1,
                                pickable=False))
    if "lignes" in choix:
        chemins = [{"path": g[["lon", "lat"]].to_numpy().tolist()} for _, g in d.lignes_bus.groupby("id_ligne")]
        sortie.append(pdk.Layer("PathLayer", chemins, get_path="path", get_color=COULEURS["bus"] + [70],
                                width_min_pixels=1))
    if "bus" in choix:
        bus = st[st.type == "bus"]
        sortie.append(_points(bus, COULEURS["bus"] + [200], 25, 2, "Arrêt de bus · " + _nom(bus)))
    if "lourd" in choix:
        lourds = d.arrets[d.arrets.modes.str.split(",").map(lambda m: bool(set(m) - {"bus"}))]
        sortie.append(_points(lourds, TEXTE + [230], 60, 4, lourds.modes + " · " + _nom(lourds)))
    if "velo" in choix:
        velo = st[st.type == "velo"]
        sortie.append(_points(velo, COULEURS["velo"] + [200], 30, 2, "VélôToulouse · " + _nom(velo)))
    if "citiz" in choix and "usage" not in choix:
        citiz = st[st.type == "citiz"]
        sortie.append(_points(citiz, CITIZ_FONCE + [230], 60, 4, "Citiz existante · " + _nom(citiz)))
    if "usage" in choix and not _sans_usage(d):
        citiz = st[(st.type == "citiz") & st.occupation_24h.notna()]
        occ = citiz.occupation_24h.to_numpy()
        couleur = [SOUS_SEUIL + [240] if o < 0.05 else [230, 51, 41, 240] if o > 0.7 else CITIZ_FONCE + [240] for o in occ]
        voitures = citiz.nb_voitures.fillna(0).astype(int).astype(str) if "nb_voitures" in citiz else pd.Series("?", index=citiz.index)
        info = ("Citiz existante · " + _nom(citiz) + " · " + voitures + " voiture(s) · en location "
                + pd.Series([f"{o:.0%}" for o in occ], index=citiz.index) + " du temps (mesuré)")
        sortie.append(pdk.Layer("ScatterplotLayer", citiz.assign(couleur=couleur, info=info)[["lon", "lat", "couleur", "info"]],
                                get_position=["lon", "lat"], get_fill_color="couleur", get_radius=70,
                                radius_min_pixels=6, stroked=True, get_line_color=[255, 255, 255],
                                line_width_min_pixels=1, pickable=True))
    if "servie" in choix and d.population_servie is not None:
        servie = st.merge(d.population_servie, left_on="id", right_on="station_id")
        servie = servie.assign(rayon=np.sqrt(servie.population_servie.clip(lower=0)) * 4)
        sortie.append(pdk.Layer(
            "ScatterplotLayer",
            servie.assign(info="Population servie : ≈ " + pd.Series(arrondi(servie.population_servie))
                          .map(lambda n: nombre(int(n))) + " · " + _nom(servie))[["lon", "lat", "rayon", "info"]],
            get_position=["lon", "lat"], get_radius="rayon", get_fill_color=PRUNE + [110],
            stroked=True, get_line_color=PRUNE, line_width_min_pixels=1, pickable=True))
    proposees_citiz = r.liste[r.liste.type == "citiz"]
    if "arbres" in choix and not _sans_arbres(d) and len(proposees_citiz):
        # seulement les arbres à 400 m des stations proposées : la carte reste légère
        xy = c.set_index("idcar_200m").loc[proposees_citiz.idcar_200m, ["x_3035", "y_3035"]].to_numpy()
        proches = cKDTree(xy).query_ball_point(d.arbres[["x_3035", "y_3035"]].to_numpy(), 400, return_length=True) > 0
        arbres = d.arbres[proches]
        sortie.append(pdk.Layer("ScatterplotLayer", arbres.assign(info="Arbre")[["lon", "lat", "info"]],
                                get_position=["lon", "lat"], get_fill_color=COULEURS["velo"] + [160], get_radius=3,
                                radius_min_pixels=1.5, pickable=False))
    if "places" in choix and not _sans_places(d) and len(proposees_citiz):
        places = (places_proposees if places_proposees is not None
                  else proposees_citiz[["rang", "idcar_200m"]].merge(d.places, on="idcar_200m"))
        if len(places):
            adresse = places["adresse"].fillna("adresse inconnue").astype(str) if "adresse" in places else "adresse inconnue"
            arbre = (" · arbre le plus proche à " + places.dist_arbre_m.round(0).astype("Int64").astype(str) + " m"
                     if "dist_arbre_m" in places else "")
            places = places.assign(info="Place proposée · rang " + places.rang.astype(str) + " · " + adresse + arbre)
            sortie.append(pdk.Layer("ScatterplotLayer", places[["lon", "lat", "info"]], get_position=["lon", "lat"],
                                    get_fill_color=PRUNE + [235], get_radius=12, radius_min_pixels=5, stroked=True,
                                    get_line_color=[255, 255, 255], line_width_min_pixels=1.5, pickable=True))
    if "proposees" in choix and len(r.liste):
        liste = r.liste.astype({"equipement": str})
        liste = liste.assign(couleur=liste.type.map(COULEURS), texte=liste.rang.astype(str),
                             info="Proposée · rang " + liste.rang.astype(str) + " · " + liste.equipement + " · ≈ "
                             + pd.Series(arrondi(liste.population_nouvelle)).map(lambda n: nombre(int(n)))
                             + " habitants gagnés · " + liste.commune.astype(str))
        sortie += [
            pdk.Layer("ScatterplotLayer", liste, get_position=["lon", "lat"], get_radius=400, stroked=True,
                      filled=True, get_fill_color=[0, 0, 0, 0], get_line_color="couleur", line_width_min_pixels=2,
                      pickable=False),
            pdk.Layer("ScatterplotLayer", liste, get_position=["lon", "lat"], get_fill_color="couleur",
                      get_radius=60, radius_min_pixels=10, stroked=True, get_line_color=[255, 255, 255],
                      line_width_min_pixels=1.5, pickable=True),
            pdk.Layer("TextLayer", liste, get_position=["lon", "lat"], get_text="texte", get_size=12,
                      get_color=[255, 255, 255], font_weight=700, pickable=False),
        ]
    return sortie


def vue(d, liste: pd.DataFrame, commune: str | None) -> pdk.ViewState:
    """Recadre sur la commune choisie, sinon sur le gros des stations proposées, sinon sur Toulouse."""
    if commune:
        c = d.carreaux[d.carreaux.commune == commune]
        etendue = max(c.lon.max() - c.lon.min(), c.lat.max() - c.lat.min())
        return pdk.ViewState(longitude=float(c.lon.mean()), latitude=float(c.lat.mean()),
                             zoom=float(np.clip(9.3 - np.log2(max(etendue, 0.01) / 0.5), 9, 15)))
    if len(liste):
        # une station isolée à 30 km ne doit pas tout dézoomer
        lon, lat = liste.lon.quantile([0.1, 0.9]), liste.lat.quantile([0.1, 0.9])
        etendue = max(lon.iat[1] - lon.iat[0], lat.iat[1] - lat.iat[0])
        return pdk.ViewState(longitude=float(liste.lon.median()), latitude=float(liste.lat.median()),
                             zoom=float(np.clip(9.3 - np.log2(max(etendue, 0.02) / 0.5), 6, 13)))
    return pdk.ViewState(longitude=1.444, latitude=43.604, zoom=10.0)
