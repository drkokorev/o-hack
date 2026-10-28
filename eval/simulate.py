"""«LLM играет путешественника»: персоны разговаривают с агентом своими словами, цель проверяется по итогу.

    .venv/bin/python -m eval.simulate                # агент с LLM из .env, если ключа нет — на правилах
    .venv/bin/python -m eval.simulate --agent rules  # агент без LLM, путешественника всё равно играет LLM

Нужен ключ LLM (путешественника играет модель из .env или USER_LLM_* — можно взять другую, дешёвую).
Уроки прошлого проекта: точная первая фраза у каждой персоны (иначе модель уходит от роли),
остановка при сбоях провайдера, неполный прогон пишется в отдельный файл и не выдаётся за результат.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain

HERE = Path(__file__).parent
MAX_TURNS = 14  # с выбором и подтверждением демо-оплаты

PERSONAS = [
    {"id": "family_sea", "first": "Привет! Хотим с мужем и сыном 6 лет куда-нибудь на море в ноябре, бюджет тысяч 250, "
     "долго лететь не хотим", "goal": "купить поездку к тёплому морю, перелёт не дольше 5–6 часов, в пределах 250 тысяч",
     "check": {"booked": True, "children": 1, "within_budget": True}},
    {"id": "hesitant_couple", "first": "Думаем съездить вдвоём куда-нибудь в Европейскую часть России на выходные, "
     "погулять по городу", "goal": "выбрать город, посмотреть варианты, засомневаться в корзине и в итоге оформить",
     "check": {"booked": True}},
    {"id": "dog_owner", "first": "Хочу в Калининград в начале декабря на 4 ночи с собакой, она 15 кг",
     "goal": "чтобы отель принимал собак; спросить про перевозку собаки; оформить",
     "check": {"booked": True, "pets": True}},
    {"id": "date_changer", "first": "Сочи с 10 по 15 декабря вдвоём", "goal": "получить варианты, потом попросить "
     "сдвинуть на два дня позже и проверить, что отель остался тем же; оформить",
     "check": {"booked": True, "date_from": "2026-12-12"}},
    {"id": "budget_hunter", "first": "Самый дешёвый вариант куда-нибудь погреться в декабре на неделю, я один",
     "goal": "найти самый бюджетный вариант, дважды попросить дешевле, оформить", "check": {"booked": True}},
    {"id": "skier", "first": "Хочу покататься на сноуборде в феврале, нас четверо друзей", "goal": "выбрать горнолыжное "
     "направление и оформить", "check": {"booked": True, "adults": 4}},
    {"id": "post_sale", "first": "Казань, 13–15 ноября, двое взрослых", "goal": "оформить, затем попросить ранний "
     "заезд и спросить про условия отмены, но НЕ отменять", "check": {"booked": True, "requests": 1}},
    {"id": "canceller", "first": "Калининград 6–9 ноября, я одна", "goal": "оформить, затем отменить бронь "
     "(подтвердить отмену)", "check": {"order": None}},
]

USER_PROMPT = """Ты играешь путешественника в чате с AI-агентом бронирования поездок. Твоя цель: {goal}.
Пиши коротко и естественно, как в мессенджере, по-русски, одной репликой. Не выдумывай новых целей.
Отвечай на вопросы агента, выбирай варианты из его списков (номером или названием).
Когда цель достигнута, ответь ровно словом СТОП."""


def user_llm():
    s = get_settings()
    if os.getenv("USER_LLM_API_KEY"):
        s = replace(s, llm_provider="openai", llm_api_key=os.environ["USER_LLM_API_KEY"],
                    llm_base_url=os.getenv("USER_LLM_BASE_URL", s.llm_base_url),
                    llm_model=os.getenv("USER_LLM_MODEL", s.llm_model))
    return build_llm(s)


def check(want: dict, state) -> list[str]:
    bad = []
    for key, value in want.items():
        if key == "booked":
            ok = (state.stage == "booked") == value
        elif key == "within_budget":
            ok = bool(state.order) and state.order["total"] <= (state.budget_total or 10**9)
        elif key == "requests":
            ok = len(state.requests) >= value
        else:
            got = getattr(state, key, None)
            ok = (got.isoformat() if isinstance(got, date) else got) == value
        if not ok:
            bad.append(key)
    return bad


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["llm", "rules"], default="llm")
    parser.add_argument("--out", type=Path, default=HERE / "report_simulate")
    args = parser.parse_args()
    user = user_llm()
    if user is None:
        raise SystemExit("Нужен ключ LLM: путешественника играет модель (LLM_API_KEY или USER_LLM_API_KEY в .env)")
    today = date(2026, 10, 24)
    agent_llm = build_llm(get_settings()) if args.agent == "llm" else None
    agent = Agent(TripsDomain(today=lambda: today), agent_llm, today=lambda: today)
    results, complete = [], True
    for p in PERSONAS:
        s = agent.new_session()
        transcript, replies, text, failed, last = [], [], p["first"], False, False
        for _ in range(MAX_TURNS):
            started = time.perf_counter()
            step = agent.handle(s, text)
            replies.append(step.reply)  # путешественник видит ответ целиком — вопрос об оплате стоит в конце
            transcript.append({"user": text, "agent": step.reply[:600], "stage": s.state.stage, "nlu": s.last_nlu,
                               "checked": s.last_notes, "ms": round((time.perf_counter() - started) * 1000)})
            if last:
                break
            msgs = [{"role": "system", "content": USER_PROMPT.format(goal=p["goal"])}]
            for t, reply in zip(transcript, replies):
                msgs += [{"role": "assistant", "content": t["user"]}, {"role": "user", "content": reply}]
            try:
                text = user.complete(msgs).strip()
            except Exception as err:  # провайдер упал — честно останавливаемся
                print("Путешественник-LLM недоступна:", type(err).__name__)
                failed, complete = True, False
                break
            if text.upper().startswith("СТОП"):
                break
            # «Оформляйте. СТОП» — реплика агенту и конец разговора; само «СТОП» агенту не отправляем
            text, last = re.subn(r"[\s.!]*\bСТОП\W*$", "", text)
            last = bool(last)
        problems = check(p["check"], s.state) if not failed else ["прогон прерван"]
        results.append({"id": p["id"], "ok": not problems, "problems": problems, "turns": len(transcript),
                        "transcript": transcript})
        print(p["id"], "ok" if not problems else problems, len(transcript), "реплик")
        if failed:
            break
    out = args.out if complete else args.out.with_name(args.out.name + "_incomplete")
    ok = sum(r["ok"] for r in results)
    out.with_suffix(".json").write_text(json.dumps({"agent": args.agent, "ok": ok, "total": len(results),
                                                    "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Итог: {ok}/{len(results)} — {out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
