"""Compare fixed-date dialogue reports, retaining replies and failures but excluding timings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical(report):
    return sorted(({
        "id": case["id"], "pass": case["pass"],
        "turns": [{key: turn.get(key) for key in ("input", "reply", "kind", "nlu", "failures")}
                  for turn in case["turns"]],
    } for case in report["results"]), key=lambda case: case["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    left, right = canonical(before), canonical(after)
    digest = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    result = {"identical": left == right, "before_passed": before["cases_passed"],
              "after_passed": after["cases_passed"], "cases": len(right),
              "turns": sum(len(case["turns"]) for case in right),
              "before_sha256": digest(left), "after_sha256": digest(right),
              "existing_failed_cases": [case["id"] for case in right if not case["pass"]],
              "scope": "Fixed-date local rules; equality preserves existing failures and does not evaluate live model quality."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
