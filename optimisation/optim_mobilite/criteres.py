"""Les critères au choix : chacun sert à la fois de carte et d'ingrédient du score des zones à potentiel.

Le décideur active les critères qu'il veut, leur donne un poids (1 à 3) et, quand un critère peut
jouer dans les deux sens (le niveau de vie, par exemple), choisit ce sens. Le score d'un carreau
est alors :

    score = Σ poids × rang du critère / Σ poids           (entre 0 et 1)

où le « rang » est la place du carreau parmi les carreaux habités au-dessus du seuil (0 = le plus
bas, 1 = le plus haut), retourné si le sens choisi est « faible ». Passer par le rang plutôt que
par les valeurs met sur la même échelle des euros, des parts et des comptages, et évite qu'une
valeur extrême écrase les autres. Un carreau sans valeur (quartier inconnu) reçoit 0,5 : neutre.

Ce score ne remplace pas le modèle prédictif (décision 7), qui reste la référence par défaut : il
permet de voir ce que donnent d'autres hypothèses, et le modèle est lui-même un critère possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

SURFACE_KM2 = 0.04  # un carreau de 200 m


def _part(numerateur: str, denominateur: str) -> Callable[[pd.DataFrame], pd.Series | None]:
    def calcul(c: pd.DataFrame):
        if numerateur not in c or denominateur not in c:
            return None
        return (c[numerateur] / c[denominateur].where(c[denominateur] > 0)).clip(0, 1)
    return calcul


def _colonne(nom: str, facteur: float = 1.0) -> Callable[[pd.DataFrame], pd.Series | None]:
    def calcul(c: pd.DataFrame):
        if nom not in c or c[nom].isna().all():
            return None
        return pd.to_numeric(c[nom], errors="coerce") * facteur
    return calcul


TYPES_QUARTIER = {"H": 1.0, "Z": 0.5, "A": 0.0}  # habitat, commune non découpée, activité


def _type_quartier(c: pd.DataFrame):
    if "type_iris" not in c or not c.type_iris.astype(bool).any():
        return None
    return c.type_iris.map(TYPES_QUARTIER)


@dataclass
class Critere:
    cle: str
    libelle: str
    groupe: str
    explication: str
    calcul: Callable[[pd.DataFrame], pd.Series | None]
    sens_defaut: str = "haut"  # « haut » : les valeurs élevées comptent plus
    sens: dict = field(default_factory=lambda: {"haut": "élevé", "bas": "faible"})
    reglable: bool = False
    categoriel: bool = False  # déjà entre 0 et 1 : pas de passage par le rang
    echelle: str = "carreau"
    unite: str = ""


CRITERES = [
    Critere("densite", "Densité de population", "Habitants", "Habitants au km² dans le carreau.",
            _colonne("population", 1 / SURFACE_KM2), unite="hab./km²"),
    Critere("niveau_vie", "Niveau de vie moyen", "Habitants",
            "Niveau de vie moyen des habitants du carreau (INSEE Filosofi).", _colonne("niveau_vie_moyen"),
            sens={"haut": "plutôt élevé", "bas": "plutôt modeste"}, reglable=True, unite="€ par an"),
    Critere("pauvrete", "Ménages sous le seuil de pauvreté", "Habitants",
            "Part des ménages du carreau sous le seuil de pauvreté.", _colonne("part_menages_pauvres"),
            sens_defaut="bas", sens={"haut": "part élevée", "bas": "part faible"}, reglable=True),
    Critere("logements_sociaux", "Logements sociaux", "Habitants", "Logements sociaux rapportés aux ménages.",
            _part("logements_sociaux", "menages"), sens_defaut="bas",
            sens={"haut": "part élevée", "bas": "part faible"}, reglable=True),
    Critere("une_personne", "Ménages d'une personne", "Habitants", "Part des ménages d'une seule personne.",
            _part("menages_1_personne", "menages")),
    Critere("jeunes_actifs", "Jeunes actifs (25-39 ans)", "Habitants", "Part des habitants de 25 à 39 ans.",
            _part("age_25_39", "population")),
    Critere("collectif", "Logement en immeuble", "Habitants",
            "Part des ménages en logement collectif (souvent sans garage).",
            _part("menages_logement_collectif", "menages")),
    Critere("sans_voiture", "Ménages sans voiture", "Motorisation", "Part des ménages sans voiture (mesurée par quartier).",
            _colonne("part_menages_sans_voiture"), sens={"haut": "part élevée", "bas": "part faible"},
            reglable=True, echelle="quartier"),
    Critere("voitures_menage", "Voitures par ménage", "Motorisation",
            "Nombre moyen de voitures par ménage (mesuré par quartier).", _colonne("voitures_par_menage"),
            sens_defaut="bas", sens={"haut": "nombreuses", "bas": "peu nombreuses"}, reglable=True,
            echelle="quartier"),
    Critere("type_quartier", "Type de quartier", "Quartier",
            "Quartier d'habitation, commune non découpée ou zone d'activité (INSEE).", _type_quartier,
            sens={"haut": "habitat d'abord", "bas": "activité d'abord"}, reglable=True, categoriel=True,
            echelle="quartier"),
    Critere("communes", "Communes à privilégier", "Quartier",
            "Les communes choisies comptent 1, les autres 0.", lambda c: None, categoriel=True),
    Critere("commerces", "Commerces alimentaires à 5 min", "Services à 5 min",
            "Commerces alimentaires à 5 minutes à pied.", _colonne("commerces_alimentaires_5min")),
    Critere("sante", "Santé à 5 min", "Services à 5 min", "Équipements de santé à 5 minutes à pied.",
            _colonne("sante_5min")),
    Critere("enseignement", "Écoles à 5 min", "Services à 5 min", "Établissements d'enseignement à 5 minutes à pied.",
            _colonne("enseignement_5min")),
    Critere("services", "Services à 5 min", "Services à 5 min", "Services aux particuliers à 5 minutes à pied.",
            _colonne("services_5min")),
    Critere("gare", "Gare à 5 min", "Services à 5 min", "Gares à 5 minutes à pied (intermodalité).",
            _colonne("gares_5min")),
    Critere("peu_transport", "Peu de transport aujourd'hui", "Transport",
            "Nombre d'options de transport à 5 min : moins il y en a, plus le carreau compte.",
            _colonne("nb_options_total"), sens_defaut="bas", sens={"haut": "beaucoup", "bas": "peu"}),
    Critere("arbres", "Stationnement dégagé (peu d'arbres)", "Stationnement",
            "Arbres au km² dans le carreau : une place dégagée est plus visible, et la voiture n'est ni salie "
            "ni abîmée (demande de Citiz).", _colonne("nb_arbres", 1 / SURFACE_KM2), sens_defaut="bas",
            sens={"haut": "arboré", "bas": "dégagé"}, unite="arbres/km²"),
    Critere("modele", "Score du modèle prédictif", "Modèle",
            "Le score de potentiel Citiz du modèle prédictif.", _colonne("score_modele")),
]
PAR_CLE = {c.cle: c for c in CRITERES}


@dataclass
class Reglage:
    """Les critères actifs : clé -> (poids, sens), et les communes à privilégier."""

    actifs: dict[str, tuple[int, str]] = field(default_factory=dict)
    communes: tuple[str, ...] = ()

    def encoder(self) -> str:
        """Forme texte, pour l'URL et les caches : densite:2,niveau_vie:1:bas,communes:1@Blagnac|Balma."""
        morceaux = []
        for cle, (poids, sens) in sorted(self.actifs.items()):
            texte = f"{cle}:{poids}"
            if sens != PAR_CLE[cle].sens_defaut:
                texte += f":{sens}"
            if cle == "communes":
                texte += "@" + "|".join(self.communes)
            morceaux.append(texte)
        return ",".join(morceaux)

    @classmethod
    def decoder(cls, texte: str) -> "Reglage":
        actifs, communes = {}, ()
        for morceau in filter(None, (texte or "").split(",")):
            morceau, _, liste = morceau.partition("@")
            cle, *reste = morceau.split(":")
            if cle not in PAR_CLE:
                continue
            poids = int(reste[0]) if reste and reste[0].isdigit() else 1
            sens = reste[1] if len(reste) > 1 and reste[1] in ("haut", "bas") else PAR_CLE[cle].sens_defaut
            actifs[cle] = (min(max(poids, 1), 3), sens)
            if cle == "communes":
                communes = tuple(filter(None, liste.split("|")))
        return cls(actifs, communes)

    def resume(self) -> str:
        if not self.actifs:
            return "aucun critère : seule la population compte"
        parties = []
        for cle, (poids, sens) in self.actifs.items():
            c = PAR_CLE[cle]
            precision = f", {', '.join(self.communes) or 'aucune choisie'}" if cle == "communes" else (
                f", {c.sens[sens]}" if c.reglable or sens != "haut" else "")
            parties.append(f"{c.libelle.lower()} (×{poids}{precision})")
        return " + ".join(parties)


def disponibles(carreaux: pd.DataFrame) -> dict[str, bool]:
    """Les critères calculables avec les données présentes."""
    return {c.cle: c.cle == "communes" or c.calcul(carreaux) is not None for c in CRITERES}


def rang(valeurs: pd.Series, reference: np.ndarray) -> pd.Series:
    """Place de chaque valeur parmi les valeurs de référence, entre 0 et 1 (ex æquo au milieu) ; 0,5 si inconnue."""
    ref = np.sort(reference[~np.isnan(reference)])
    v = valeurs.to_numpy(dtype=float)
    if ref.size == 0:
        return pd.Series(0.5, index=valeurs.index)
    r = (np.searchsorted(ref, v, "left") + np.searchsorted(ref, v, "right")) / (2 * ref.size)
    return pd.Series(np.where(np.isnan(v), 0.5, r), index=valeurs.index)


def valeur_critere(carreaux: pd.DataFrame, cle: str, communes: tuple[str, ...] = ()) -> pd.Series | None:
    """La valeur brute d'un critère pour chaque carreau (pour la carte), ou None si indisponible."""
    if cle == "communes":
        return carreaux.commune.isin(communes).astype(float)
    return PAR_CLE[cle].calcul(carreaux)


def score(carreaux: pd.DataFrame, reglage: Reglage) -> np.ndarray:
    """Score de chaque carreau, entre 0 et 1, selon les seuls critères actifs ; 1 partout s'il n'y en a aucun."""
    reference = ((carreaux.population > 0) & ~carreaux.sous_seuil).to_numpy()
    total = np.zeros(len(carreaux))
    somme_poids = 0
    for cle, (poids, sens) in reglage.actifs.items():
        brut = valeur_critere(carreaux, cle, reglage.communes)
        if brut is None:
            continue
        brut = brut.astype(float)
        r = brut.fillna(0.5) if PAR_CLE[cle].categoriel else rang(brut, brut.to_numpy()[reference])
        if sens == "bas":
            r = 1 - r
        total += poids * r.to_numpy()
        somme_poids += poids
    return total / somme_poids if somme_poids else np.ones(len(carreaux))
