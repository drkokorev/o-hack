"""Replay synthetic suspected problems through the running local website API."""
import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

CASES = [
    ("P04", ["В Сочи с ребёнком шести лет и собакой"]),
    ("P05", ["В Сочи едем я, жена и ребёнок"]),
    ("B06", ["В Париж бюджет до 100 долларов"]),
    ("B07", ["В Париж максимум 1,5 миллиона рублей на всю поездку"]),
    ("T07", ["Хочу в Сочи, боюсь летать, но запрета на самолёт нет"]),
    ("T07_control", ["В Сочи хочу самолёт"]),
    ("T08", ["Хочу в Сочи, желательно недолго ехать"]),
    ("H02", ["В Анталию пять звёзд и всё включено"]),
    ("H03", ["В Сочи гостиница с бассейном и вайфаем, спа не нужно"]),
    ("H06", ["В Казань отель с кухней и парковкой"]),
    ("W03", ["Хочу за границу, но Турцию исключаем", "в июле"]),
    ("W05", ["Хочу в Сочи, воздух от 24 до 30 градусов, море от 22 градусов"]),
    ("W08", ["Возможно поедем втроём в Сочи"]),
    ("W09", ["В Сочи вода не теплее 27 градусов"]),
    ("A07", ["В Сочи возможно полетим самолётом"]),
    ("A09", ["В Казань хочу на автобусе"]),
    ("A09_full", ["Из Москвы в Казань с 1 по 5 декабря 2026 двое взрослых на автобусе"]),
    ("A12", ["Хочу безвизовую поездку в начале марта 2027, кроме Египта"]),
    ("A15", ["В Анталию, температура моря от 23 до 27 градусов"]),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18185")
    parser.add_argument("--output", required=True)
    parser.add_argument("--pause", type=float, default=2.5)
    args = parser.parse_args()
    results = []
    for cid, messages in CASES:
        session_id = None
        turns = []
        for text in messages:
            if args.pause:
                time.sleep(args.pause)
            body = json.dumps({"text": text, "session_id": session_id, "detected_city": "Moscow"}, ensure_ascii=False).encode("utf-8")
            try:
                request = Request(args.url.rstrip("/") + "/api/chat", body, {"Content-Type": "application/json"})
                with urlopen(request, timeout=45) as response:
                    answer = json.load(response)
                session_id = answer["session_id"]
                payload = answer.get("payload") or {}
                items = [{"name": item.get("name"), "country": item.get("country")} for item in payload.get("items", [])]
                turns.append({"text": text, "nlu": answer.get("nlu"), "reply": answer.get("reply"),
                              "understood": answer.get("understood"), "kind": payload.get("kind"), "items": items})
            except Exception as exc:
                turns.append({"text": text, "exception_type": type(exc).__name__})
                break
        results.append({"id": cid, "turns": turns})
        Path(args.output).write_text(json.dumps({"synthetic_ip_hint": "Moscow", "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{cid}: {','.join(x.get('nlu','error') for x in turns)}", flush=True)


if __name__ == "__main__":
    main()
