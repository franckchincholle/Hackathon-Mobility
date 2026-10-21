"""Démo : choisir un budget, obtenir la carte et la liste priorisée des emplacements.

    streamlit run app/streamlit_app.py

Tout est lu en local au démarrage puis gardé en cache : aucun téléchargement de données
pendant la démo. Les réglages se passent aussi par l'URL (?budget=citiz&montant=500000&alpha=1
&fourchette=defaut).
"""

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carte import CALQUES, couches, vue  # noqa: E402
from optim_mobilite import couverture, criteres, criteres_citiz, equite, impact, rentabilite, scenarios  # noqa: E402
from optim_mobilite.contrat import charger_donnees  # noqa: E402
from optim_mobilite.geo import vers_wgs84  # noqa: E402
from optim_mobilite.scenarios import arrondi, euros, nombre  # noqa: E402

st.set_page_config(page_title="Où installer les prochaines stations ?", page_icon="🚏", layout="wide")

BUDGETS = {"citiz": "Citiz (autopartage)", "collectivite": "Collectivité (vélo + bus)"}
MONTANTS = {"citiz": (500_000, 1_000_000, 25_000), "collectivite": (1_000_000, 2_000_000, 50_000)}


# ---------- données et calculs, mis en cache ----------

# Les données sont relues sur Fabric toutes les 10 minutes (ou par le bouton « Mettre à jour ») ;
# chaque calcul en cache porte la version des données (`version`), pour ne jamais mélanger une
# couverture calculée sur l'ancienne version avec les nouvelles données. Les paramètres qui
# commencent par « _ » ne servent pas de clé de cache (règle de Streamlit).
@st.cache_resource(ttl=600, show_spinner="Lecture des données sur Fabric…")
def donnees():
    d = charger_donnees()
    # les quatre coins de chaque carreau de 200 m, pour le dessiner comme un vrai carré
    x, y = d.carreaux.x_3035.to_numpy(), d.carreaux.y_3035.to_numpy()
    coins = [vers_wgs84(x + dx, y + dy) for dx, dy in ((-100, -100), (100, -100), (100, 100), (-100, 100))]
    lon, lat = np.stack([c[0] for c in coins], 1), np.stack([c[1] for c in coins], 1)
    d.carreaux["carre"] = list(np.stack([lon, lat], 2).round(6).tolist())
    d.lignes_bus["lon"], d.lignes_bus["lat"] = vers_wgs84(d.lignes_bus.x_3035.to_numpy(), d.lignes_bus.y_3035.to_numpy())
    return d


@st.cache_resource(show_spinner="Précalcul de la couverture…", max_entries=8)
def structure(_d, version: str, budget: str, types: tuple):
    return couverture.construire(_d, budget, types)


@st.cache_data(show_spinner="Calcul du score selon vos critères…", max_entries=32)
def score_choisi(version, reglage: str):
    """Score par carreau selon les critères choisis ; None = modèle prédictif (le défaut)."""
    if reglage == "modele":
        return None
    if reglage == "citiz8":  # l'indice Citiz : moyenne des 8 critères, de 0 à 100 ; neutre si inconnu
        return (d.carreaux.indice_citiz.fillna(50) / 100).to_numpy()
    return criteres.score(d.carreaux, criteres.Reglage.decoder(reglage))


def euros_signe(montant: float) -> str:
    return ("+" if montant > 0 else "-" if montant < 0 else "") + euros(abs(montant))


def entre(fourchette: tuple[float, float], unite: str = "") -> str:
    """« 212 à 363 » : une fourchette de l'ADEME, arrondie."""
    return f"{nombre(fourchette[0])} à {nombre(fourchette[1])}{unite}"


@st.cache_resource(max_entries=4)
def criteres_de_citiz(version: str):
    """Les 8 critères de Citiz et les places, au format de criteres_citiz.py ; None s'ils manquent."""
    if "indice_citiz" not in d.carreaux:
        return None
    colonnes = [c for c in criteres_citiz.COLONNES_CRITERES if c in d.carreaux]
    places = (d.places.drop_duplicates("idcar_200m").set_index("idcar_200m") if d.places is not None
              else pd.DataFrame(columns=criteres_citiz.COLONNES_PLACES[1:]))
    return criteres_citiz.CriteresCitiz(d.carreaux[colonnes].drop_duplicates("idcar_200m").set_index("idcar_200m"),
                                        places)


COLONNES_PLACE = ["rang", "idcar_200m", "lat", "lon", "adresse", "dist_arbre_m", "distance_centre_m"]


def places_des_stations(cc, liste: pd.DataFrame) -> pd.DataFrame:
    """La place de chaque station Citiz proposée : dans son carreau, sinon la plus proche à moins de 300 m."""
    if cc is None:
        return pd.DataFrame(columns=COLONNES_PLACE)
    centres = d.carreaux.drop_duplicates("idcar_200m").set_index("idcar_200m")[["x_3035", "y_3035"]]
    lignes = []
    for rang, idcar in liste.loc[liste.type == "citiz", ["rang", "idcar_200m"]].itertuples(index=False):
        x, y = centres.loc[idcar]
        place = criteres_citiz.place_la_plus_proche(cc, idcar, float(x), float(y))
        if place:
            lignes.append({"rang": rang, "idcar_200m": idcar, **{k: place.get(k) for k in COLONNES_PLACE[2:]}})
    return pd.DataFrame(lignes, columns=COLONNES_PLACE)


def resoudre(budget, types, montant, alpha, fourchette, reglage):
    return scenarios.resoudre(d, structure(d, d.lecture, budget, types), montant, alpha, fourchette,
                              score_choisi(d.lecture, reglage))


@st.cache_data(show_spinner="Calcul de la courbe…", max_entries=32)
def courbe(version, budget, types, alpha, fourchette, maximum, pas, reglage):
    budgets = np.arange(0, maximum + pas, pas)
    return scenarios.courbe(d, structure(d, version, budget, types), alpha, fourchette, budgets,
                            score_choisi(version, reglage))


@st.cache_data(show_spinner="Calcul des zones à potentiel…", max_entries=32)
def potentiel_candidats(version, budget, types, alpha, reglage):
    return scenarios.potentiel_candidats(d, structure(d, version, budget, types), alpha, score_choisi(version, reglage))


@st.cache_data(max_entries=32)
def comparer_alpha(version, budget, types, montant, fourchette, reglage):
    return scenarios.comparer_alpha(d, structure(d, version, budget, types), montant, fourchette,
                                    score_carreaux=score_choisi(version, reglage))


def robustesse(budget, types, montant, alpha, reglage):
    return scenarios.robustesse(d, structure(d, d.lecture, budget, types), montant, alpha,
                                score_choisi(d.lecture, reglage))


# ---------- réglages : barre latérale, valeurs initiales lisibles dans l'URL ----------

def parametre(nom, defaut, conversion=str):
    try:
        return conversion(st.query_params.get(nom, defaut))
    except ValueError:
        return defaut


d = donnees()
if d.est_provisoire:
    st.warning(
        "**Résultats provisoires** : population, arrêts et stations réels de Toulouse Métropole ; "
        f"encore en cours de finalisation : {', '.join(d.provisoires)}.",
        icon=":material/science:",
    )
for message in d.avertissements:
    st.info(message, icon=":material/cloud_off:" if message.startswith("Lecture en direct") else None)

with st.sidebar:
    st.header("Scénario")
    cles = list(BUDGETS)
    budget = st.radio("Budget", cles, format_func=BUDGETS.get,
                      index=cles.index(parametre("budget", "citiz")) if parametre("budget", "citiz") in cles else 0)
    if budget == "collectivite":
        types = tuple(t for t, nom in (("velo", "Stations vélo"), ("bus", "Arrêts de bus (sur lignes existantes)"))
                      if st.checkbox(nom, value=True))
        if not types:
            st.error("Choisir au moins un équipement.")
            st.stop()
    else:
        types = ("citiz",)
    defaut, maximum, pas = MONTANTS[budget]
    montant = 1_000 * st.slider("Budget annuel en k€ (coût complet d'une station par an)", 0, maximum // 1_000,
                                int(parametre("montant", defaut, float)) // pas * pas // 1_000, pas // 1_000,
                                format="%d k€")
    fourchette = st.radio("Hypothèse de coût d'une station", scenarios.FOURCHETTES, horizontal=True,
                          index=scenarios.FOURCHETTES.index(parametre("fourchette", "defaut"))
                          if parametre("fourchette", "defaut") in scenarios.FOURCHETTES else 1,
                          format_func={"bas": "bas", "defaut": "par défaut", "haut": "haut"}.get,
                          help="Coût complet d'une station et par an. « Par défaut » est l'estimation retenue ; bas et haut "
                               "servent à vérifier que la liste reste la même si les coûts réels diffèrent.")
    st.markdown("**Priorité aux habitants sans transport**")
    alpha = st.slider(
        "Priorité aux habitants sans transport", 0.0, equite.ALPHA_MAX, parametre("alpha", 1.0, float), 0.25,
        label_visibility="collapsed",
        format="%.2f",
        help="Faut-il toucher le plus de monde possible, ou d'abord ceux qui n'ont rien ? "
             "À 0, chaque habitant compte pareil. Plus on monte, plus un habitant sans bus, tram, métro, train, "
             "vélo ni Citiz à 5 minutes de chez lui compte lourd dans le choix des emplacements.",
    )
    st.caption(
        "**0** : toucher le plus d'habitants possible, où qu'ils soient.  \n"
        f"**{equite.ALPHA_MAX:g}** : servir d'abord ceux qui n'ont aucun transport à 5 min, quitte à toucher "
        "un peu moins de monde au total.  \n"
        f"Réglage actuel : un habitant sans transport compte **{1 + alpha:g} fois** plus qu'un habitant "
        f"déjà bien desservi."
    )
    effet_equite = st.empty()  # rempli plus bas, une fois le scénario calculé
    st.divider()
    st.markdown("**Zones à potentiel : sur quoi se baser ?**")
    indice_dispo = "indice_citiz" in d.carreaux and d.carreaux.indice_citiz.notna().any()
    bases = ["modele"] + (["citiz8"] if indice_dispo else []) + ["criteres"]
    base_demandee = parametre("score", "modele")
    base_score = st.radio(
        "Zones à potentiel : sur quoi se baser ?", bases, label_visibility="collapsed",
        index=bases.index(base_demandee) if base_demandee in bases else 0,
        format_func={"modele": "Modèle prédictif", "citiz8": "Les 8 critères de Citiz", "criteres": "Mes critères"}.get,
        help="Le modèle prédictif estime le potentiel Citiz d'un emplacement d'après les quartiers où Citiz "
             "est déjà installé. « Les 8 critères de Citiz » prend la moyenne des 8 critères de l'emplacement "
             "idéal que Citiz nous a donnés. « Mes critères » remplace ce score par les seuls critères que vous "
             "cochez, avec vos poids : la carte des zones à potentiel et la liste des stations en dépendent alors.",
    )
    if base_score == "criteres":
        demande = criteres.Reglage.decoder(parametre("criteres", "densite:1"))
        dispo = criteres.disponibles(d.carreaux)
        actifs, communes_choisies = {}, ()
        groupes = list(dict.fromkeys(c.groupe for c in criteres.CRITERES))
        for groupe in groupes:
            du_groupe = [c for c in criteres.CRITERES if c.groupe == groupe]
            with st.expander(groupe, expanded=any(c.cle in demande.actifs for c in du_groupe)):
                for c in du_groupe:
                    coche = st.checkbox(c.libelle, value=c.cle in demande.actifs and dispo[c.cle],
                                        disabled=not dispo[c.cle], key=f"critere_{c.cle}",
                                        help=c.explication if dispo[c.cle] else f"{c.explication} Pas encore disponible.")
                    if not coche:
                        continue
                    poids_defaut, sens_defaut = demande.actifs.get(c.cle, (1, c.sens_defaut))
                    colonne_poids, colonne_sens = st.columns([1, 1.3]) if c.reglable else (st.container(), None)
                    poids = colonne_poids.select_slider("Poids", [1, 2, 3], value=poids_defaut, key=f"poids_{c.cle}",
                                                        format_func=lambda p: f"×{p}")
                    sens = sens_defaut
                    if c.reglable:
                        sens = colonne_sens.radio("Favoriser", ["haut", "bas"], index=0 if sens_defaut == "haut" else 1,
                                                  format_func=c.sens.get, key=f"sens_{c.cle}")
                    if c.cle == "communes":
                        communes_choisies = tuple(st.multiselect("Communes", sorted(d.carreaux.commune.unique()),
                                                                 default=list(demande.communes), key="communes_choisies"))
                    actifs[c.cle] = (poids, sens)
        choix_criteres = criteres.Reglage(actifs, communes_choisies)
        reglage = choix_criteres.encoder() or "aucun"
        if actifs:
            st.caption(f"Score = {choix_criteres.resume()}.")
        else:
            st.warning("Aucun critère coché : seule la population compte.")
    elif base_score == "citiz8":
        reglage = "citiz8"
        st.caption("Score = indice Citiz, la moyenne des 8 critères de l'emplacement idéal : transports collectifs, "
                   "densité urbaine, mixité habitat/activité, accessibilité/circulation, simple pour stationner, "
                   "taux de motorisation faible, visible, arbres à distance.")
    else:
        reglage = "modele"
    st.divider()
    st.caption(f"Source : {d.lecture}.")
    if st.button("Mettre à jour les données", icon=":material/refresh:",
                 help="Relit tout de suite les tables sur Fabric (sinon, automatiquement toutes les 10 minutes)."):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()
    fond = st.toggle("Plan des rues sous la carte", value=parametre("fond", "1") != "0",
                     help="Affiche les rues, les quartiers et les noms de lieux sous les données. Ce plan est "
                          "chargé depuis internet (OpenStreetMap, via Carto) : si la connexion est mauvaise, "
                          "désactivez-le, la carte reste lisible sur fond blanc.")
    communes = sorted(d.carreaux.commune.unique())
    commune = st.selectbox("Recadrer sur une commune", ["Toute la métropole"] + communes,
                           index=(communes.index(parametre("commune", "")) + 1) if parametre("commune", "") in communes else 0)
    commune = None if commune == "Toute la métropole" else commune
    with st.expander("Calques de la carte", expanded=False):
        demandes = set(parametre("calques", "").split(",")) - {""}
        choix = set()
        groupe = None
        for calque in CALQUES:
            if calque.groupe != groupe:
                groupe = calque.groupe
                st.markdown(f"**{groupe}**")
            raison = calque.indisponible(d)
            defaut = (calque.cle in demandes) if demandes else (calque.defaut or calque.cle in types)
            if st.checkbox(calque.libelle, value=defaut and not raison, disabled=bool(raison),
                           help=raison or calque.legende or None, key=f"calque_{calque.cle}"):
                choix.add(calque.cle)

r = resoudre(budget, types, float(montant), alpha, fourchette, reglage)
rob = robustesse(budget, types, float(montant), alpha, reglage)
cc = criteres_de_citiz(d.lecture)
places_proposees = places_des_stations(cc, r.liste)
k = r.indicateurs
if alpha > 0:
    k0 = resoudre(budget, types, float(montant), 0.0, fourchette, reglage).indicateurs
    total = int(arrondi(k["habitants_nouveaux"] - k0["habitants_nouveaux"]))
    sans = int(arrondi(k["habitants_sans_transport_nouveaux"] - k0["habitants_sans_transport_nouveaux"]))
    effet_equite.info(
        f"**Effet de ce réglage** (comparé à 0) : {'+' if total > 0 else ''}{nombre(total)} habitants touchés "
        f"au total, dont {'+' if sans > 0 else ''}{nombre(sans)} parmi ceux qui n'ont aucun transport.",
        icon=":material/balance:",
    )

# ---------- en-tête : phrase-choc et indicateurs ----------

st.title("Où installer les prochaines stations ?")
st.markdown(f"#### {scenarios.phrase_choc(rob)}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Stations proposées", k["nb_stations"])
c2.metric("Coût total", euros(k["cout_total"]), f"budget {euros(montant)}", delta_color="off", delta_arrow="off")
c3.metric("Habitants nouvellement desservis", nombre(arrondi(k["habitants_nouveaux"])))
c4.metric("dont sans aucun transport aujourd'hui", nombre(arrondi(k["habitants_sans_transport_nouveaux"])))
c5.metric("Coût par habitant gagné (par an)",
          f"{k['cout_total'] / k['habitants_nouveaux']:.0f} €" if k["habitants_nouveaux"] else "—")
# Usage de référence d'une nouvelle station : l'occupation mesurée de nos voitures de la métropole
# (pondérée par voiture, arrondie au point), sinon la moyenne du réseau. En-tête et business plan
# partent du même chiffre.
existantes_citiz = d.stations[d.stations.type == "citiz"]
usage_mesure = "occupation_24h" in existantes_citiz and existantes_citiz.occupation_24h.notna().any()
mesurees = existantes_citiz.dropna(subset=["occupation_24h"]) if usage_mesure else existantes_citiz.iloc[:0]
occupation_reference = round(float(np.average(
    mesurees.occupation_24h, weights=mesurees.nb_voitures.fillna(1) if "nb_voitures" in mesurees else None))
    if usage_mesure else rentabilite.OCCUPATION_RESEAU, 2)
if budget == "citiz" and k["nb_stations"]:
    env = k["environnement"]
    recette_reference = k["voitures_ajoutees"] * float(rentabilite.recette_voiture(occupation_reference))
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Recette prévue par an", euros(recette_reference), f"à {occupation_reference:.0%} d'usage, notre moyenne",
              delta_color="off", delta_arrow="off")
    b2.metric("Rentable au-dessus de", f"{rentabilite.occupation_equilibre(scenarios.cout_station(d.couts, 'citiz', fourchette)):.0%} d'usage",
              f"nos voitures : {occupation_reference:.0%} (mesuré)" if usage_mesure else None, delta_color="off", delta_arrow="off")
    b3.metric("Investissement d'ouverture", euros(k["investissement"]), f"{k['voitures_ajoutees']} voitures",
              delta_color="off", delta_arrow="off")
    b4.metric("Voitures personnelles en moins", entre(env["voitures_en_moins"]), "ADEME 2022", delta_color="off", delta_arrow="off")
    b5.metric("CO2 évité par an", entre(env["tonnes_co2_evitees"], " t"), "ADEME 2022", delta_color="off", delta_arrow="off")

(onglet_carte, onglet_business, onglet_impact, onglet_courbe, onglet_equite, onglet_robustesse,
 onglet_methode) = st.tabs(["Carte et liste", "Business plan", "Impact", "Budget → habitants", "Équité",
                            "Robustesse des coûts", "Méthode"])

# ---------- carte et liste ----------

with onglet_carte:
    liste = r.liste.astype({"equipement": str, "commune": str, "iris": str})
    if liste.empty:
        st.info(f"Aucune station ne rentre dans ce budget : une station coûte au moins "
                f"{euros(min(scenarios.cout_station(d.couts, t, fourchette) for t in types))}.")
    potentiel = potentiel_candidats(d.lecture, budget, types, alpha, reglage) if "potentiel" in choix else pd.DataFrame()
    st.pydeck_chart(
        pdk.Deck(
            layers=couches(d, choix, r, structure(d, d.lecture, budget, types), potentiel, commune, places_proposees),
            initial_view_state=vue(d, liste, commune),
            map_provider="carto" if fond else None,
            map_style=None,  # fond Carto accordé au thème de Streamlit
            tooltip={"html": "{info}"},
        ),
        height=600,
    )
    legendes = [f"**{c.libelle}** : {c.legende}" for c in CALQUES if c.cle in choix and c.legende]
    st.caption(" · ".join(legendes + ["gris : carreaux sous le seuil de diffusion, jamais détaillés"]))

    tableau = pd.DataFrame({
        "Rang": liste.rang,
        "Équipement": liste.equipement,
        "Commune": liste.commune,
        "IRIS": liste.iris,
        ("Score (mes critères)" if reglage != "modele" else "Score du modèle"): liste.score.round(2),
        "Coût par an": liste.cout.map(euros),
        "Coût bas – haut": liste.cout_bas.map(euros).astype(str) + " – " + liste.cout_haut.map(euros).astype(str),
        "Habitants nouvellement desservis": arrondi(liste.population_nouvelle),
        "dont sans transport": arrondi(liste.dont_sans_transport),
        "Valeur (pondérée)": liste.valeur.round(0).astype(int),
        "Coût cumulé": liste.cout_cumule.map(euros),
        "Habitants cumulés": arrondi(liste.population_cumulee),
    })
    # colonnes vides tant qu'elles ne sont pas disponibles : IRIS, score de potentiel
    if not liste.iris.astype(bool).any():
        tableau = tableau.drop(columns="IRIS")
    if "score de potentiel" in d.provisoires and reglage == "modele":
        tableau = tableau.drop(columns="Score du modèle")
    st.dataframe(tableau, hide_index=True, width="stretch")

    # La fiche d'une station : ce que Citiz regarde avant d'ouvrir (ses 8 critères, la place, le compte).
    proposees = liste[liste.type == "citiz"]
    if cc is not None and len(proposees):
        st.markdown("**Fiche d'une station proposée**")
        rang_choisi = st.selectbox("Station", proposees.rang.tolist(), label_visibility="collapsed",
                                   format_func=lambda n: f"Station n° {n} · {proposees.set_index('rang').commune[n]}")
        station = proposees[proposees.rang == rang_choisi].iloc[0]
        gauche, droite = st.columns([1.3, 1])
        if station.idcar_200m in cc.criteres.index:
            notes = criteres_citiz.notes_radar(cc, station.idcar_200m)
            notes["info"] = notes.note.round(0).astype(int).astype(str) + " / 100" + np.where(
                notes.mesure, "", " (non mesuré ici)")
            base_notes = alt.Chart(notes).encode(
                x=alt.X("note:Q", title="Note sur 100 (rang dans la métropole)", scale=alt.Scale(domain=[0, 100])),
                y=alt.Y("libelle:N", title=None, sort=notes.libelle.tolist(),
                        axis=alt.Axis(labelLimit=260, labelOverlap=False)),
                tooltip=["libelle:N", "info:N"],
            )
            barres = base_notes.mark_bar(color="#32b4b5")
            valeurs = base_notes.mark_text(align="left", dx=4, color="#616060").encode(
                text=alt.Text("note:Q", format=".0f"))
            gauche.altair_chart((barres + valeurs).properties(
                height=320, title=f"Les 8 critères de Citiz · indice "
                                  f"{cc.criteres.indice_citiz[station.idcar_200m]:.0f} / 100"), width="stretch")
        recette = rentabilite.VOITURES_PAR_STATION * float(rentabilite.recette_voiture(occupation_reference))
        lignes_fiche = [
            f"Habitants gagnés à 5 minutes : {nombre(arrondi(station.population_nouvelle))}",
            f"Recette à notre usage moyen ({occupation_reference:.0%}) : {euros(recette)} par an, pour "
            f"{euros(station.cout)} de coût complet",
        ]
        place = places_proposees[places_proposees.rang == rang_choisi]
        if len(place):
            place = place.iloc[0]
            details = ["arbre le plus proche à " + f"{place.dist_arbre_m:.0f} m" if pd.notna(place.dist_arbre_m)
                       else "arbres non mesurés dans cette commune"]
            if place.distance_centre_m > 0:
                details.append(f"à {place.distance_centre_m:.0f} m du centre du carreau")
            adresse = place.adresse if isinstance(place.adresse, str) and place.adresse else "adresse inconnue"
            lignes_fiche.insert(0, f"Place proposée : {adresse} ({', '.join(details)})")
        else:
            lignes_fiche.insert(0, "Place proposée : aucun parking public à moins de 300 m, à trouver sur place")
        par_carreau = d.carreaux.set_index("idcar_200m")
        if "raison_1" in par_carreau and station.idcar_200m in par_carreau.index:
            raisons = [par_carreau.at[station.idcar_200m, f"raison_{i}"] for i in (1, 2, 3)]
            raisons = [r_ for r_ in raisons if isinstance(r_, str) and r_]
            if raisons:
                lignes_fiche.append("Ce que voit le modèle : " + " ; ".join(raisons).lower())
        droite.markdown("\n".join(f"- {t}" for t in lignes_fiche))

    export = liste.assign(
        population_nouvelle=arrondi(liste.population_nouvelle),
        dont_sans_transport=arrondi(liste.dont_sans_transport),
        population_cumulee=arrondi(liste.population_cumulee),
        valeur=liste.valeur.round(1),
        alpha=alpha, fourchette=fourchette, budget=montant, donnees="provisoire" if d.est_provisoire else "definitive",
    )
    st.download_button("Exporter la liste (CSV)", export.to_csv(index=False).encode("utf-8"),
                       file_name=f"{'PROVISOIRE_' if d.est_provisoire else ''}emplacements_{budget}_{montant}_alpha{alpha:g}_{fourchette}.csv",
                       mime="text/csv")

# ---------- business plan : ce que les stations rapportent à Citiz ----------

with onglet_business:
    if budget != "citiz":
        st.info("Le business plan porte sur les stations Citiz : choisir le budget Citiz dans la barre latérale.")
    else:
        cout = scenarios.cout_station(d.couts, "citiz", fourchette)
        equilibre = rentabilite.occupation_equilibre(cout)
        moyenne = occupation_reference
        texte = (f"Une station de 2 voitures coûte {euros(cout)} par an, amortissements compris. Elle couvre ce coût "
                 f"au-dessus de {equilibre:.0%} d'occupation, soit {euros(rentabilite.recette_voiture(equilibre))} "
                 "de recette par voiture et par an.")
        if usage_mesure:
            texte += (f" Nos voitures de la métropole sont en location {moyenne:.0%} du temps (mesuré) : "
                      "c'est l'emplacement qui fait la marge.")
        st.markdown(texte)
        cz = r.liste[r.liste.type == "citiz"]
        if cz.empty:
            st.info("Aucune station Citiz dans ce scénario.")
        else:
            st.markdown(f"**Le plan : {len(cz)} stations, {rentabilite.VOITURES_PAR_STATION * len(cz)} voitures**")
            visee = st.slider(
                "Occupation visée des nouvelles stations (part du temps en location)", 5, 70,
                int(round(moyenne * 100)), 1, format="%d %%",
                help="Par défaut, l'usage moyen mesuré de nos voitures. On ne prédit pas l'usage station par "
                     "station : sur 30 heures de relevés, aucune variable ne le prévoit encore de façon fiable "
                     "(modele/RESULTATS.md). Le curseur montre ce que le plan rapporte selon l'usage atteint.",
            ) / 100
            plan = rentabilite.comptes(np.full(len(cz), visee), cout, fourchette)
            tresorerie = rentabilite.tresorerie(plan.flux.to_numpy(), fourchette, annees=8)
            point_mort = next((int(a) for a, v in zip(tresorerie.annee, tresorerie.cumul) if v >= 0), None)
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Recette par an", euros(plan.recette.sum()))
            p2.metric("Résultat par an", euros_signe(plan.resultat.sum()), "après coût complet", delta_color="off", delta_arrow="off")
            p3.metric("Investissement d'ouverture", euros(len(cz) * rentabilite.INVESTISSEMENT[fourchette]))
            delai = plan.delai_ans.iat[0]
            p4.metric("Chaque station est remboursée en", f"{delai:.1f} ans".replace(".", ",") if np.isfinite(delai)
                      else "jamais")
            courbe_tresorerie = alt.Chart(tresorerie).mark_area(line={"color": "#32b4b5"}, color="#DBF4F4").encode(
                x=alt.X("annee:Q", title="Années après l'ouverture", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("cumul:Q", title="Trésorerie cumulée (€)", axis=alt.Axis(format="~s")),
                tooltip=[alt.Tooltip("annee:Q", title="année"), alt.Tooltip("cumul:Q", format=",.0f", title="cumul")],
            )
            zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#616060").encode(y="y:Q")
            st.altair_chart((courbe_tresorerie + zero).properties(height=300), width="stretch")
            st.caption(f"Les {len(cz)} stations ouvrent l'année 0 ({euros(-tresorerie.cumul.iat[0])} investis). "
                       + (f"Le plan est remboursé au bout de {point_mort} ans." if point_mort
                          else "À ce niveau d'usage, le plan n'est pas remboursé en 8 ans."))
            # chaque station proposée : où la poser, et ce qu'en disent les critères de Citiz
            par_carreau = d.carreaux.set_index("idcar_200m")
            stations_plan = pd.DataFrame({"Rang": cz.rang.to_numpy(), "Commune": cz.commune.astype(str).to_numpy()})
            if len(places_proposees):
                par_rang = places_proposees.set_index("rang")
                stations_plan["Place proposée"] = cz.rang.map(par_rang.adresse).fillna("à trouver sur place").to_numpy()
                stations_plan["Arbre le plus proche"] = cz.rang.map(par_rang.dist_arbre_m).map(
                    lambda m: f"{m:.0f} m" if pd.notna(m) else "non mesuré").to_numpy()
            if "indice_citiz" in par_carreau:
                stations_plan["Indice Citiz"] = cz.idcar_200m.map(par_carreau.indice_citiz).round(0).to_numpy()
            stations_plan["Habitants gagnés"] = arrondi(cz.population_nouvelle)
            st.dataframe(stations_plan, hide_index=True, width="stretch")
        st.markdown("**Le compte d'une station selon son usage**")
        comptes_types = rentabilite.comptes([0.05, moyenne, equilibre, 0.40, 0.50], cout, fourchette)
        st.dataframe(pd.DataFrame({
            "Occupation": [f"{o:.0%}" for o in comptes_types.occupation],
            "Cas": ["station qui dort", "moyenne mesurée", "équilibre", "bien placée", "très bien placée"],
            "Recette par an": comptes_types.recette.map(euros),
            "Résultat par an": comptes_types.resultat.map(euros_signe),
            "Délai de retour": comptes_types.delai_ans.map(lambda a: f"{a:.1f} ans".replace(".", ",")
                                                           if np.isfinite(a) else "jamais"),
        }), hide_index=True, width="stretch")
        if usage_mesure:
            st.markdown("**L'usage mesuré de nos stations**")
            dormantes = mesurees[mesurees.occupation_24h < 0.05]
            saturees = mesurees[mesurees.occupation_24h > 0.7]
            nb = (lambda s: int(s.nb_voitures.sum())) if "nb_voitures" in mesurees else len
            st.markdown(f"{len(dormantes)} stations ont servi moins de 5 % du temps pendant la mesure ({nb(dormantes)} "
                        f"voitures) ; {len(saturees)} ont dépassé 70 % ({nb(saturees)} voitures). Avant d'ouvrir, on "
                        "peut déplacer des voitures des unes vers les autres.")
            st.altair_chart(alt.Chart(mesurees.assign(pct=mesurees.occupation_24h * 100)).mark_bar(color="#32b4b5").encode(
                x=alt.X("pct:Q", bin=alt.Bin(step=10), title="Part du temps en location (%)"),
                y=alt.Y("count():Q", title="Stations"),
            ).properties(height=220), width="stretch")
            gauche, droite = st.columns(2)
            colonnes = {"nom": "Station", "nb_voitures": "Voitures", "occupation_24h": "En location"}
            for colonne_st, titre, df in ((gauche, "Saturées", saturees), (droite, "Qui dorment", dormantes)):
                colonne_st.markdown(titre)
                colonne_st.dataframe(df[[c for c in colonnes if c in df]].rename(columns=colonnes)
                                     .assign(**{"En location": lambda x: x["En location"].map(lambda o: f"{o:.0%}")}),
                                     hide_index=True, width="stretch")
            st.caption("Mesure : flux GBFS de Citiz relevé toutes les 10 minutes (table citiz_releves). Les premiers "
                       "jours ne couvrent pas de week-end : la mesure s'affine à chaque relevé.")

# ---------- impact : ce que les stations changent pour la ville et les ménages ----------

with onglet_impact:
    soc = k["social"]
    if budget == "citiz":
        env = k["environnement"]
        st.markdown(f"Ce que changent, chaque année, les {k['voitures_ajoutees']} voitures partagées de ce scénario "
                    "(enquête nationale sur l'autopartage, ADEME 2022 ; émissions : ADEME Base Empreinte).")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Voitures personnelles en moins", entre(env["voitures_en_moins"]))
        e2.metric("Voirie rendue à la ville", entre(env["m2_liberes"], " m²"),
                  f"{entre(env['places_liberees'])} places", delta_color="off", delta_arrow="off")
        e3.metric("Kilomètres en voiture évités", entre(env["km_evites"]))
        e4.metric("CO2 évité", entre(env["tonnes_co2_evitees"], " t"))
    st.markdown("Qui gagne une station à 5 minutes à pied :")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Habitants nouvellement desservis", nombre(arrondi(soc["habitants"])))
    s2.metric("Ménages sans voiture", nombre(arrondi(soc["menages_sans_voiture"]))
              if np.isfinite(soc["menages_sans_voiture"]) else "-")
    deja = impact.social(d.carreaux, np.flatnonzero(d.carreaux.a_option_citiz.to_numpy()))
    s3.metric("Vivent dans la moitié la plus modeste", f"{soc['part_sous_mediane']:.0%}"
              if np.isfinite(soc["part_sous_mediane"]) else "-",
              f"{deja['part_sous_mediane']:.0%} chez ceux qui ont déjà une Citiz" if np.isfinite(deja["part_sous_mediane"])
              else None, delta_color="off", delta_arrow="off")
    s4.metric("Logements sociaux", nombre(arrondi(soc["logements_sociaux"])) if np.isfinite(soc["logements_sociaux"]) else "-")
    st.caption("Moitié la plus modeste : sous le niveau de vie médian des habitants de la métropole (INSEE Filosofi). "
               "La Métropole rembourse la moitié des trajets Citiz des ménages modestes, jusqu'à 1 000 € par an "
               "(livre blanc Citiz 2026) : ces stations rendent l'aide utilisable là où ils vivent.")

# ---------- courbe budget -> habitants ----------

with onglet_courbe:
    cb = courbe(d.lecture, budget, types, alpha, fourchette, maximum, pas * 2, reglage)
    st.markdown("Chaque euro supplémentaire touche moins d'habitants que le précédent : les premières "
                "stations vont là où la population est la plus dense, les suivantes complètent.")
    base = alt.Chart(cb).encode(x=alt.X("budget:Q", title="Budget (€)", axis=alt.Axis(format="~s")))
    ligne = base.mark_line(point=True, color="#32b4b5").encode(
        y=alt.Y("habitants_nouveaux:Q", title="Habitants nouvellement desservis"),
        tooltip=[alt.Tooltip("budget:Q", format=",.0f"), alt.Tooltip("habitants_nouveaux:Q", format=",.0f"),
                 "nb_stations:Q"],
    )
    sans = base.mark_line(strokeDash=[4, 3], color="#FBBA43").encode(y="habitants_sans_transport_nouveaux:Q")
    repere = alt.Chart(pd.DataFrame({"budget": [montant]})).mark_rule(color="#616060").encode(x="budget:Q")
    st.altair_chart((ligne + sans + repere).properties(height=380), width="stretch")
    st.caption("Trait plein : tous les habitants gagnés · pointillé jaune : dont sans aucun transport · "
               "trait gris : budget choisi.")
    st.dataframe(cb.assign(habitants_nouveaux=arrondi(cb.habitants_nouveaux),
                           habitants_sans_transport_nouveaux=arrondi(cb.habitants_sans_transport_nouveaux)),
                 hide_index=True, width="stretch")

# ---------- équité ----------

with onglet_equite:
    cmp = comparer_alpha(d.lecture, budget, types, float(montant), fourchette, reglage)
    st.markdown(f"Même budget ({euros(montant)}, {dict(bas='coûts bas', defaut='coûts par défaut', haut='coûts hauts')[fourchette]}), **α = 0** (efficacité pure) contre "
                f"**α = {cmp['alpha_haut']:g}** (priorité aux zones sans aucun transport).")
    a, b, c = st.columns(3)
    a.metric("Habitants desservis", nombre(arrondi(cmp["habitants_alpha_haut"])),
             f"{-arrondi(cmp['habitants_en_moins']):+,} vs α = 0".replace(",", " "))
    b.metric("dont sans aucun transport", nombre(arrondi(cmp["sans_transport_alpha_haut"])),
             f"{arrondi(cmp['sans_transport_en_plus']):+,} vs α = 0".replace(",", " "))
    c.metric("Zones sans transport gagnées (carreaux)", cmp["zones_sans_transport_alpha_haut"],
             f"{cmp['zones_sans_transport_alpha_haut'] - cmp['zones_sans_transport_alpha0']:+} vs α = 0")
    pas_alpha = [0, 0.5, 1, 1.5, 2, 2.5, 3]
    frontiere = pd.DataFrame([
        {"alpha": al, **{key: resoudre(budget, types, float(montant), al, fourchette, reglage).indicateurs[key]
                         for key in ("habitants_nouveaux", "habitants_sans_transport_nouveaux")}}
        for al in pas_alpha
    ])
    st.altair_chart(
        alt.Chart(frontiere).mark_line(point=True, color="#32b4b5").encode(
            x=alt.X("habitants_nouveaux:Q", title="Habitants nouvellement desservis", scale=alt.Scale(zero=False)),
            y=alt.Y("habitants_sans_transport_nouveaux:Q", title="dont sans aucun transport", scale=alt.Scale(zero=False)),
            order="alpha:Q", tooltip=["alpha:Q", alt.Tooltip("habitants_nouveaux:Q", format=",.0f"),
                                      alt.Tooltip("habitants_sans_transport_nouveaux:Q", format=",.0f")],
        ).properties(height=340, title="Chaque point est une valeur de α : l'arbitrage revient au décideur"),
        width="stretch",
    )

# ---------- robustesse ----------

with onglet_robustesse:
    st.markdown(
        f"Coûts bas : **{rob['nb_bas']} stations** · coûts hauts : **{rob['nb_haut']} stations**. "
        f"**{rob['part_haut_dans_bas']:.0%}** des stations retenues en coûts hauts le sont aussi en coûts bas."
    )
    if rob["part_haut_dans_bas"] == 1 and len(types) == 1:
        st.caption("Avec un coût identique pour toutes les stations d'un type, l'ordre de priorité ne dépend pas "
                   "du coût : les coûts hauts gardent simplement le début de la liste.")
    tableau_rob = rob["tableau"]
    if not tableau_rob.iris.fillna("").astype(bool).any():
        tableau_rob = tableau_rob.drop(columns="iris")
    st.dataframe(tableau_rob.rename(columns={"rang_bas": "Rang (coûts bas)", "rang_haut": "Rang (coûts hauts)",
                                                "equipement": "Équipement", "commune": "Commune", "iris": "IRIS",
                                                "idcar_200m": "Carreau"}),
                 hide_index=True, width="stretch")

# ---------- méthode ----------

with onglet_methode:
    st.markdown(f"""
**Comment l'outil choisit, en trois phrases.**
1. Pour chaque emplacement possible, on compte les habitants à moins de 400 m (5 minutes à pied) qui n'ont
   aujourd'hui aucune station de ce type, pondérés par le curseur équité, puis on multiplie par le score
   de potentiel de l'emplacement.
2. On pose d'abord la station qui apporte le plus d'habitants nouveaux **par euro**, on retire ces habitants
   (chacun ne compte qu'une fois), et on recommence tant que le budget le permet.
3. On vérifie enfin qu'aucune station seule ne ferait mieux que toute la liste, ce qui garantit
   mathématiquement un résultat proche de l'optimum, et on mesure l'écart avec une résolution exacte.

**Ce scénario** : {k['nb_candidats']:,} emplacements candidats examinés, {k['recalculs']:,} calculs de gain
grâce au glouton paresseux (au lieu de {k['nb_candidats'] * max(k['nb_stations'], 1):,} pour un glouton naïf).
""".replace(",", " "))
    st.markdown("**D'où viennent les données**")
    st.table(pd.DataFrame({"Brique": list(d.sources), "Source": list(d.sources.values())}))
