"""Snapshot active aerodrome records from OurAirports, without live schedules.

    python -m tools.fetch_airports

Source: https://ourairports.com/data/ (public domain, no accuracy guarantee).
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUT = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data" / "ourairports.json"
TYPES = {"large_airport", "medium_airport", "small_airport"}


def main():
    with urlopen(Request(URL, headers={"User-Agent": "odin-zapros-hackathon/1.0"}), timeout=90) as response:
        rows = csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")))
        records = []
        for row in rows:
            if row.get("type") not in TYPES or not row.get("name") or not row.get("id"):
                continue
            try:
                lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            records.append({"id": row["id"], "name": row["name"], "lat": lat, "lon": lon,
                            "type": row["type"], "country": row.get("iso_country") or None,
                            "city": row.get("municipality") or None, "iata": row.get("iata_code") or None,
                            "scheduled_service": row.get("scheduled_service") or None})
    records.sort(key=lambda row: int(row["id"]))
    snapshot = {"source": URL, "license": "public domain", "accessed_at": datetime.now(timezone.utc).isoformat(),
                "filter": sorted(TYPES), "airports": records}
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"OurAirports: {len(records)} records, {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
