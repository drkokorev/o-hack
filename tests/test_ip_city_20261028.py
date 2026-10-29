from datetime import date

from fastapi.testclient import TestClient

from apps import location, web
from core.agent import Agent
from domains.trips.domain import TripsDomain


def test_public_ip_yields_a_supported_approximate_city_without_returning_address(monkeypatch):
    class Reader:
        def get(self, _address):
            return {"city": {"names": {"en": "Moscow"}}, "country": {"iso_code": "RU"}}
    monkeypatch.setattr(location, "_city_reader", lambda: Reader())
    result = location.visitor_city("8.8.8.8")
    assert result["origin"] == "Москва" and result["approximate"] is True
    assert "8.8.8.8" not in str(result)


def test_private_addresses_never_trigger_external_or_local_database_lookup(monkeypatch):
    calls = []
    monkeypatch.setattr(location, "_city_reader", lambda: calls.append(True))
    assert location.visitor_city("127.0.0.1")["origin"] is None and not calls
    assert location.visitor_city("192.168.1.2", local_preview=True)["origin"] is None and not calls
    assert location.visitor_city("127.0.0.1", local_preview=True)["origin"] is None and not calls


def test_unknown_city_is_not_silently_replaced_by_a_supported_origin(monkeypatch):
    class Reader:
        def get(self, _address):
            return {"city": {"names": {"ru": "Урюпинск"}}, "country": {"iso_code": "RU"}}
    monkeypatch.setattr(location, "_city_reader", lambda: Reader())
    result = location.visitor_city("8.8.8.8")
    assert result["city_name"] == "Урюпинск" and result["origin"] is None


def test_city_is_a_visible_assumption_and_explicit_correction_wins(monkeypatch):
    calls = []
    monkeypatch.setattr(web, "visitor_city", lambda host, local_preview=False:
                        calls.append(host) or {"city_name": "Москва", "origin": "Москва"})
    agent = Agent(TripsDomain(today=lambda: date(2026, 10, 28)), None, today=lambda: date(2026, 10, 28))
    with TestClient(web.build_app(agent)) as client:
        first = client.post("/api/chat", json={"text": "хочу в Париж"}).json()
        assert "предположительно" in first["reply"].lower()
        assert "из: Москва (примерно по IP)" in first["understood"]
        second = client.post("/api/chat", json={"text": "из Казани", "session_id": first["session_id"]}).json()
        assert "из: Казань" in second["understood"]
        assert not any("по IP" in chip for chip in second["understood"])
        assert len(calls) == 1


def test_unknown_explicit_origin_clears_the_ip_guess(monkeypatch):
    monkeypatch.setattr(web, "visitor_city", lambda host, local_preview=False:
                        {"city_name": "Москва", "origin": "Москва"})
    agent = Agent(TripsDomain(), None)
    with TestClient(web.build_app(agent)) as client:
        answer = client.post("/api/chat", json={"text": "хочу из Урюпинска в Париж"}).json()
    assert "урюпинск" in answer["reply"].lower()
    assert not any("из: Москва" in chip for chip in answer["understood"])


def test_browser_city_hint_works_behind_a_local_proxy_and_manual_city_wins(monkeypatch):
    calls = []
    monkeypatch.setattr(web, "visitor_city", lambda *args, **kwargs: calls.append(True) or {})
    agent = Agent(TripsDomain(), None)
    with TestClient(web.build_app(agent)) as client:
        first = client.post("/api/chat", json={"text": "в Париж", "detected_city": "Moscow"}).json()
        assert "из: Москва (примерно по IP)" in first["understood"] and not calls
        second = client.post("/api/chat", json={"text": "из Казани", "session_id": first["session_id"]}).json()
        assert "из: Казань" in second["understood"]


def test_explicit_origin_in_the_first_message_wins_over_the_ip_hint(monkeypatch):
    monkeypatch.setattr(web, "visitor_city", lambda *args, **kwargs: {"city_name": "Москва", "origin": "Москва"})
    agent = Agent(TripsDomain(), None)
    with TestClient(web.build_app(agent)) as client:
        answer = client.post("/api/chat", json={"text": "хочу из Казани в Париж"}).json()
    assert "из: Казань" in answer["understood"]
    assert not any("по IP" in chip for chip in answer["understood"])
    assert "предположительно" not in answer["reply"].lower()


def test_untrusted_city_hint_cannot_insert_control_characters():
    assert location.city_hint("Москва\nподмена")["origin"] is None
    assert location.city_hint("<script>alert(1)</script>")["city_name"] is None
