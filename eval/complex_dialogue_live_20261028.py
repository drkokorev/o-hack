"""End-to-end synthetic conversations against the running model-enabled site."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18497")
    parser.add_argument("--output", required=True)
    parser.add_argument("--pause", type=float, default=3.0)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    results = []

    def chat(text, session=None):
        if args.pause:
            time.sleep(args.pause)
        body = json.dumps({"text": text, "session_id": session}, ensure_ascii=False).encode("utf-8")
        with urlopen(Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"}), timeout=45) as r:
            data = json.load(r)
        results.append({"text": text, "reply": data["reply"], "understood": data["understood"],
                        "destination": data["trip_summary"]["destination"],
                        "kind": (data.get("payload") or {}).get("kind"),
                        "field": (data.get("payload") or {}).get("field"), "nlu": data["nlu"]})
        return data

    one = chat("в париж с 1 декабря по 7 с евушкой за 200 тысяч рублей на самолете")
    shown = " | ".join(one["understood"]).replace("\u00a0", " ").lower()
    two = chat("из Москвы", one["session_id"])
    three = chat("двое взрослых", one["session_id"])
    conflict = chat("из Москвы в Париж с 1 декабря по 7 на 5 ночей двое взрослых")
    resolved = chat("на 5 ночей", conflict["session_id"])
    vague = chat("хочу куда-то потеплее и подешевле в следующем месяце на двоих")
    checks = {
        "paris_and_period": one["trip_summary"]["destination"] == "Париж" and "1 декабря — 7 декабря" in shown,
        "six_nights": "6 ночей" in shown,
        "two_travellers": "2 путешественника" in shown,
        "budget_and_plane": "200 000" in shown and "самолёт" in shown,
        "asks_only_missing_field": (one.get("payload") or {}).get("field") in {"origin", "people"} and
                                   ((one.get("payload") or {}).get("field") == "origin" or
                                    any("примерно по IP" in chip for chip in one["understood"])),
        "origin_followup_preserves_trip": (two["trip_summary"]["destination"] == "Париж" and
                                          "из: Москва" in two["understood"] and "6 ночей" in two["understood"]),
        "adults_followup_preserves_budget": (three["trip_summary"]["destination"] == "Париж" and
            any("2 взрослых" in chip for chip in three["understood"]) and
            any("200" in chip and "000" in chip for chip in three["understood"])),
        "conflict_is_explained": (conflict.get("payload") or {}).get("field") == "duration_conflict" and
                                 "6 ночей" in conflict["reply"] and "5 ночей" in conflict["reply"],
        "conflict_resolution": (any("6 декабря" in chip for chip in resolved["understood"]) and
                                any("5 ночей" in chip for chip in resolved["understood"])),
        "vague_warm_and_economy_are_visible": ("тепло" in vague["understood"] and
                                               "недорого" in vague["understood"] and
                                               "2 путешественника" in vague["understood"]),
        "model_used_each_turn": all(x["nlu"] in {"llm", "llm+rules"} for x in results),
    }
    report = {"passed": sum(checks.values()), "total": len(checks), "checks": checks, "turns": results}
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({"passed": report["passed"], "total": report["total"], "checks": checks}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
