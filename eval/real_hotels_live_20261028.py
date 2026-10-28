"""Synthetic source-hotel selection and route change against the running site."""
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
    turns = []

    def chat(text, session=None):
        if args.pause:
            time.sleep(args.pause)
        body = json.dumps({"text": text, "session_id": session}, ensure_ascii=False).encode("utf-8")
        with urlopen(Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"}), timeout=45) as response:
            answer = json.load(response)
        payload = answer.get("payload") or {}
        turns.append({"text": text, "reply": answer["reply"], "nlu": answer["nlu"],
                      "understood": answer["understood"], "kind": payload.get("kind"),
                      "destination": answer["trip_summary"]["destination"]})
        return answer

    initial = chat("из Москвы в Париж с 1 декабря по 7 двое взрослых только без пересадок")
    session = initial["session_id"]
    listed = chat("покажи реальные отели", session)
    items = (listed.get("payload") or {}).get("items") or []
    chosen_record = next((item for item in items if item["name"] == "Campanile Taverny"), None)
    chosen_number = items.index(chosen_record) + 1 if chosen_record else 0
    chosen = chat(str(chosen_number or 2), session)
    relaxed = chat("можно с пересадкой", session)
    listed_again = chat("покажи реальные отели", session)
    named = chat("campanile taverny", session)
    found = chat("найди отель Campanile Taverny", session)
    found_items = (found.get("payload") or {}).get("items") or []
    found_selection = chat("1", session)

    selection = (chosen.get("payload") or {}).get("hotel") or {}
    named_selection = (named.get("payload") or {}).get("hotel") or {}
    final_selection = (found_selection.get("payload") or {}).get("hotel") or {}
    demo_id = "paris-h" + (chosen_record or {}).get("id", "").removeprefix("overture:")
    packages = (relaxed.get("payload") or {}).get("items") or []
    checks = {
        "direct_route_limitation_explained": (initial.get("payload") or {}).get("reason") == "no_transport",
        "source_list_has_records_and_no_prices": bool(items) and "Overture Maps" in listed["reply"] and "₽" not in listed["reply"],
        "number_selects_exact_source_id": bool(chosen_record) and selection.get("id") == chosen_record["id"],
        "selection_has_no_fake_price": "Campanile Taverny" in chosen["reply"] and "₽" not in chosen["reply"],
        "allow_transfer_preserves_selected_hotel": bool(packages) and all(item["hotel"]["id"] == demo_id for item in packages),
        "packages_are_marked_demo": "демонстрацион" in relaxed["reply"].lower(),
        "name_selects_same_source_id": bool(chosen_record) and named_selection.get("id") == chosen_record["id"],
        "name_search_uses_open_catalog": bool(chosen_record) and bool(found_items) and any(x["id"] == chosen_record["id"] for x in found_items),
        "search_selection_keeps_identity": bool(chosen_record) and final_selection.get("id") == chosen_record["id"],
        "model_used_each_turn": all(item["nlu"] in {"llm", "llm+rules"} for item in turns),
    }
    report = {"passed": sum(checks.values()), "total": len(checks), "checks": checks, "turns": turns}
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({"passed": report["passed"], "total": report["total"], "checks": checks}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
