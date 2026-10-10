import json
from datetime import date

import pytest

TODAY = date(2026, 10, 5)  # понедельник


class FakeLLM:
    """Возвращает заранее заданные ответы по очереди; dict сериализуется в JSON, Exception — бросается."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages, *, json_mode=False):
        self.calls.append(messages)
        item = self.responses.pop(0) if self.responses else {}
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)


@pytest.fixture
def today():
    return TODAY
