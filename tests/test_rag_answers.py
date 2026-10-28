"""Ответы через LLM на маскированных данных: обратимые метки, RAG по путеводителям, проверка ответа модели."""
from datetime import date

from core.agent import Agent
from core.answer import compose, verify
from core.guard import mask_sensitive_data
from core.privacy import Vault
from domains.trips import guides
from domains.trips.domain import TripsDomain
from tests.conftest import FakeLLM

TODAY = date(2026, 10, 28)


def agent(llm=None, nlg=True):
    return Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY, nlg=nlg)


# ---------- обратимое маскирование ----------

def test_vault_gives_stable_tokens_and_restores_only_names():
    vault = Vault()
    text, masked = mask_sensitive_data("Меня зовут Иван Петров, телефон +7 999 123-45-67. Иван поедет в Сочи",
                                       vault=vault)
    assert masked and "Иван" not in text and "999" not in text
    assert text.startswith("Меня зовут [имя_1]") and "[имя_1] поедет" in text  # тот же человек — та же метка
    shown = vault.restore("[имя_1], подобрал варианты. Не звоню на [телефон_1]")
    assert shown.startswith("Иван Петров") and "[телефон]" in shown and "999" not in shown


def test_without_vault_masking_is_unchanged():
    text, _ = mask_sensitive_data("Мой телефон +7 999 123-45-67, хочу в Сочи")
    assert "[телефон]" in text and "_1" not in text


def test_model_never_sees_personal_data_but_user_sees_own_name():
    llm = FakeLLM({"destination": "Будва"}, "[имя_1], отличный выбор — Будва! Когда хотите поехать?")
    a = agent(llm)
    session = a.new_session()
    reply = a.handle(session, "Меня зовут Иван, хочу в Будву").reply
    sent = " ".join(m["content"] for call in llm.calls for m in call)
    assert "Иван" not in sent and "[имя_1]" in sent
    assert "Иван, отличный выбор — Будва!" in reply and session.last_answer_by == "llm"
    assert all("Иван" not in m["content"] for m in session.history)  # в истории — только метки


# ---------- проверка ответа модели ----------

FACTS = "1. Оптимальный — 122 140 ₽\n2. Экономный — 98 500 ₽\nКакой вариант берём?"


def test_verify_accepts_faithful_answer():
    answer = "Нашёл два хороших варианта:\n1. Оптимальный — 122 140 ₽\n2. Экономный — 98 500 ₽\nКакой берём?"
    assert verify(answer, FACTS, "", set(), FACTS) == []


def test_verify_rejects_invented_numbers_lost_prices_links_and_promises():
    assert any("числа" in p for p in verify(FACTS.replace("98 500", "88 500"), FACTS, "", set(), FACTS))
    assert any("цены" in p for p in verify("1. Оптимальный — 122 140 ₽\nКакой берём?", FACTS, "", set(), FACTS))
    assert "ссылка" in verify(FACTS + " Подробнее на booking.com", FACTS, "", set(), FACTS)
    assert any("обещание" in p for p in verify(FACTS + " Я уже забронировал номер.", FACTS, "", set(), FACTS))
    assert any("метки" in p for p in verify(FACTS + " [имя_2]", FACTS, "", {"[имя_1]"}, FACTS))


def test_compose_retries_once_then_falls_back_to_template():
    llm = FakeLLM("Всё за 10 ₽!", "Опять 10 ₽")
    result = compose(llm, "покажи варианты", FACTS, FACTS, [], set())
    assert result.by == "template" and result.text == FACTS and len(llm.calls) == 2
    assert "Предыдущий вариант отклонён" in llm.calls[1][-1]["content"]


def test_compose_without_model_or_on_error_keeps_template():
    assert compose(None, "x", FACTS, FACTS, [], set()).by == "template"
    assert compose(FakeLLM(TimeoutError()), "x", FACTS, FACTS, [], set()).text == FACTS


# ---------- RAG по путеводителям ----------

def test_guides_search_is_filtered_by_destination_and_topic():
    assert guides.available()
    found = guides.search("что посмотреть", dest="budva", topic="sights", k=2)
    assert found and all(s.dest == "budva" for s in found) and found[0].tag == "see"
    assert "Wikivoyage «Будва»" in found[0].cite()


def test_place_question_without_model_answers_from_guide_and_keeps_trip():
    a = agent(nlg=False)
    session = a.new_session()
    a.handle(session, "Из Москвы в Стамбул с 10 по 15 июня 2027 двое взрослых")
    params = session.state.params()
    reply = a.handle(session, "где лучше поесть?")
    assert reply.reply.startswith("По путеводителю Wikivoyage («Стамбул»)")
    assert any("раздел «Еда»" in s["cite"] for s in reply.sources)
    assert session.state.params() == params  # вопрос о месте не меняет условия поездки


def test_llm_answer_on_guide_question_cites_source():
    answer = "Путеводитель советует искать кафе в центре и попробовать симит. Какой вариант берём?"
    llm = FakeLLM({}, {"question": "food"}, answer)
    a = agent(llm)
    session = a.new_session()
    a.nlg = False  # первая реплика — подбор по правилам, ответ шаблоном
    a.handle(session, "Из Москвы в Стамбул с 10 по 15 июня 2027 двое взрослых")
    a.nlg = True
    reply = a.handle(session, "где лучше поесть?")
    assert session.last_answer_by == "llm" and reply.reply.startswith("Путеводитель советует")
    assert "Источник: Wikivoyage «Стамбул»" in reply.reply and "CC BY-SA" in reply.reply
    prompt = llm.calls[-1][-1]["content"]
    assert "Источники (путеводитель)" in prompt and "Еда" in prompt
