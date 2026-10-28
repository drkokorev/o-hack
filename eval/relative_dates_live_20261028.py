"""Exercise synthetic conversations against a running model-enabled preview."""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from urllib.request import Request, urlopen

from apps.web import MONTHS_NOM
from core.ru import MONTHS_GEN
from domains.trips.textparse import parse_dates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18497")
    parser.add_argument("--output", required=True)
    parser.add_argument("--pause", type=float, default=0, help="seconds between synthetic messages")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    def request(path, body=None):
        encoded = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(base + path, data=encoded, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=50) as response:
            return json.load(response)

    info, voice = request("/api/info"), request("/api/voice")
    evidence = {"today": date.today().isoformat(), "model": info.get("llm"),
                "voice": voice, "conversations": [], "checks": {}}
    checks = evidence["checks"]
    checks["model_configured"] = info.get("llm") == "GigaChat-2-Max"
    checks["voice_ready"] = voice.get("backend") == "gigaam" and voice.get("status") == "ready"

    def conversation(name, texts):
        result, session = [], None
        for text in texts:
            if args.pause:
                time.sleep(args.pause)
            answer = request("/api/chat", {"text": text, "session_id": session})
            session = answer["session_id"]
            result.append({"text": text, "reply": answer["reply"], "nlu": answer["nlu"],
                           "understood": answer["understood"], "destination": answer["trip_summary"]["destination"],
                           "kind": (answer.get("payload") or {}).get("kind"), "ms": answer["ms"]})
        evidence["conversations"].append({"name": name, "turns": result})
        return result

    today = date.today()
    next_month, next_year = today.month % 12 + 1, today.year + (today.month == 12)
    next_label = f"{MONTHS_NOM[next_month - 1]} {next_year}"
    start = today + timedelta(days=3)
    start_label = f"начало: {start.day} {MONTHS_GEN[start.month - 1]} {start.year}"

    date_turns = conversation("примеры пользователя", ["Хочу куда-нибудь отдохнуть", "в следующем месяце",
                                                        "через 3 дня", "1.11-7.11"])
    checks["next_month_without_invented_city_or_day"] = (next_label in date_turns[1]["understood"] and
        not date_turns[1]["destination"] and not any("начало:" in x for x in date_turns[1]["understood"]))
    checks["three_days_is_a_start_not_duration"] = (start_label in date_turns[2]["understood"] and
        not date_turns[2]["destination"] and not any("ноч" in x for x in date_turns[2]["understood"]))
    begin, end = parse_dates("1.11-7.11", today)
    checks["numeric_range_keeps_both_dates"] = (begin is not None and end is not None and
        any(str(begin.day) in x and str(end.day) in x and "—" in x for x in date_turns[3]["understood"]) and
        not date_turns[3]["destination"])
    checks["chat_confirms_time_in_each_reply"] = ("учёл" in date_turns[1]["reply"].lower() and
        "учёл" in date_turns[2]["reply"].lower() and "учёл" in date_turns[3]["reply"].lower())

    trip = conversation("поездка в Казань", ["Хочу в Казань", "в следующем месяце", "на 7 ночей",
                                              "из Москвы", "двое взрослых", "Можно отменить бронь?"])
    checks["destination_survives_followups"] = all(x["destination"] == "Казань" for x in trip)
    checks["trip_month_and_duration_retained"] = (next_label in trip[1]["understood"] and
        any("7 ноч" in x for x in trip[2]["understood"]))
    checks["complete_trip_produces_packages"] = trip[4]["kind"] == "packages"
    checks["question_about_cancellation"] = "отмен" in trip[5]["reply"].lower()

    outside = conversation("место вне каталога", ["Хочу в Рейкьявик", "через 3 дня"])
    checks["real_unknown_place_not_erased"] = all("рейкьявик" in (x["destination"] or "").lower() for x in outside)
    checks["model_used_each_turn"] = all(t["nlu"] in {"llm", "llm+rules"}
        for c in evidence["conversations"] for t in c["turns"])
    evidence["passed"] = sum(checks.values())
    evidence["total"] = len(checks)
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(evidence, output, ensure_ascii=False, indent=2)
    print(json.dumps({"passed": evidence["passed"], "total": evidence["total"], "checks": checks}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
