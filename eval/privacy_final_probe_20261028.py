"""Synthetic boundary cases used during tuning; deliberately not a representative benchmark."""
import json
import unicodedata
from core.agent import Agent
from domains.trips.domain import TripsDomain

CASES = [
    ("name", "Меня зовут Ольга, ищу поездку в Казань", "Ольга"),
    ("telephone", "мой телефон +7 912 555-33-22, хочу в Сочи", "+7 912 555-33-22"),
    ("email", "почта demo.person@example.org, хочу в Казань", "demo.person@example.org"),
    ("passport", "паспорт CD 3456789, хочу в Сочи", "CD 3456789"),
    ("telegram_url", "связь t.me/fake_traveler, хочу в Казань", "t.me/fake_traveler"),
    ("unusual_phone", "звони мне девятсот двенадцать триста сорок пять, хочу в Сочи", "девятсот двенадцать"),
    ("unusual_name", "зовите меня дашей, хочу в Казань", "дашей"),
    ("birth_abbreviation", "я 1991 г.р., хочу в Сочи", "1991"),
    ("medical", "езжу с инсулиновой помпой, хочу в Сочи", "инсулиновой"),
    ("email_words", "alina это example точка ru, хочу в Казань", "alina это example"),
    ("place_address", "моя квартира рядом с метро Тестовая, пятый дом, хочу в Сочи", "Тестовая"),
    ("international_id", "паспорт AB-1234567, хочу в Казань", "AB-1234567"),
]


def normalize(text):
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold()
                   if unicodedata.category(ch) != "Cf")


def main():
    results = []
    for ident, text, secret in CASES:
        class FakeModel:
            def __init__(self):
                self.calls = []

            def complete(self, messages, **_kwargs):
                self.calls.append(messages)
                return "{}"

        model = FakeModel()
        agent = Agent(TripsDomain(), model)
        agent.handle(agent.new_session(), text)
        sent = json.dumps(model.calls, ensure_ascii=False)
        results.append({"id": ident, "not_sent": normalize(secret) not in normalize(sent),
                        "model_called": bool(model.calls)})
    print(json.dumps({"not_sent": sum(item["not_sent"] for item in results), "total": len(results),
                      "locally_processed": sum(not item["model_called"] for item in results),
                      "misses": [item for item in results if not item["not_sent"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
