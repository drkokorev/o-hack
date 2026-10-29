from datetime import date

from fastapi.testclient import TestClient

from apps import location, web
from core.agent import Agent
from domains.trips.domain import TripsDomain


def test_documents_are_readable_without_calling_a_model_or_creating_a_trip():
    class NoCalls:
        def complete(self, *args, **kwargs):
            raise AssertionError("Reading a legal document must not call the model")

    agent = Agent(TripsDomain(), NoCalls())
    with TestClient(web.build_app(agent)) as client:
        for path, title in [("/terms", "Условия использования"), ("/privacy", "Политика конфиденциальности")]:
            response = client.get(path)
            assert response.status_code == 200 and title in response.text
            assert "ДЕМОНСТРАЦИОННАЯ РЕДАКЦИЯ" in response.text
            assert "Оператор сервиса ещё не указан" in response.text
            assert response.headers["cache-control"] == "no-store"
            assert "script-src" not in response.headers["content-security-policy"]
            assert "default-src 'none'" in response.headers["content-security-policy"]


def test_operator_details_are_configurable_and_html_is_escaped(monkeypatch):
    monkeypatch.setenv("ODIN_OPERATOR_NAME", 'Тестовая команда <script>alert("x")</script>')
    monkeypatch.setenv("ODIN_OPERATOR_ADDRESS", "Тестовый адрес <b>1</b>")
    monkeypatch.setenv("ODIN_OPERATOR_EMAIL", "privacy@example.test")
    with TestClient(web.build_app()) as client:
        response = client.get("/privacy")
    assert "mailto:privacy@example.test" in response.text
    assert "&lt;script&gt;" in response.text and "<script>" not in response.text
    assert "&lt;b&gt;1&lt;/b&gt;" in response.text
    assert "Оператор сервиса ещё не указан" not in response.text


def test_invalid_operator_contact_cannot_inject_a_link(monkeypatch):
    monkeypatch.setenv("ODIN_OPERATOR_EMAIL", 'javascript:alert(1)" onclick="alert(2)')
    with TestClient(web.build_app()) as client:
        text = client.get("/privacy").text
    assert "javascript:" not in text and 'onclick="' not in text
    assert "Контакт для обращений ещё не указан" in text


def test_reading_documents_preserves_the_current_trip_and_manual_correction():
    fixed = lambda: date(2026, 10, 28)
    agent = Agent(TripsDomain(today=fixed), None, today=fixed)
    with TestClient(web.build_app(agent)) as client:
        first = client.post("/api/chat", json={"text": "Из Москвы в Сочи с 10 по 17 июня 2027 вдвоём"}).json()
        assert "из: Москва" in first["understood"]
        client.get("/terms")
        client.get("/privacy")
        second = client.post("/api/chat", json={"text": "теперь из Казани", "session_id": first["session_id"]}).json()
    assert "из: Казань" in second["understood"]
    assert any("Сочи" in chip for chip in second["understood"])
    assert second["session_id"] == first["session_id"]


def test_missing_city_database_does_not_contact_an_external_service(monkeypatch):
    import urllib.request

    monkeypatch.setattr(location, "_city_reader", lambda: None)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("External IP lookup is forbidden")))
    assert location.visitor_city("8.8.8.8")["origin"] is None
    assert location.visitor_city("127.0.0.1", local_preview=True)["origin"] is None
    with TestClient(web.build_app()) as client:
        assert client.get("/api/visitor-city").json()["origin"] is None
        assert client.post("/api/chat", json={"text": "из Казани в Сочи"}).status_code == 200


def test_a_foreign_namesake_cannot_become_a_russian_departure_city(monkeypatch):
    class Reader:
        def get(self, _address):
            return {"city": {"names": {"en": "Moscow"}}, "country": {"iso_code": "US"}}

    monkeypatch.setattr(location, "_city_reader", lambda: Reader())
    result = location.visitor_city("8.8.8.8")
    assert result["origin"] is None
