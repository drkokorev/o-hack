"""Fetch bounded Overture campground snapshots for four demo regions.

    python -m tools.fetch_campgrounds

Records are map features, not proof of open pitches, prices, fire permission,
or suitability for a personal tent. Requires DuckDB and network access.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from domains.trips.geo import BY_ID, distance_km
from tools.build_hotels import RELEASE, bbox, connect, places

OUT = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data" / "campgrounds.json"
REGIONS = {"altai": 75, "sochi": 50, "karelia": 60, "sheregesh": 40}


def main():
    con = connect()
    con.sql("PRAGMA disable_progress_bar")
    result = {"source": "Overture Maps Places", "release": RELEASE,
              "accessed_at": datetime.now(timezone.utc).isoformat(), "regions_km": REGIONS, "campgrounds": {}}
    for ident, radius in REGIONS.items():
        d = BY_ID[ident]
        started = time.monotonic()
        rows = places(con, bbox(d.lat, d.lon, radius),
                      "taxonomy.primary = 'campground' and coalesce(operating_status, 'open') = 'open'")
        items = {}
        for pid, name, name_ru, cat, conf, web, street, city, brand, country, lat, lon in rows:
            display_name = (name_ru or name or "").strip()
            if (not display_name or len(display_name) > 100 or conf is None or conf < .5 or
                    (country and country != "RU") or distance_km(d.lat, d.lon, lat, lon) > radius):
                continue
            items[pid] = {"id": pid, "name": display_name, "lat": round(lat, 5), "lon": round(lon, 5),
                          "conf": round(conf, 2), "street": street or None, "city": city or None,
                          "website": web or None}
        result["campgrounds"][ident] = sorted(items.values(), key=lambda item: (-item["conf"], item["name"]))[:100]
        print(f"{ident}: {len(rows)} source rows, {len(result['campgrounds'][ident])} retained, "
              f"{time.monotonic()-started:.1f}s", flush=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {sum(map(len, result['campgrounds'].values()))} campground records")


if __name__ == "__main__":
    main()
