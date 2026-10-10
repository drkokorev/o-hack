from fastapi.testclient import TestClient

from apps.web import server

client = TestClient(server.app)


def test_web_flow_and_clinic_panel():
    client.post("/api/reset")
    start = client.post("/api/session").json()
    assert start["greeting"] and "Иванов Иван" in start["demo_patients"]
    before = len(client.get("/api/clinic").json()["bookings"])

    sid = start["session_id"]
    for text in ["Запишите к терапевту", "первый", "Тестов Тест"]:
        r = client.post("/api/message", json={"session_id": sid, "text": text}).json()
    assert r["done"] and r["nlu"] in ("rules", "llm") and r["latency_ms"] >= 0
    assert len(client.get("/api/clinic").json()["bookings"]) == before + 1


def test_unknown_session_is_404():
    assert client.post("/api/message", json={"session_id": "nope", "text": "hi"}).status_code == 404


def test_index_served():
    assert "Голосовой ассистент клиники" in client.get("/").text
