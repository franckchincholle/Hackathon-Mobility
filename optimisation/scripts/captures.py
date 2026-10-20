"""Captures de secours de la démo : le plan B si le site ou le réseau tombe pendant l'oral.

Le site doit tourner (./start.sh à la racine du dépôt). Le script l'ouvre dans un Chromium sans écran,
règle chaque scénario par l'URL, et enregistre une image par écran de la démo :

    python scripts/captures.py [--port 8501] [--sortie ../presentation/captures]

Navigateur : celui de Playwright s'il est installé ; sinon le Chromium indiqué par la variable
CHROME_PATH, ou le plus récent trouvé dans le cache de Playwright (~/.cache/ms-playwright).
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

RACINE = Path(__file__).resolve().parent.parent
SCENARIO = "?budget=citiz&montant=500000&alpha=1&fourchette=defaut"


def chromium(p):
    """Le navigateur de Playwright, ou à défaut un Chromium déjà présent sur le poste."""
    try:
        return p.chromium.launch()
    except Error:
        chemin = os.environ.get("CHROME_PATH")
        if not chemin:
            trouves = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
            if not trouves:
                raise SystemExit("Aucun Chromium : installer celui de Playwright, ou donner CHROME_PATH.")
            chemin = str(trouves[-1])
        return p.chromium.launch(executable_path=chemin, args=["--use-gl=swiftshader", "--enable-webgl"])


def attendre(page, secondes: int = 120) -> None:
    """Le site a fini de calculer : l'en-tête est là et l'indicateur d'exécution a disparu."""
    page.wait_for_selector("text=Où installer les prochaines stations", timeout=secondes * 1000)
    fin = time.time() + secondes
    while time.time() < fin and page.locator("[data-testid='stStatusWidget']").count():
        time.sleep(0.5)
    time.sleep(4)  # la carte et les graphiques finissent de se dessiner


def main() -> None:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--port", default="8501")
    arguments.add_argument("--sortie", type=Path, default=RACINE.parent / "presentation" / "captures")
    a = arguments.parse_args()
    a.sortie.mkdir(parents=True, exist_ok=True)
    base = f"http://localhost:{a.port}/"

    with sync_playwright() as p:
        navigateur = chromium(p)
        page = navigateur.new_page(viewport={"width": 1600, "height": 1000})

        def capture(nom: str) -> None:
            page.screenshot(path=a.sortie / nom)
            print("  ", nom)

        def defiler(dy: int) -> None:
            page.mouse.move(950, 300)  # sur la page, loin de la carte, qui prendrait la molette pour un zoom
            page.mouse.wheel(0, dy)
            time.sleep(2)

        page.goto(base + SCENARIO + "&calques=proposees,gagnes,citiz,places,communes")
        attendre(page, 240)
        capture("1_scenario_citiz_500k.png")
        defiler(1150)
        capture("2_liste_des_stations.png")
        defiler(800)
        capture("2b_fiche_station.png")

        for prefixe, onglet in (("3", "Business plan"), ("4", "Impact")):
            page.goto(base + SCENARIO)
            attendre(page)
            page.get_by_role("tab", name=onglet).click()
            time.sleep(3)
            nom = onglet.lower().replace(" ", "_")
            capture(f"{prefixe}_{nom}.png")
            if onglet == "Business plan":
                for suite in ("b", "c", "d"):
                    defiler(850)
                    capture(f"{prefixe}{suite}_{nom}.png")

        page.goto(base + SCENARIO + "&score=citiz8&calques=proposees,places,usage,arbres")
        attendre(page)
        capture("5_les_8_criteres_de_citiz.png")
        page.goto(base + "?budget=collectivite&montant=1000000&alpha=1&fourchette=defaut")
        attendre(page)
        capture("6_collectivite_velo_bus.png")
        navigateur.close()


if __name__ == "__main__":
    main()
