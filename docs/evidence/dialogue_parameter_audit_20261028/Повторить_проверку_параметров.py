"""Synthetic, pre-registered cases against the site's Agent and real configured LLM.

No private data is included. The script reads an existing env file only at runtime;
it records no secrets, tokens, session IDs, or raw model responses.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import date
from pathlib import Path


CASES = []


def case(id, group, turns, *, eq=None, one_of=None, includes=None, excludes=None,
         reply_any=None, kind=None, field=None, exact_list_choice=None, note=""):
    CASES.append(dict(id=id, group=group, turns=turns if isinstance(turns, list) else [turns],
                      eq=eq or {}, one_of=one_of or {}, includes=includes or {}, excludes=excludes or {},
                      reply_any=reply_any or [], kind=kind, field=field,
                      exact_list_choice=exact_list_choice, note=note))


# Expected values are specified before the model calls. Each case is a new synthetic session.
case("G01", "Направление и отправление", "Хочу съездить в Екатеринбург", eq={"dest_id": "yekaterinburg"})
case("G02", "Направление и отправление", "Хочу путешествие в Lisbon", eq={"dest_id": "lisbon"})
case("G03", "Направление и отправление", "В Сочи из Санкт-Петербурга", eq={"dest_id": "sochi", "origin": "Санкт-Петербург"})
case("G04", "Направление и отправление", "Поеду из Казани в Ярославль", eq={"dest_id": "yaroslavl", "origin": "Казань"})
case("G05", "Направление и отправление", "Хочу в Амстердам", eq={"dest_id": None}, reply_any=["Амстердам", "амстердам"])
case("G06", "Направление и отправление", "Из Томска в Сочи", eq={"dest_id": "sochi", "origin": None}, reply_any=["Томск", "томск"])

case("D01", "Даты и длительность", "В Сочи с 27 ноября по 2 декабря 2026", eq={"date_from": "2026-11-27", "date_to": "2026-12-02", "nights": 5})
case("D02", "Даты и длительность", "Казань 05.12.2026–10.12.2026", eq={"date_from": "2026-12-05", "date_to": "2026-12-10", "nights": 5})
case("D03", "Даты и длительность", "В Париж с 30 декабря 2026 по 5 января 2027", eq={"date_from": "2026-12-30", "date_to": "2027-01-05", "nights": 6})
case("D04", "Даты и длительность", "В Сочи послезавтра", eq={"date_from": "2026-10-30"})
case("D05", "Даты и длительность", "В Казань через две недели", eq={"date_from": "2026-11-11"})
case("D06", "Даты и длительность", "В Сочи в конце января 2027 года", eq={"month": 1, "year": 2027, "month_part": "late", "date_from": None})
case("D07", "Даты и длительность", "В Казань весной 2027 года", eq={"season": "spring", "year": 2027, "date_from": None})
case("D08", "Даты и длительность", "В Париж на пять ночей", eq={"nights": 5})
case("D09", "Даты и длительность", "В Сочи на 4 дня", eq={"trip_days_min": 4, "trip_days_max": 4})
case("D10", "Даты и длительность", "В Сочи с 14 по 10 ноября 2027", kind="question", reply_any=["дат", "раньше", "период"])
case("D11", "Даты и длительность", "В Сочи с 10 по 14 ноября 2025", kind="question", reply_any=["дат", "прошл", "период"])
case("D12", "Даты и длительность", "В Париж в ноябре 2028 на неделю", eq={"month": 11, "year": 2028, "nights": 7, "date_from": None})

case("P01", "Путешественники и номера", "В Сочи двое взрослых и двое детей 7 и 11 лет", eq={"adults": 2, "children": 2}, includes={"children_ages": [7, 11]})
case("P02", "Путешественники и номера", "В Сочи едем втроём", eq={"party_size": 3, "adults": None})
case("P03", "Путешественники и номера", "В Казань один взрослый без детей", eq={"adults": 1, "children": 0})
case("P04", "Путешественники и номера", "В Сочи с ребёнком шести лет и собакой", eq={"children": 1, "pets": True}, includes={"children_ages": [6]})
case("P05", "Путешественники и номера", "В Сочи едем я, жена и ребёнок", eq={"party_size": 3, "children": 1})
case("P06", "Путешественники и номера", "В Париж двое взрослых, ребёнок и два отдельных номера", eq={"adults": 2, "children": 1, "rooms": 2})
case("P07", "Путешественники и номера", "В Сочи поедем с детьми, число пока неизвестно", eq={"children_unknown": True, "children": None})

case("B01", "Бюджет", "В Казань бюджет 85 тысяч рублей на всех", eq={"budget_total": 85000, "budget_per_person": None})
case("B02", "Бюджет", "В Сочи до 45 тысяч рублей на человека", eq={"budget_per_person": 45000, "budget_total": None})
case("B03", "Бюджет", "В Париж гостиница до 7500 рублей за ночь", eq={"budget_night": 7500, "budget_total": None})
case("B04", "Бюджет", "В Сочи бюджет от 120 до 150 тысяч рублей", eq={"budget_total": 150000})
case("B05", "Бюджет", "В Сочи бюджет около 150к на всю поездку", eq={"budget_total": 150000})
case("B06", "Бюджет", "В Париж бюджет до 100 долларов", eq={"budget_total": None, "budget_per_person": None})
case("B07", "Бюджет", "В Париж максимум 1,5 миллиона рублей на всю поездку", eq={"budget_total": 1500000})
case("B08", "Бюджет", "В Казань хочется подешевле, точной суммы нет", eq={"economy": True, "budget_total": None})

case("T01", "Транспорт и багаж", "Из Москвы в Казань поедем поездом", eq={"transport": "train"})
case("T02", "Транспорт и багаж", "Из Казани в Сочи без самолёта", eq={"transport": "train"})
case("T03", "Транспорт и багаж", "В Сочи на машине, не самолётом и не поездом", eq={"transport": "none"})
case("T04", "Транспорт и багаж", "В Париж самолётом без пересадок и с багажом", eq={"transport": "plane", "direct_only": True, "baggage": True})
case("T05", "Транспорт и багаж", "В Сочи на самолёте, только ручная кладь, без сдаваемого багажа", eq={"transport": "plane", "baggage": False})
case("T06", "Транспорт и багаж", "В Сочи, полёт не дольше 6 часов", eq={"max_travel_hours": 6})
case("T07", "Транспорт и багаж", "Хочу в Сочи, боюсь летать, но запрета на самолёт нет", eq={"flight_concern": True, "transport": None})
case("T08", "Транспорт и багаж", "Хочу в Сочи, желательно недолго ехать", eq={"prefer_short_travel": True, "max_travel_hours": None})

case("H01", "Жильё и условия", "В Сочи отель от четырёх звёзд с завтраком", eq={"lodging": "hotel", "stars_min": 4, "meal": "breakfast"})
case("H02", "Жильё и условия", "В Анталию пять звёзд и всё включено", eq={"stars_min": 5, "meal": "all_inclusive"})
case("H03", "Жильё и условия", "В Сочи гостиница с бассейном и вайфаем, спа не нужно", includes={"hotel_wishes": ["pool", "wifi"]}, excludes={"hotel_wishes": ["spa"]})
case("H04", "Жильё и условия", "В Сочи гостиница с бесплатной отменой", eq={"free_cancellation": True})
case("H05", "Жильё и условия", "На Алтай со своей палаткой, отель не нужен", eq={"lodging": "tent"})
case("H06", "Жильё и условия", "В Казань отель с кухней и парковкой", includes={"hotel_wishes": ["kitchen", "parking"]})
case("H07", "Жильё и условия", "В Анталию отель на первой линии у моря", includes={"hotel_wishes": ["beach_line"]})
case("H08", "Жильё и условия", "В Сочи гостиница с детским клубом и тренажёрным залом", includes={"hotel_wishes": ["kids_club", "gym"]})
case("H09", "Жильё и условия", "В Сочи с котом", eq={"pets": True})
case("H10", "Жильё и условия", "В Париж нужен полупансион", eq={"meal": "half_board"})

case("W01", "Предпочтения и погода", "Летом хочу в горы и на природу, море не интересует", eq={"season": "summer"}, includes={"trip_types": ["mountains", "nature"]}, excludes={"trip_types": ["sea", "beach"]})
case("W02", "Предпочтения и погода", "Хочу путешествие только по России", eq={"abroad": False})
case("W03", "Предпочтения и погода", "Хочу за границу, но Турцию исключаем", eq={"abroad": True}, includes={"excluded_countries": ["Турция"]})
case("W04", "Предпочтения и погода", "Хочу за границу без визы", eq={"visa_free_requested": True, "abroad": True})
case("W05", "Предпочтения и погода", "Хочу в Сочи, воздух от 24 до 30 градусов, море от 22 градусов", eq={"air_min_temp": 24, "air_max_temp": 30, "sea_min_temp": 22})
case("W06", "Предпочтения и погода", "На Байкал в феврале, температура воздуха не ниже минус 5 градусов", eq={"air_min_temp": -5})
case("W07", "Предпочтения и погода", "Хочу культурный отдых и музеи в феврале", includes={"trip_types": ["culture"]}, eq={"month": 2})
case("W08", "Предпочтения и погода", "Возможно поедем втроём в Сочи", eq={"party_size": 3}, includes={"tentative_fields": ["party_size"]})
case("W09", "Предпочтения и погода", "В Сочи вода не теплее 27 градусов", eq={"sea_max_temp": 27})

case("C01", "Изменения в диалоге", ["Из Москвы в Сочи с 5 по 12 декабря 2026 на двоих", "Нет, вылет из Казани"], eq={"origin": "Казань", "dest_id": "sochi", "date_from": "2026-12-05", "date_to": "2026-12-12", "party_size": 2})
case("C02", "Изменения в диалоге", ["В Сочи бюджет 150 тысяч рублей", "Бюджет уменьшаем до 90 тысяч рублей"], eq={"budget_total": 90000, "dest_id": "sochi"})
case("C03", "Изменения в диалоге", ["В Казань поездом", "Передумал, полетим самолётом"], eq={"transport": "plane", "dest_id": "kazan"})
case("C04", "Изменения в диалоге", ["В Сочи с 5 по 12 декабря 2026", "На два дня позже"], eq={"date_from": "2026-12-07", "date_to": "2026-12-14", "nights": 7})
case("C05", "Изменения в диалоге", ["В Сочи отель с бассейном и завтраком", "Бассейн не нужен, завтрак оставьте"], eq={"meal": "breakfast"}, excludes={"hotel_wishes": ["pool"]})
case("C06", "Изменения в диалоге", ["В Сочи на двоих", "Передумал, лучше в Казань"], eq={"dest_id": "kazan", "party_size": 2})
case("C07", "Изменения в диалоге", ["В Сочи двое взрослых", "Нет, нас трое взрослых"], eq={"adults": 3})
case("C08", "Изменения в диалоге", ["В Сочи с 5 по 12 декабря 2026", "Поменяй даты на 10–15 декабря 2026"], eq={"date_from": "2026-12-10", "date_to": "2026-12-15", "nights": 5})
case("C09", "Изменения в диалоге", ["В Париж без пересадок", "Можно с пересадкой"], eq={"direct_only": False})
case("C10", "Изменения в диалоге", ["В Сочи с бесплатной отменой", "Отмена больше не важна"], one_of={"free_cancellation": [None, False]})
case("C11", "Изменения в диалоге", ["В Сочи воздух от 25 градусов", "Температура больше не важна"], eq={"air_min_temp": None, "dest_id": "sochi"})
case("C12", "Изменения в диалоге", ["В Сочи на самолёте с багажом", "Багаж больше не нужен"], eq={"baggage": False, "transport": "plane"})

case("R01", "Реальные отели", ["В Париж", "Покажи реальные отели без цен", "1"], kind="real_hotel_selected", exact_list_choice=[1, 1], note="Выбранная запись должна иметь ID первого объекта ранее показанного списка.")
case("R02", "Реальные отели", ["В Париж", "Покажи реальные отели без цен", "9"], eq={"selected_real_hotel": None}, note="Несуществующий номер не должен выбирать другой отель.")
case("R03", "Реальные отели", ["В Париж", "Найди отель Campanile Taverny", "1"], kind="real_hotel_selected", eq={"selected_real_hotel.name": "Campanile Taverny"})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--env-file", required=True)
    p.add_argument("--cases", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--pause", type=float, default=2.5)
    p.add_argument("--write-cases", action="store_true")
    args = p.parse_args()
    today = date(2026, 10, 28)
    if args.write_cases:
        Path(args.cases).write_text(json.dumps({"today": today.isoformat(), "cases": CASES}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Registered {len(CASES)} cases / {sum(len(c['turns']) for c in CASES)} messages.", flush=True)
        return
    fixture = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = fixture["cases"]
    sys.path.insert(0, args.project)
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=True)
    from core.agent import Agent
    from core.config import get_settings
    from core.llm import build_llm
    from apps.web import understood
    from domains.trips.domain import TripsDomain
    settings = get_settings()
    llm = build_llm(settings)
    if llm is None:
        raise SystemExit("Real model is not configured; no evaluation was run.")
    logging.disable(logging.CRITICAL)
    agent = Agent(TripsDomain(today=lambda: today), llm, today=lambda: today)
    try:
        tested_commit = subprocess.run(["git", "-C", args.project, "rev-parse", "HEAD"], check=True,
                                       text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        tested_commit = None  # a source archive has no Git metadata
    results = []
    path = Path(args.output)

    def get(state, name):
        obj = state
        for part in name.split("."):
            obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
        return obj

    def persist(complete=False):
        summary = {s: sum(x["status"] == s for x in results) for s in ("PASS", "FAIL", "INCONCLUSIVE")}
        path.write_text(json.dumps({"commit": tested_commit, "model": settings.llm_model,
                                    "today": today.isoformat(), "complete": complete, "planned": len(cases),
                                    "summary": summary, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for index, c in enumerate(cases, 1):
        session = agent.new_session()
        turns = []
        for message in c["turns"]:
            if args.pause: time.sleep(args.pause)
            before = getattr(getattr(llm, "breaker", None), "total_failures", 0)
            started = time.monotonic()
            try:
                step = agent.handle(session, message)
                payload = step.payload if isinstance(step.payload, dict) else {}
                turns.append({"text": message, "reply": step.reply, "kind": payload.get("kind"),
                              "field": payload.get("field"), "nlu": session.last_nlu,
                              "provider_failures_added": getattr(getattr(llm, "breaker", None), "total_failures", 0) - before,
                              "ms": round((time.monotonic() - started) * 1000), "chips": understood(session.state),
                              "state": session.state.params().model_dump(mode="json", exclude_none=True),
                              "selected_real_hotel": session.state.selected_real_hotel,
                              "listed_hotel_ids": [x.get("id") for x in payload.get("items", [])] if payload.get("kind") == "real_hotels" else []})
            except Exception as exc:
                turns.append({"text": message, "exception_type": type(exc).__name__})
                break
        differences = []
        state = session.state
        for name, expected in c["eq"].items():
            actual = get(state, name)
            if hasattr(actual, "isoformat"): actual = actual.isoformat()
            if actual != expected: differences.append({"check": name, "expected": expected, "actual": actual})
        for name, choices in c["one_of"].items():
            actual = get(state, name)
            if actual not in choices: differences.append({"check": name, "expected_one_of": choices, "actual": actual})
        for name, expected in c["includes"].items():
            actual = get(state, name) or []
            if any(item not in actual for item in expected): differences.append({"check": name, "expected_contains": expected, "actual": actual})
        for name, forbidden in c["excludes"].items():
            actual = get(state, name) or []
            if any(item in actual for item in forbidden): differences.append({"check": name, "expected_without": forbidden, "actual": actual})
        last = turns[-1] if turns else {}
        if c["kind"] and last.get("kind") != c["kind"]: differences.append({"check": "kind", "expected": c["kind"], "actual": last.get("kind")})
        if c["field"] and last.get("field") != c["field"]: differences.append({"check": "field", "expected": c["field"], "actual": last.get("field")})
        if c["reply_any"] and not any(x.lower() in last.get("reply", "").lower() for x in c["reply_any"]):
            differences.append({"check": "reply", "expected_any": c["reply_any"], "actual": last.get("reply", "")[:300]})
        if c["exact_list_choice"]:
            turn_index, position = c["exact_list_choice"]
            ids = turns[turn_index].get("listed_hotel_ids", []) if len(turns) > turn_index else []
            expected = ids[position - 1] if len(ids) >= position else None
            actual = (state.selected_real_hotel or {}).get("id")
            if not expected or actual != expected: differences.append({"check": "source_record_id", "expected": expected, "actual": actual})
        model_used = len(turns) == len(c["turns"]) and all(t.get("nlu") in {"llm", "llm+rules"} for t in turns)
        status = "INCONCLUSIVE" if not model_used else "FAIL" if differences else "PASS"
        results.append({"id": c["id"], "group": c["group"], "status": status, "differences": differences, "turns": turns})
        print(f"{index}/{len(cases)} {c['id']} {status} ({','.join(t.get('nlu', '?') for t in turns)})", flush=True)
        persist()
    persist(True)


if __name__ == "__main__":
    main()
