"""Démo : choisir un budget, obtenir la carte et la liste priorisée des emplacements.

    streamlit run app/streamlit_app.py

Tout est lu en local au démarrage puis gardé en cache : aucun téléchargement de données
pendant la démo. Les réglages se passent aussi par l'URL (?budget=citiz&montant=500000&alpha=1
&fourchette=defaut), ce qu'utilise scripts/captures.py.
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
from optim_mobilite import couverture, criteres, equite, scenarios  # noqa: E402
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
    return criteres.score(d.carreaux, criteres.Reglage.decoder(reglage))


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
    base_score = st.radio(
        "Zones à potentiel : sur quoi se baser ?", ["modele", "criteres"], label_visibility="collapsed",
        index=1 if parametre("score", "modele") == "criteres" else 0,
        format_func={"modele": "Modèle prédictif", "criteres": "Mes critères"}.get,
        help="Le modèle prédictif estime le potentiel Citiz d'un emplacement d'après les quartiers où Citiz "
             "fonctionne déjà. « Mes critères » remplace ce score par les seuls critères que vous cochez, avec "
             "vos poids : la carte des zones à potentiel et la liste des stations en dépendent alors.",
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
c2.metric("Coût total", euros(k["cout_total"]), f"budget {euros(montant)}", delta_color="off")
c3.metric("Habitants nouvellement desservis", nombre(arrondi(k["habitants_nouveaux"])))
c4.metric("dont sans aucun transport aujourd'hui", nombre(arrondi(k["habitants_sans_transport_nouveaux"])))
c5.metric("Coût par habitant gagné (par an)",
          f"{k['cout_total'] / k['habitants_nouveaux']:.0f} €" if k["habitants_nouveaux"] else "—")

onglets = st.tabs(["Carte et liste", "Budget → habitants", "Équité", "Robustesse des coûts", "Méthode"])

# ---------- carte et liste ----------

with onglets[0]:
    liste = r.liste.astype({"equipement": str, "commune": str, "iris": str})
    if liste.empty:
        st.info(f"Aucune station ne rentre dans ce budget : une station coûte au moins "
                f"{euros(min(scenarios.cout_station(d.couts, t, fourchette) for t in types))}.")
    potentiel = potentiel_candidats(d.lecture, budget, types, alpha, reglage) if "potentiel" in choix else pd.DataFrame()
    st.pydeck_chart(
        pdk.Deck(
            layers=couches(d, choix, r, structure(d, d.lecture, budget, types), potentiel, commune),
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

# ---------- courbe budget -> habitants ----------

with onglets[1]:
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

with onglets[2]:
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

with onglets[3]:
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

with onglets[4]:
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
