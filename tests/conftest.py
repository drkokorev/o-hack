import json
from datetime import date

import pytest

TODAY = date(2026, 10, 5)  # понедельник


class FakeLLM:
    """Возвращает заранее заданные ответы по очереди; dict сериализуется в JSON, Exception — бросается."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages, *, json_mode=False, schema=None):
        self.calls.append(messages)
        item = self.responses.pop(0) if self.responses else {}
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)


@pytest.fixture
def today():
    return TODAY


@pytest.fixture(autouse=True)
def no_local_env(monkeypatch):
    """Тесты не зависят от личного .env разработчика: только значения по умолчанию и то, что задал сам тест."""
    import os

    from core import config

    for name in list(os.environ):
        if name.startswith(("LLM_", "GIGACHAT_")):
            monkeypatch.delenv(name)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
