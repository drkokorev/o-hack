"""Privacy-boundary checks use invented data and a fake model only."""
from datetime import date
import re

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from core.guard import mask_sensitive_data
from domains.trips.domain import TripsDomain
from tests.conftest import FakeLLM


TODAY = date(2026, 10, 28)


@pytest.mark.parametrize("text, secrets", [
    ("Меня зовут Марина Петрова, хочу в Сочи", ("Марина", "Петрова")),
    ("Подберите поездку для Ивана Петрова в Сочи", ("Ивана", "Петрова")),
    ("Меня зовут иван петров, хочу в Сочи", ("иван", "петров")),
    ("Я Иван, хочу в Казань", ("Иван",)),
    ("Летим с Анной Ивановой в Турцию", ("Анной", "Ивановой")),
    ("Позвоните +7 (999) 123-45-67, подберите Сочи", ("999", "123-45-67")),
    ("Контакт test\u200b@example.com, подберите Казань", ("test", "example.com")),
    ("Паспорт серия 1234 номер 567890, хочу в Сочи", ("1234", "567890")),
    ("Карта 4111 1111 1111 1111, хочу в Сочи", ("4111",)),
    ("Дата рождения 12.02.1980, хочу в Сочи", ("12.02.1980",)),
    ("СНИЛС 123-456-789 01, хочу в Сочи", ("123-456-789",)),
    ("Мой адрес: улица Примерная, 1, хочу в Сочи", ("Примерная",)),
    ("API key: synthetic-token, хочу в Сочи", ("synthetic-token",)),
    ("мой телефон девятьсот двенадцать триста сорок пять шестьдесят семь, хочу в Сочи", ("девятьсот двенадцать", "шестьдесят семь")),
    ("моя почта marina собака example точка ru, хочу в Сочи", ("marina", "example")),
    ("поездка для анны ивановой в Сочи", ("анны", "ивановой")),
    ("у меня диабет, хочу поездку в Сочи", ("диабет",)),
    ("мой номер клиента 12345678, хочу в Казань", ("12345678",)),
    ("живу возле станции Лесная в доме 12, хочу в Сочи", ("Лесная",)),
    ("Мой мобильный 9123456789, хочу в Сочи", ("9123456789",)),
    ("Серия паспорта 4510, номер 123456, хочу в Сочи", ("4510", "123456")),
    ("Код из смс 149280, хочу в Сочи", ("149280",)),
    ("Расчётный счёт 40702810900000000001, хочу в Сочи", ("40702810900000000001",)),
    ("Я родилась 7 марта 1984 года, хочу в Сочи", ("7 марта 1984",)),
    ("Хочу поехать с лёшей в Казань", ("лёшей",)),
    ("Мой вацап 9123456789, хочу в Казань", ("9123456789",)),
    ("логин ivan_1987, хочу в Сочи", ("ivan_1987",)),
    ("У мужа гипертония, мы хотим в Сочи", ("гипертония",)),
    ("контакт 9001112233, хочу в Сочи", ("9001112233",)),
    ("моя почта alice(собака)example.рф, еду в Сочи", ("alice", "example.рф")),
    ("мой телеграм @example_traveler, хочу в Казань", ("example_traveler",)),
    ("я 1986 года рождения, хочу в Сочи", ("1986",)),
    ("загранпаспорт AB 1234567, еду в Сочи", ("AB 1234567",)),
    ("адрес пр. Мира, д. 12, хочу в Сочи", ("Мира",)),
    ("номер брони AB-73-91, хочу в Казань", ("AB-73-91",)),
    ("Instagram @sample_travel, хочу в Казань", ("@sample_travel",)),
    ("мой номер связи 900 один один один 22 33, хочу в Сочи", ("900 один",)),
    ("я родился в июне 1986 года, еду в Сочи", ("1986",)),
    ("у меня диагноз целиакия, хочу в Казань", ("целиакия",)),
    ("мой номер заказа OX-1234, хочу в Сочи", ("OX-1234",)),
    ("я живу в доме Лесная 5, хочу в Казань", ("Лесная 5",)),
])
def test_recognized_secrets_are_masked_and_trip_continues(text, secrets):
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    reply = agent.handle(session, text)
    assert model.calls
    sent = str(model.calls).casefold()
    assert all(not re.search(r"(?<!\w)" + re.escape(secret.casefold()) + r"(?!\w)", sent)
               for secret in secrets)
    assert "данн" in reply.reply.lower()
    assert session.state.dest_id or session.state.country


@pytest.mark.parametrize("text", [
    "Из Москвы в Казань с 10 по 15 июня 2027 двое взрослых",
    "Хочу в Сочи, бюджет 150 тысяч рублей, отель с бассейном",
    "Из Владимира в Калининград на две недели",
    "Хочу посетить Владимир на майские праздники",
    "Собираемся в Иваново из Москвы на выходные",
    "Поездка в Великий Новгород и Санкт-Петербург",
    "Подберите отель в Нижнем Новгороде, нужен завтрак",
    "А можно будет отменить бронь?",
    "Нужен прямой перелёт из Самары в Сочи",
    "Два взрослых и три ребёнка, 7 ночей и 150000 рублей",
    "Первый вариант слишком дорогой, нужен дешевле",
    "Давайте подумаем и не будем пока оформлять",
    "Перенеси всю поездку на два дня позже",
    "Хочу в Сочи с собакой и двумя детьми",
    "Поеду с другом на море",
    "Какое имя гостиницы в Казани?",
])
def test_normal_travel_requests_are_not_changed(text):
    result, masked = mask_sensitive_data(text, TripsDomain.preserve_place)
    assert not masked
    assert result == text


def test_existing_state_is_filtered_before_each_model_call():
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    session.state.origin = "contact@example.com"
    agent.handle(session, "Хочу в Сочи")
    assert model.calls and "contact@example.com" not in str(model.calls)


def test_clean_system_instructions_remain_unchanged():
    domain = TripsDomain(today=lambda: TODAY)
    text = domain.extraction_messages(domain.state_model(), [], "Хочу в Сочи", TODAY)[0]["content"]
    cleaned, masked = mask_sensitive_data(text, domain.preserve_place)
    assert not masked and cleaned == text


def test_recognized_food_allergy_keeps_a_dietary_request_without_the_diagnosis():
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "У меня сильная аллергия на орехи, хочу в Сочи")
    assert not model.calls
    assert session.state.accessibility_needs == ["diet_nuts"]
    assert "аллергия" not in session.state.model_dump_json().lower()
    assert session.state.dest_id == "sochi"


def test_recognized_food_intolerance_keeps_the_dietary_requirement():
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "У меня непереносимость глютена, еду в Сочи")
    assert not model.calls
    assert session.state.accessibility_needs == ["diet_gluten"]
    assert "непереносимость" not in session.state.model_dump_json().lower()


def test_http_chat_continues_after_automatic_redaction():
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    with TestClient(build_app(agent)) as client:
        response = client.post("/api/chat", json={
            "text": "Меня зовут Иван Петров, телефон +7 999 123-45-67, хочу в Сочи",
        })
    assert response.status_code == 200
    payload = response.json()
    assert "личные данные" in payload["reply"].lower()
    assert payload["trip_summary"]["destination"] == "Сочи"
    assert model.calls
    sent = str(model.calls)
    assert "Иван Петров" not in sent and "999 123-45-67" not in sent


def test_model_retry_filters_the_previous_response_and_validation_error():
    secret = "+7 999 123-45-67"
    model = FakeLLM(f"неверный ответ {secret}", {})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    agent.handle(agent.new_session(), "Хочу в Сочи")
    assert len(model.calls) == 2
    assert secret not in str(model.calls)


def test_detector_failure_uses_local_rules_without_calling_model(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic detector failure")

    monkeypatch.setattr("core.guard.mask_names", fail)
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    reply = agent.handle(session, "Хочу в Сочи, мой телефон +7 999 123-45-67")
    assert not model.calls
    assert session.state.dest_id == "sochi"
    assert "локальн" in reply.reply.lower()


def test_outbound_detector_failure_never_calls_provider(monkeypatch):
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic outbound filter failure")

    # Agent's imported first-pass function remains available; only the final
    # filter at the network boundary fails.
    monkeypatch.setattr("core.guard.mask_sensitive_data", fail)
    session = agent.new_session()
    agent.handle(session, "Хочу в Сочи")
    assert not model.calls
    assert session.state.dest_id == "sochi" and session.last_nlu == "rules"


@pytest.mark.parametrize("text", [
    "связь t.me/fake_traveler, хочу в Казань",
    "звони мне девятсот двенадцать триста сорок пять, хочу в Сочи",
    "зовите меня дашей, хочу в Казань",
    "я 1991 г.р., хочу в Сочи",
    "езжу с инсулиновой помпой, хочу в Сочи",
    "alina это example точка ru, хочу в Казань",
    "моя квартира рядом с метро Тестовая, пятый дом, хочу в Сочи",
    "паспорт AB-1234567, хочу в Казань",
    "У моей тёти артрит, хотим в Казань",
    "связь instagram.com/fake_traveler, хочу в Сочи",
    "я родилась в тысяча девятьсот восемьдесят первом году, хочу в Сочи",
    "пишите ivan через mail точка ru, хочу в Сочи",
    "[t.me/fake_traveler], хочу в Казань",
    "[зовите меня дашей], хочу в Казань",
])
def test_unresolved_sensitive_patterns_are_processed_only_locally(text):
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    result = agent.handle(session, text)
    assert not model.calls
    assert session.state.dest_id in {"sochi", "kazan"}
    assert "локально" in result.reply.lower()


def test_unresolved_dynamic_context_is_not_forwarded_to_model():
    model = FakeLLM({})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    session.state.origin = "t.me/fake_traveler"
    agent.handle(session, "Хочу в Сочи")
    assert not model.calls and session.last_nlu == "rules"
