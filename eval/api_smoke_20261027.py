"""Black-box checks against a locally running instance; only synthetic inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results = []
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        health = client.get("/health")
        assert health.status_code == 200 and health.json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        info = client.get("/api/info")
        info.raise_for_status()
        data = info.json()
        assert data["destinations"] == 75 and data["hotels"] == 65924
        results.append({"id": "health_and_catalog", "pass": True,
                        "destinations": data["destinations"], "objects": data["hotels"],
                        "llm_state": data["llm_state"]})
        map_info = client.get("/api/map/catalog")
        map_info.raise_for_status()
        counts = map_info.json()["counts"]
        assert counts == {"hotel": 65924, "airport": 48101, "city": 161662, "beach": 7866, "camping": 8}
        clusters = client.get("/api/map/clusters", params={"kind": "hotel", "zoom": 3})
        clusters.raise_for_status()
        assert sum(item["count"] for item in clusters.json()["items"]) == 65924
        points = client.get("/api/map/points", params={"kind": "hotel", "limit": 10})
        points.raise_for_status()
        assert len(points.json()["items"]) == 10 and points.json()["next_cursor"] is not None
        point_id = points.json()["items"][0]["id"]
        detail = client.get("/api/map/point/" + point_id)
        detail.raise_for_status()
        assert detail.json()["id"] == point_id and detail.json()["source_url"]
        countries = client.get("/api/map/countries")
        countries.raise_for_status()
        assert len(countries.json()["items"]) == 250
        destinations = client.get("/api/map/destinations")
        destinations.raise_for_status()
        assert len(destinations.json()["items"]) == 75
        cities = client.get("/api/map/points", params={"kind": "city", "country_code": "RU", "limit": 10})
        cities.raise_for_status()
        assert len(cities.json()["items"]) == 10 and all(item["country_code"] == "RU" for item in cities.json()["items"])
        results.append({"id": "sourced_map_catalog", "pass": True, "counts": counts})

        def chat(text, session=None):
            response = client.post("/api/chat", json={"text": text, "session_id": session})
            response.raise_for_status()
            return response.json()

        first = chat("хочу увидеть горы, вайб лета, шашлыка, с другом, денег не много, главное еда и перелет, проживание в палатках")
        session = first["session_id"]
        chat("горы", session)
        filtered = chat("только Россия", session)
        assert filtered["payload"]["kind"] == "ideas"
        assert filtered["payload"]["items"] and all(item["country"] == "Россия" for item in filtered["payload"]["items"])
        travel = chat("какое время в пути?", session)
        last = chat("я не говорил про 7 ночей", session)
        assert "откуда" in travel["reply"].lower()
        assert "вы правы" in last["reply"].lower() and (last.get("payload") or {}).get("kind") == "ideas"
        results.append({"id": "H01_tent", "pass": True, "turns": 5, "nlu": last["nlu"]})
        client.post("/api/reset", json={"session_id": session}).raise_for_status()

        real = chat("В Ярославль, покажи реальные отели")
        assert "Overture Maps" in real["reply"] and "цены, наличие, удобства" in real["reply"].lower()
        assert "₽" not in real["reply"]
        results.append({"id": "real_hotel_records_no_rates", "pass": True, "nlu": real["nlu"]})
        client.post("/api/reset", json={"session_id": real["session_id"]}).raise_for_status()

        rooms = chat("Из Москвы в Казань с 3 по 6 июня 2027 двое взрослых, нужно 2 номера")
        assert rooms["payload"]["kind"] == "question" and "несколько номеров" in rooms["reply"]
        one_room = chat("один номер", rooms["session_id"])
        assert one_room["payload"]["kind"] == "packages"
        results.append({"id": "multi_room_no_fake_quote", "pass": True})
        client.post("/api/reset", json={"session_id": rooms["session_id"]}).raise_for_status()

        initial = chat("Хочу горы, возможно палатка")
        session = initial["session_id"]
        refused = chat("передумал, без палатки", session)
        assert not any("палатк" in chip for chip in refused["understood"])
        waiting = chat("из Москвы в Казань с 3 по 6 июня 2027 двое взрослых", session)
        assert waiting["payload"]["kind"] == "question" and "размещение" in waiting["reply"]
        assert chat("отель", session)["payload"]["kind"] == "packages"
        results.append({"id": "tent_refusal_then_lodging_question", "pass": True, "turns": 4})
        client.post("/api/reset", json={"session_id": session}).raise_for_status()

        weather = chat("Идеи на июль, воздух не ниже +25 градусов и вода от 22 градусов")
        assert weather["payload"]["kind"] == "ideas" and weather["payload"]["items"]
        assert "историческими" in weather["reply"].lower() and "не прогноз" in weather["reply"].lower()
        assert "поверхности моря" in weather["reply"].lower()
        assert any("воздух от 25" in chip for chip in weather["understood"])
        assert any("море от 22" in chip for chip in weather["understood"])
        results.append({"id": "temperature_historical_not_forecast", "pass": True})
        client.post("/api/reset", json={"session_id": weather["session_id"]}).raise_for_status()

        first = chat("Из Москвы в Ярославль с 10 по 14 июля 2027, двое взрослых, поездом")
        session = first["session_id"]
        assert first["payload"]["kind"] == "packages"
        assert "демонстрацион" in first["reply"].lower()
        assert all(item["out"]["mode"] == "train" and item["back"]["mode"] == "train"
                   for item in first["payload"]["items"])
        assert chat("выбираю первый вариант", session)["stage"] == "cart"
        assert chat("да, оформить", session)["stage"] == "payment"
        assert chat("оплата картой", session)["stage"] == "payment"
        final = chat("да, подтверждаю", session)
        assert final["stage"] == "booked" and "не списано" in final["reply"].lower()
        results.append({"id": "yaroslavl_train_mock_order", "pass": True, "turns": 5, "nlu": final["nlu"]})
        client.post("/api/reset", json={"session_id": session}).raise_for_status()
    Path(args.output).write_text(json.dumps({"base_url": args.base_url, "checks": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"API smoke: {len(results)}/{len(results)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
