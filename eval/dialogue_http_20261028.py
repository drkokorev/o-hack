"""Small synthetic HTTP smoke check against a running local demo."""
from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    def get(path: str) -> dict:
        with urlopen(base + path, timeout=20) as response:
            return json.load(response)

    def chat(text: str, session: str | None = None) -> tuple[dict, str | None]:
        body = json.dumps({"text": text, "session_id": session}, ensure_ascii=False).encode("utf-8")
        request = Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=20) as response:
            return json.load(response), response.headers.get("Cache-Control")

    checks = {"health": get("/health") == {"status": "ok"}}
    first, _ = chat("Хочу в Сочи в июне")
    weather, _ = chat("Какая там погода?", first["session_id"])
    resumed, _ = chat("на 5 ночей", first["session_id"])
    checks["interruption"] = ("средн" in weather["reply"].lower() and "не прогноз" in weather["reply"].lower()
                              and "города" in resumed["reply"].lower())

    first, _ = chat("Хочу в Казань")
    blocked, cache = chat("Напишите на synthetic@example.com", first["session_id"])
    resumed, _ = chat("в июне", first["session_id"])
    checks["privacy_and_resume"] = ("synthetic@example.com" not in json.dumps(blocked, ensure_ascii=False)
                                     and cache == "no-store" and "ноч" in resumed["reply"].lower())

    plan, _ = chat("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых")
    answer, _ = chat("Завтрак и бассейн есть?", plan["session_id"])
    checks["multiple_questions"] = (plan.get("payload", {}).get("kind") == "packages"
                                    and "питан" in answer["reply"].lower() and "бассейн" in answer["reply"].lower())
    with_baggage, _ = chat("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых, самолётом, нужен багаж")
    items = with_baggage.get("payload", {}).get("items", [])
    checks["baggage"] = bool(items) and all(item[direction]["mode"] == "plane" and item[direction]["baggage"]
                                             for item in items for direction in ("out", "back"))
    print(json.dumps(checks, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
