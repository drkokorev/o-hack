from core.answer import compose, verify
from tests.conftest import FakeLLM


def test_unrelated_link_is_rejected_even_when_context_has_a_link():
    facts = 'Источник: https://example.org/guide'
    assert 'ссылка' in verify('Смотрите https://other.org/pay', facts, '', set(), facts)


def test_negative_booking_statement_does_not_authorize_a_positive_claim():
    facts = 'Номер не забронирован. Оплата не проведена.'
    assert any('обещание' in issue for issue in verify('Номер забронирован.', facts, '', set(), facts))
    assert not verify(facts, facts, '', set(), facts)


def test_rewording_cannot_replace_the_required_question():
    draft = 'Когда хотите поехать?'
    model = FakeLLM('Какой отель выбираете?', 'Сколько взрослых едет?')
    result = compose(model, 'Казань', draft, draft, [], set(), required_question=draft)
    assert result.by == 'template' and result.text == draft
    assert len(model.calls) == 2


def test_grounded_rewording_can_keep_the_required_question():
    draft = 'Когда хотите поехать?'
    result = compose(FakeLLM('Когда хотите поехать? Можно назвать месяц.'), 'Казань', draft, draft, [], set(),
                     required_question=draft)
    assert result.by == 'llm'
