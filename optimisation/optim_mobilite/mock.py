"""Ce qui reste MOCK : les coûts que le MBA n'a pas encore chiffrés.

Le MBA a livré Citiz (classeur « Coût citiz.xlsx », importé par scripts/importer_couts_mba.py) ;
le vélo et le bus restent ici, en ordres de grandeur, jusqu'à sa livraison. La ligne Citiz ne
sert que si son classeur n'a pas été importé. Coût complet d'une station et par an.
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
