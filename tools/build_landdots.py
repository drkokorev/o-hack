"""Сетка точек суши для карты в интерфейсе из Natural Earth 110m land (public domain).

    curl -sSL -o land.geojson https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson
    .venv/bin/python -m tools.build_landdots land.geojson

Пишет apps/static/landdots.json: список [lon, lat] с шагом STEP градусов в области карты.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

STEP = 1.5
BOX = (5.0, -20.0, 170.0, 75.0)  # lon_min, lat_min, lon_max, lat_max — Европа, Азия, Африка до экватора
OUT = Path(__file__).resolve().parent.parent / "apps" / "static" / "landdots.json"


def inside(lon: float, lat: float, ring: list[list[float]]) -> bool:
    hit = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def main(path: str) -> None:
    polygons: list[list[list[list[float]]]] = []
    for f in json.loads(Path(path).read_text())["features"]:
        g = f["geometry"]
        polygons += [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    dots = []
    lat = BOX[1]
    while lat <= BOX[3]:
        lon = BOX[0]
        while lon <= BOX[2]:
            for poly in polygons:
                if inside(lon, lat, poly[0]) and not any(inside(lon, lat, hole) for hole in poly[1:]):
                    dots.append([round(lon, 1), round(lat, 1)])
                    break
            lon += STEP
        lat += STEP
    OUT.write_text(json.dumps({"step": STEP, "box": BOX, "dots": dots}, separators=(",", ":")))
    print(len(dots), "точек →", OUT)


if __name__ == "__main__":
    main(sys.argv[1])
