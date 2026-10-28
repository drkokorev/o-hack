"""Turn-by-turn fixed-date evaluation; fixtures contain only synthetic inputs.

Examples: python -m eval.dialogue_20261027 --set dev --output ../dev.json
          python -m eval.dialogue_20261027 --set holdout --output ../holdout.json
No LLM is called unless --model is explicitly selected and configured.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date
from pathlib import Path
from statistics import median
from collections import Counter

from core.agent import Agent
from domains.trips.domain import TripsDomain

TODAY = date(2026, 10, 27)
DIR = Path(__file__).parent


def run(cases, agent, pace_seconds=0):
    results, durations = [], []
    for case in cases:
        session = agent.new_session()
        turns = []
        for turn in case["turns"]:
            failures = []
            started = time.perf_counter()
            try:
                step = agent.handle(session, turn["text"])
                elapsed = time.perf_counter() - started
                durations.append(elapsed)
                state = session.state.model_dump(mode="json")
                for key, expected in turn.get("state", {}).items():
                    if state.get(key) != expected:
                        failures.append(f"state.{key}: expected {expected!r}, got {state.get(key)!r}")
                for key, values in turn.get("contains", {}).items():
                    if not set(values) <= set(state.get(key) or []):
                        failures.append(f"state.{key}: expected to contain {values!r}, got {state.get(key)!r}")
                for key, values in turn.get("excludes", {}).items():
                    if set(values) & set(state.get(key) or []):
                        failures.append(f"state.{key}: expected to exclude {values!r}, got {state.get(key)!r}")
                reply = step.reply.lower()
                for item in turn.get("reply_all", []):
                    if item not in reply:
                        failures.append(f"reply: missing {item!r}")
                if turn.get("reply_any") and not any(item in reply for item in turn["reply_any"]):
                    failures.append(f"reply: missing any of {turn['reply_any']!r}")
                if turn.get("payload_kind") and (step.payload or {}).get("kind") != turn["payload_kind"]:
                    failures.append(f"payload: expected {turn['payload_kind']!r}, got {(step.payload or {}).get('kind')!r}")
                if turn.get("items_country"):
                    items = (step.payload or {}).get("items", [])
                    if not items or any(item.get("country") != turn["items_country"] for item in items):
                        failures.append(f"payload: expected only {turn['items_country']!r} destinations")
                if turn.get("all_legs"):
                    items = (step.payload or {}).get("items", [])
                    if not items or any(item.get(leg, {}).get("mode") != turn["all_legs"]
                                        for item in items for leg in ("out", "back")):
                        failures.append(f"payload: all legs should be {turn['all_legs']!r}")
                turns.append({"input": turn["text"], "reply": step.reply, "kind": (step.payload or {}).get("kind"),
                              "nlu": session.last_nlu, "seconds": round(elapsed, 4), "failures": failures})
                if pace_seconds:
                    time.sleep(pace_seconds)
            except Exception as exc:
                turns.append({"input": turn["text"], "failures": [f"exception: {type(exc).__name__}: {exc}"]})
                break
        results.append({"id": case["id"], "family": case["family"],
                        "pass": len(turns) == len(case["turns"]) and all(not t["failures"] for t in turns), "turns": turns})
    ordered = sorted(durations)
    nlu_counts = Counter(t.get("nlu", "exception") for c in results for t in c["turns"])
    return {"fixed_today": TODAY.isoformat(), "cases_passed": sum(c["pass"] for c in results),
            "cases_total": len(results), "turns": len(durations),
            "nlu_counts": dict(nlu_counts),
            "median_seconds": round(median(durations), 4) if durations else None,
            "p95_seconds": round(ordered[math.ceil(len(ordered) * .95) - 1], 4) if ordered else None,
            "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=("dev", "holdout", "final_holdout", "exact_h01"), required=True)
    parser.add_argument("--model", action="store_true", help="Use explicitly configured permitted model")
    parser.add_argument("--pace-seconds", type=float, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    llm = None
    if args.model:
        from core.config import get_settings
        from core.llm import build_llm
        settings = get_settings()
        if not settings.llm_enabled:
            raise SystemExit("No permitted model configured")
        llm = build_llm(settings)
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    cases = json.loads((DIR / f"dialogue_{args.set}_20261027.json").read_text(encoding="utf-8"))
    report = run(cases, agent, args.pace_seconds)
    report.update({"set": args.set, "mode": "configured model + rules" if llm else "rules"})
    if llm:
        report["model_completion"] = ("complete" if all(t.get("nlu") in ("llm", "llm+rules")
                                      for case in report["results"] for t in case["turns"]) else "incomplete")
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.set}: {report['cases_passed']}/{report['cases_total']}, turns={report['turns']}, "
          f"p50={report['median_seconds']}s, p95={report['p95_seconds']}s")
    return 0 if report["cases_passed"] == report["cases_total"] and report.get("model_completion") != "incomplete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
