"""Les coûts MOCK : le repli si aucun coût du MBA n'est lisible.

Le MBA a livré les trois équipements (docs/couts/, lus par couts_mba.py et copiés dans
data/reel/mba/couts.parquet) : ces ordres de grandeur ne servent plus que si cette table manque,
par exemple dans les tests. Coût complet d'une station et par an.
"""

from pathlib import Path

import pandas as pd

COUTS_MOCK = pd.DataFrame(
    {
        "type": ["citiz", "velo", "bus"],
        "cout_bas": [25_000, 15_000, 8_000],
        "cout_defaut": [35_000, 22_500, 14_000],
        "cout_haut": [45_000, 30_000, 20_000],
        "budget": ["citiz", "collectivite", "collectivite"],
    }
)


def generer(dossier: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "MOCK_couts.parquet"
    COUTS_MOCK.to_parquet(chemin, index=False)
    return chemin
