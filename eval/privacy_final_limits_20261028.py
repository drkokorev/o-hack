"""Post-tuning adversarial examples; deliberately not a representative benchmark."""
import json
import unicodedata
from core.agent import Agent
from domains.trips.domain import TripsDomain

CASES = [
    ("ordinary_phone", "Телефон +7 912 555-33-22, хочу в Сочи", "+7 912 555-33-22"),
    ("ordinary_name", "Меня зовут Ольга, хочу в Казань", "Ольга"),
    ("medication_context", "еду с таблетками метформина в Сочи", "метформина"),
    ("alternative_address", "моя квартира возле метро Лесная, корпус пять, хочу в Казань", "метро Лесная"),
    ("rare_id", "мой полис ОМС 1234567890123456, еду в Сочи", "1234567890123456"),
    ("age_in_context", "мне 42 года, хочу в Казань", "мне 42 года"),
    ("surname_unusual", "выбирает поездку котовский-иванов александр, хочу в Сочи", "котовский-иванов"),
    ("voiced_email", "пиши marina в example точка ru, хочу в Казань", "marina в example"),
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
