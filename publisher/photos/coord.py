"""WGS84 → GCJ02 conversion for AMap lookups in mainland China.

Pure functions, no I/O. AMap serves GCJ02 tiles and expects GCJ02 coordinates;
feeding raw EXIF (WGS84) coordinates straight in shifts results by a few
hundred metres. Outside the mainland bounding box the transform is not defined
and coordinates are returned unchanged.
"""
from __future__ import annotations

import math

_PI = math.pi
_SEMI_MAJOR = 6_378_245.0
_EE = 0.006_693_421_622_965_943


def out_of_china(lat: float, lon: float) -> bool:
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _delta_lat(lon: float, lat: float) -> float:
    result = (-100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat
              + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon)))
    result += (20.0 * math.sin(6.0 * lon * _PI) + 20.0 * math.sin(2.0 * lon * _PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(lat * _PI) + 40.0 * math.sin(lat / 3.0 * _PI)) * 2.0 / 3.0
    result += (160.0 * math.sin(lat / 12.0 * _PI) + 320.0 * math.sin(lat * _PI / 30.0)) * 2.0 / 3.0
    return result


def _delta_lon(lon: float, lat: float) -> float:
    result = (300.0 + lon + 2.0 * lat + 0.1 * lon * lon
              + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon)))
    result += (20.0 * math.sin(6.0 * lon * _PI) + 20.0 * math.sin(2.0 * lon * _PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(lon * _PI) + 40.0 * math.sin(lon / 3.0 * _PI)) * 2.0 / 3.0
    result += (150.0 * math.sin(lon / 12.0 * _PI) + 300.0 * math.sin(lon / 30.0 * _PI)) * 2.0 / 3.0
    return result


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    if out_of_china(lat, lon):
        return lat, lon
    dlat = _delta_lat(lon - 105.0, lat - 35.0)
    dlon = _delta_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = 1 - _EE * math.sin(radlat) ** 2
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_SEMI_MAJOR * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    dlon = (dlon * 180.0) / (_SEMI_MAJOR / sqrt_magic * math.cos(radlat) * _PI)
    return lat + dlat, lon + dlon
