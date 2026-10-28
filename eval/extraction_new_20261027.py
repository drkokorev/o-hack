"""Evaluate the raw LLM extraction separately from dialogue arbitration."""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date
from pathlib import Path
from statistics import median

from core.config import get_settings
from core.llm import build_llm, extract, parse_json_object, unwrap
from domains.trips.domain import TripsDomain
from domains.trips.state import TripState, TripUpdate
from eval.compare_extraction import judge

TODAY = date(2026, 10, 27)


class ObservedLLM:
    def __init__(self, client):
        self.client = client
        self.breaker = client.breaker
        self.calls = self.invalid = self.errors = self.valid = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        try:
            raw = self.client.complete(messages, **kwargs)
        except Exception:
            self.errors += 1
            raise
        try:
            TripUpdate.model_validate(unwrap(json.loads(parse_json_object(raw)), TripUpdate))
            self.valid += 1
        except ValueError:
            self.invalid += 1
        return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--pace-seconds", type=float, default=0, help="Pause between model calls to respect limits")
    args = parser.parse_args()
    if args.pace_seconds < 0:
        parser.error("--pace-seconds must be non-negative")
    settings = get_settings()
    if not settings.llm_enabled:
        raise SystemExit("No permitted model configured")
    client = ObservedLLM(build_llm(settings))
    cases = json.loads(Path(__file__).with_name("extraction_new_20261027.json").read_text(encoding="utf-8"))
    domain = TripsDomain(today=lambda: TODAY)
    results, timings = [], []
    for index, case in enumerate(cases):
        if index and args.pace_seconds:
            time.sleep(args.pace_seconds)
        messages = domain.extraction_messages(TripState(), [], case["text"], TODAY)
        valid_before = client.valid
        started = time.perf_counter()
        update = extract(client, TripUpdate, messages)
        elapsed = time.perf_counter() - started
        if client.valid == valid_before:
            # An unavailable model, invalid response or open breaker is not a
            # prediction and cannot count as either a pass or a quality failure.
            results.append({"id": case["id"], "status": "INCOMPLETE", "seconds": round(elapsed, 4)})
            print(case["id"], "INCOMPLETE; stopping to avoid further quota use", flush=True)
            break
        timings.append(elapsed)
        failures = judge(case, update)
        results.append({"id": case["id"], "pass": not failures, "failures": failures,
                        "fields": update.model_dump(mode="json", exclude_none=True), "seconds": round(elapsed, 4)})
        print(case["id"], "PASS" if not failures else "FAIL", flush=True)
    timings.sort()
    completed = [item for item in results if "pass" in item]
    report = {"fixed_today": TODAY.isoformat(), "provider": settings.llm_provider, "model": settings.llm_model,
              "status": "complete" if len(completed) == len(cases) else "incomplete",
              "passed": sum(item["pass"] for item in completed), "completed": len(completed),
              "total_planned": len(cases), "calls": client.calls,
              "invalid_responses": client.invalid, "request_errors": client.errors,
              "median_seconds": round(median(timings), 4) if timings else None,
              "p95_seconds": round(timings[math.ceil(len(timings)*.95)-1], 4) if timings else None,
              "cases": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"raw extraction: {report['passed']}/{report['completed']} completed of {report['total_planned']}; "
          f"status={report['status']}; calls={client.calls}; invalid={client.invalid}; "
          f"errors={client.errors}; p50={report['median_seconds']}s; p95={report['p95_seconds']}s")
    return 2 if report["status"] == "incomplete" else 0 if report["passed"] == report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
