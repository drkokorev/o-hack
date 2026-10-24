"""Консольный чат для ручной проверки: python -m apps.cli"""

import argparse
import logging
import sys

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains import build_domain


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", choices=["trips"], nargs="?", default="trips")
    parser.add_argument("--debug", action="store_true", help="показывать состояние после каждой реплики")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.debug else logging.WARNING)

    settings = get_settings()
    if not settings.llm_enabled:
        print("⚠️  LLM_API_KEY не задан в .env — агент не сможет разобрать запрос", file=sys.stderr)
    llm = build_llm(settings)
    agent = Agent(build_domain(args.domain), llm, nlg=settings.llm_nlg)
    session = agent.new_session()
    print(f"Модель: {settings.llm_model if llm else 'нет (правила)'}. Команды: /state, /reset, /quit")

    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text == "/quit":
            break
        if text == "/reset":
            session = agent.new_session()
            print("Диалог сброшен.")
            continue
        if text == "/state":
            print(session.state.model_dump_json(indent=2, exclude_none=True))
            continue
        print(agent.handle(session, text).reply)
        if args.debug:
            print(f"[{session.last_nlu}]", session.state.model_dump_json(exclude_none=True, exclude={"act", "last_plan", "suggested", "hotel_ids_shown"}))


if __name__ == "__main__":
    main()
