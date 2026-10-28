"""Walk every map point to verify paging and global cluster counts."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from domains.trips import map_catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    info = map_catalog.catalogue()
    results = []
    for kind in ("hotel", "all"):
        expected = info["counts"]["hotel"] if kind == "hotel" else sum(info["counts"].values())
        seen, cursor, pages = set(), 0, 0
        started = time.perf_counter()
        while cursor is not None:
            result = map_catalog.points(kind, -180, -90, 180, 90, cursor, 1000)
            assert result["catalog_version"] == info["catalog_version"]
            for point in result["items"]:
                assert point["id"] not in seen
                assert "price" not in point and "availability" not in point
                seen.add(point["id"])
            cursor, pages = result["next_cursor"], pages + 1
        page_seconds = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        cluster = map_catalog.clusters(kind, -180, -90, 180, 90, 3)
        cluster_seconds = round(time.perf_counter() - started, 3)
        total = sum(item["count"] for item in cluster["items"])
        assert len(seen) == total == expected
        results.append({"kind": kind, "expected": expected, "unique_points": len(seen), "pages": pages,
                        "cluster_points": total, "cluster_count": len(cluster["items"]),
                        "paging_seconds": page_seconds, "clustering_seconds": cluster_seconds})
        print(kind, len(seen), "points", pages, "pages", "cluster total", total, flush=True)
    report = {"catalog_version": info["catalog_version"], "results": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
