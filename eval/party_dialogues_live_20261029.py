"""Synthetic HTTP conversations against an explicitly model-enabled server."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18763")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scenarios = {
        "pregnancy": ["Я беременна, 24 недели, хочу в Казань", "из Москвы с 10 по 15 декабря 2027", "2 взрослых"],
        "infant": ["Только отель в Казани с 10 по 15 декабря 2027, 2 взрослых, ребёнок", "на дату заезда 8 месяцев"],
        "mixed_ages": ["Только отель в Казани с 10 по 15 декабря 2027, 2 взрослых, 2 ребёнка", "8 месяцев и 7 лет"],
        "count_from_ages": ["В Сочи из Москвы 10–15 декабря 2027, 2 взрослых и дети", "2 и 7 лет."],
        "pet": ["Перелёт из Москвы в Казань 10.12.2027 в одну сторону, 2 взрослых, с собакой 9 кг в салоне"],
        "diet": ["В Казань из Москвы 10–15 декабря 2027, 2 взрослых, аллергия на арахис и молоко", "арахис больше можно"],
    }
    results, checks = {}, {}
    for name, inputs in scenarios.items():
        session, records = None, []
        for value in inputs:
            # Avoid bursting requests into the shared remote provider.
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
                            "input_sensitive": item.get("input_sensitive"), "understood": item.get("understood")})
        results[name] = records
    if all(len(results[name]) == len(inputs) and all("error" not in row for row in results[name])
           for name, inputs in scenarios.items()):
        p, i, mixed, count, pet, diet = (results[name] for name in ("pregnancy", "infant", "mixed_ages", "count_from_ages", "pet", "diet"))
        checks = {
            "pregnancy_input_local_and_sensitive": p[0]["nlu"] == "rules" and p[0]["input_sensitive"],
            "ordinary_followup_used_model": p[1]["nlu"] in {"llm", "llm+rules"},
            "pregnancy_warning_survives_followups": "врач" in p[-1]["reply"].lower() and "не проверены" in p[-1]["reply"].lower(),
            "pregnancy_weeks_not_trip_length": not any("24 ноч" in row["reply"].lower() for row in p),
            "infant_age_answer_local_and_results": i[1]["nlu"] == "rules" and i[1]["input_sensitive"] and i[1]["kind"] == "service_results",
            "child_fares_unverified": "льготы не проверены" in i[1]["reply"].lower(),
            "mixed_ages_local_and_on_checkin": mixed[1]["nlu"] == "rules" and mixed[1]["input_sensitive"] and
                mixed[1]["kind"] == "service_results" and any("8 мес., 7 лет (на дату заезда)" in chip for chip in mixed[1]["understood"]),
            "punctuated_child_ages_local": count[1]["nlu"] == "rules" and count[1]["input_sensitive"] and
                count[1]["kind"] == "packages" and any("2, 7 лет" in chip for chip in count[1]["understood"]),
            "pet_details_unverified": all(piece in pet[0]["reply"].lower() for piece in ("9 кг", "в салоне", "не проверены")),
            "no_universal_pet_weight_limit": "до 8 кг" not in pet[0]["reply"].lower(),
            "allergy_handled_locally": diet[0]["nlu"] == "rules" and diet[0]["input_sensitive"],
            "allergy_not_claimed_safe": "перекрёстного" in diet[0]["reply"].lower() and "не отобраны" in diet[0]["reply"].lower(),
            "remaining_dietary_restriction_preserved": any("молок" in chip.lower() for chip in diet[1]["understood"]),
        }
    report = {"status": "complete" if checks else "incomplete", "checks": checks, "scenarios": results}
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "checks": checks}, ensure_ascii=False))
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
