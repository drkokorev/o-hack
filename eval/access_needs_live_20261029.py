"""Synthetic HTTP scenario against an explicitly configured model-enabled server."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18763")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    inputs = ["перелёт в коляске", "из Москвы в Казань 10.12.2027", "в одну сторону"]
    records, session = [], None
    for i, value in enumerate(inputs):
        if i:
            time.sleep(3)
        request = Request(args.url.rstrip("/") + "/api/chat",
                          data=json.dumps({"text": value, "session_id": session}, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=90) as response:
                item = json.load(response)
        except Exception as exc:
            records.append({"input": value, "error": type(exc).__name__})
            break
        session = item["session_id"]
        records.append({"input": value, "nlu": item["nlu"], "reply": item["reply"],
                        "kind": item.get("payload", {}).get("kind"),
                        "accessibility_status": item.get("payload", {}).get("accessibility_status"),
                        "input_sensitive": item.get("input_sensitive"), "understood": item.get("understood")})
    checks = {}
    if len(records) == 3 and not any("error" in row for row in records):
        checks = {
            "accessibility_input_processed_locally": records[0]["nlu"] == "rules" and records[0]["input_sensitive"],
            "model_used_for_ordinary_followup": records[1]["nlu"] in {"llm", "llm+rules"},
            "requirements_preserved": all(row["accessibility_status"] == "unverified" for row in records),
            "flight_results_not_claimed_accessible": records[2]["kind"] == "flight_results" and "не отобраны" in records[2]["reply"],
            "unspecified_children_not_mentioned": "детск" not in records[2]["reply"].lower(),
        }
    report = {"status": "complete" if checks else "incomplete", "checks": checks, "records": records}
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "checks": checks}, ensure_ascii=False))
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
