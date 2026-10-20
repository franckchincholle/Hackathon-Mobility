"""Passage EPSG:3035 (calculs, en mètres, comme les tables de MSc 1) <-> WGS84 (carte)."""

from functools import lru_cache

import numpy as np
from pyproj import Transformer


@lru_cache(maxsize=None)
def _transformeur(source: str, cible: str) -> Transformer:
    return Transformer.from_crs(source, cible, always_xy=True)


def vers_wgs84(x, y) -> tuple[np.ndarray, np.ndarray]:
    """EPSG:3035 -> (longitude, latitude)."""
    return _transformeur("EPSG:3035", "EPSG:4326").transform(np.asarray(x), np.asarray(y))


def vers_3035(lon, lat) -> tuple[np.ndarray, np.ndarray]:
    """(longitude, latitude) -> EPSG:3035."""
    return _transformeur("EPSG:4326", "EPSG:3035").transform(np.asarray(lon), np.asarray(lat))
