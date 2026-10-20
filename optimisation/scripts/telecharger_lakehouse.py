"""Copie locale des tables du Lakehouse `Mobilite`, pour lancer le site sans lire Fabric en direct.

    python scripts/telecharger_lakehouse.py              copie dans data/reel/ (ou OPTIM_DONNEES)
    python scripts/telecharger_lakehouse.py --verifier   dit si la copie locale suffit au site
    python scripts/telecharger_lakehouse.py --dossier D  copie dans un autre dossier

La lecture et le rangement sont ceux du site (`optim_mobilite.fabric.lire`, puis
`fabric.sauvegarder`) : toute table que `fabric.py` sait lire est copiée, et une table
facultative absente du Lakehouse est sautée. Si la lecture d'ensemble échoue sur une table,
les tables sont relues une par une pour copier toutes les autres.

Demande une session Azure CLI sur le tenant Epitech (`az login`). Rien n'est écrit dans Fabric.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from optim_mobilite import contrat, fabric  # noqa: E402


def taille_lisible(octets: float) -> str:
    """« 4,2 Mo » : virgule décimale, à la française."""
    for unite in ("o", "Ko", "Mo"):
        if octets < 1024:
            return f"{octets:.0f} {unite}" if unite == "o" else f"{octets:.1f} {unite}".replace(".", ",")
        octets /= 1024
    return f"{octets:.1f} Go".replace(".", ",")


def lire_table_par_table(dossier: Path) -> tuple[dict, list[str], dict[str, str]]:
    """Secours : les mêmes lectures que `fabric.lire`, une table à la fois, pour qu'une table
    illisible n'empêche pas de copier les autres. Renvoie (tables, trouvées, erreurs)."""
    j = fabric.jeton()
    acces = {"bearer_token": j, "use_fabric_endpoint": "true"}
    entetes = {"Authorization": f"Bearer {j}", "x-ms-version": "2023-11-03"}
    racine = f"abfss://{fabric.ESPACE}@{fabric.ONELAKE}/{fabric.LAKEHOUSE}/Tables/dbo"
    tables, trouvees, erreurs = {}, [], {}
    declarees = {**fabric.OBLIGATOIRES, **fabric.FACULTATIVES}
    renommages = getattr(fabric, "RENOMMAGES", {})
    for nom, (cle, colonnes) in declarees.items():
        if cle in tables:
            continue
        try:
            tables[cle] = fabric._table(racine, nom, acces, colonnes).rename(columns=renommages.get(nom, {}))
            trouvees.append(nom)
        except fabric.TableNotFoundError:
            if nom in fabric.OBLIGATOIRES:
                erreurs[nom] = "absente du Lakehouse"
        except Exception as e:  # une table illisible : on copie les autres
            erreurs[nom] = f"{type(e).__name__} : {e}"
    try:
        tables.update(fabric._gtfs_tisseo(entetes, dossier / "msc1"))
    except Exception as e:
        erreurs["Files/brut/gtfs (tracés Tisséo)"] = f"{type(e).__name__} : {e}"
    if "couts" not in tables:
        try:
            classeur = fabric._classeur_couts(entetes)
            if classeur is not None:
                tables["couts"] = classeur
                trouvees.append("Files/mba")
        except Exception as e:
            erreurs["Files/mba (classeur de coûts)"] = f"{type(e).__name__} : {e}"
    return tables, trouvees, erreurs


def chemin_copie(dossier: Path, cle: str) -> Path | None:
    """Où `fabric.sauvegarder` a rangé la table `cle`."""
    chemin = dossier / getattr(fabric, "RANGEMENT", {}).get(cle, "msc1") / f"{cle}.parquet"
    if chemin.exists():
        return chemin
    return next(iter(sorted(dossier.rglob(f"{cle}.parquet"))), None)


def copier(dossier: Path) -> int:
    print(f"Lecture du Lakehouse Mobilite (espace « Hackathon Mobi »), copie dans {dossier}", flush=True)
    debut = time.monotonic()
    erreurs: dict[str, str] = {}
    try:
        tables, trouvees = fabric.lire(dossier)
    except fabric.FabricInjoignable as e:
        if "az login" in str(e) or "Azure CLI" in str(e):
            print(f"Copie impossible : {e}", file=sys.stderr)
            return 1
        print(f"La lecture d'ensemble a échoué ({e}) : relecture table par table.", flush=True)
        try:
            tables, trouvees, erreurs = lire_table_par_table(dossier)
        except Exception as e2:
            print(f"Copie impossible : {type(e2).__name__} : {e2}", file=sys.stderr)
            return 1
    manquantes = [n for n in fabric.OBLIGATOIRES if fabric.OBLIGATOIRES[n][0] not in tables]
    if not tables:
        print("Copie impossible : aucune table lue.", file=sys.stderr)
        return 1

    horodatage = dt.datetime.now().strftime("%d/%m/%Y à %H:%M")
    fabric.sauvegarder(tables, dossier, horodatage)

    print(f"\n{'Table':<24} {'Lignes':>9} {'Taille':>10}  Fichier")
    total = 0
    for cle in sorted(tables, key=lambda c: (str(chemin_copie(dossier, c)), c)):
        chemin = chemin_copie(dossier, cle)
        octets = chemin.stat().st_size if chemin else 0
        total += octets
        fichier = str(chemin.relative_to(dossier)) if chemin else "?"
        lignes = f"{len(tables[cle]):,}".replace(",", " ")
        print(f"{cle:<24} {lignes:>9} {taille_lisible(octets):>10}  {fichier}")
    print(f"{len(tables)} tables, {taille_lisible(total)}, en {time.monotonic() - debut:.0f} s "
          f"(lecture du {horodatage}).")

    absentes = [nom for nom, (cle, _) in getattr(fabric, "FACULTATIVES", {}).items()
                if nom not in trouvees and cle not in tables]
    if absentes:
        print(f"Absentes du Lakehouse, sautées : {', '.join(absentes)}.")
    for nom, message in erreurs.items():
        print(f"Non copiée : {nom} ({message}).", file=sys.stderr)
    if manquantes:
        print(f"Tables obligatoires manquantes : {', '.join(manquantes)}. Le site ne pourra pas "
              "démarrer sur cette copie.", file=sys.stderr)
        return 1
    return 0


def verifier(dossier: Path) -> int:
    """0 si la copie locale contient toutes les tables obligatoires, 1 sinon."""
    manquantes = [nom for nom in contrat.TABLES["msc1"]
                  if nom not in contrat.FACULTATIVES_MSC1 and contrat.trouver(dossier, "msc1", nom) is None]
    if manquantes:
        print(f"Copie locale incomplète dans {dossier} : il manque {', '.join(manquantes)}.", file=sys.stderr)
        return 1
    marque = dossier / "derniere_lecture.json"
    quand = json.loads(marque.read_text()).get("date", "date inconnue") if marque.exists() else "date inconnue"
    print(f"Copie locale trouvée dans {dossier} (dernière lecture de Fabric : {quand}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Copie locale des tables du Lakehouse Mobilite.")
    parser.add_argument("--dossier", type=Path,
                        help="dossier de la copie (défaut : OPTIM_DONNEES, sinon dossier_donnees de config.toml)")
    parser.add_argument("--verifier", action="store_true",
                        help="ne copie rien : dit si la copie locale suffit pour lancer le site")
    args = parser.parse_args()
    dossier = args.dossier.resolve() if args.dossier else contrat.dossier_par_defaut()
    return verifier(dossier) if args.verifier else copier(dossier)


if __name__ == "__main__":
    sys.exit(main())
