"""Оценка агента на сценариях «от фразы до результата» — метрики из задания трека.

    .venv/bin/python -m eval.run                  # правила + LLM (если есть ключ) + LLM со сбоями
    .venv/bin/python -m eval.run --modes rules

Режимы:
- rules  — без LLM (так запустит жюри, если у него нет ключа);
- llm    — с моделью из .env;
- chaos  — с «плохой» моделью: таймауты, мусор, ответ в форме схемы, повтор действий, «да» на всё.
Отчёт: eval/report.md и eval/report.json с пометкой коммита.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain
from domains.trips.offers import hotels_for

HERE = Path(__file__).parent


class ChaosLLM:
    """Модель, которая ошибается так, как ошибаются настоящие: сбои сети, мусор, повторы, ложное «да»."""

    def __init__(self, seed: int = 7):
        self.rng = random.Random(seed)

    def complete(self, messages, *, json_mode=False, schema=None) -> str:
        roll = self.rng.random()
        if roll < 0.15:
            raise TimeoutError("chaos")
        if roll < 0.25:
            return "Конечно! Вот что я понял: пользователь хочет отдохнуть."
        if roll < 0.35:
            return json.dumps({"properties": {"confirm": True}})
        if roll < 0.55:
            return json.dumps({"confirm": True, "shift_days": 2, "pets": True, "cheaper": True})
        return "{}"


def check(expect: dict, state, step_payloads: list[dict], history: list[str]) -> list[str]:
    """Возвращает список нарушенных ожиданий."""
    bad = []
    for key, want in expect.items():
        if key == "all_hotels_pets":
            items = (step_payloads[-1] or {}).get("items", [])
            if not items or any("можно с животными" not in i["hotel"]["amenities"] for i in items):
                bad.append(key)
        elif key == "diff_mentions":
            if not any(want in d for d in (step_payloads[-1] or {}).get("diff", [])):
                bad.append(key)
        elif key == "suggested_any":
            if not set(want) & set(state.suggested):
                bad.append(key)
        elif key == "suggested_domestic":
            items = (step_payloads[-1] or {}).get("items", [])
            if not items or any(i["country"] != "Россия" for i in items):
                bad.append(key)
        elif key == "budget_set":
            if not state.budget_total:
                bad.append(key)
        elif key == "hotel_pinned":
            if not state.hotel_id:
                bad.append(key)
        elif key == "within_budget":
            if not state.order or state.order["total"] > (state.budget_total or 0):
                bad.append(key)
        elif key == "requests":
            if len(state.requests) != want:
                bad.append(key)
        else:
            got = getattr(state, key, None)
            if isinstance(got, date):
                got = got.isoformat()
            if got != want:
                bad.append(f"{key}: ждали {want!r}, получили {got!r}")
    return bad


def run_scenario(agent: Agent, sc: dict) -> dict:
    s = agent.new_session()
    payloads, ms, questions, first_reco = [], [], 0, None
    events: set[str] = set()
    had_order = False
    for i, text in enumerate(sc["turns"]):
        started = time.perf_counter()
        step = agent.handle(s, text)
        ms.append((time.perf_counter() - started) * 1000)
        payload = step.payload or {}
        payloads.append(payload)
        kind = payload.get("kind")
        if kind in ("question", "greeting"):
            questions += 1
        if first_reco is None and kind in ("destinations", "packages"):
            first_reco = i + 1
        if s.state.stage == "booked":
            events.add("booked")
        if s.state.order:
            had_order = True
        elif had_order:
            events.add("cancelled")
    bad = check(sc.get("expect", {}), s.state, payloads, sc["turns"])
    bad += [f"запрещено: {f}" for f in sc.get("forbid", []) if f in events]
    return {"id": sc["id"], "persona": sc.get("persona", ""), "ok": not bad, "problems": bad,
            "turns": len(sc["turns"]), "questions": questions, "first_reco_turn": first_reco,
            "wrong_irreversible": sum(1 for f in sc.get("forbid", []) if f in events),
            "ms": [round(x) for x in ms], "nlu": s.last_nlu}


def summarize(results: list[dict]) -> dict:
    ms = sorted(x for r in results for x in r["ms"])
    reco = [r["first_reco_turn"] for r in results if r["first_reco_turn"]]
    return {
        "scenarios": len(results), "ok": sum(r["ok"] for r in results),
        "success_rate": round(sum(r["ok"] for r in results) / len(results), 3),
        "wrong_irreversible": sum(r["wrong_irreversible"] for r in results),
        "questions_per_scenario": round(sum(r["questions"] for r in results) / len(results), 2),
        "first_reco_turn_median": median(reco) if reco else None,
        "latency_ms_p50": round(median(ms)) if ms else None,
        "latency_ms_p95": ms[max(0, int(len(ms) * 0.95) - 1)] if ms else None,
    }


def commit() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.call(["git", "diff", "--quiet", "HEAD", "--", "core", "domains", "apps"]) != 0
        return sha + ("+изменения" if dirty else "")
    except Exception:
        return "unknown"


def render(report: dict) -> str:
    out = ["# Оценка агента поездки", "",
           f"Коммит `{report['commit']}`, {report['date']}. {report['scenarios']} сценариев из `eval/scenarios.json`, "
           f"«сегодня» в сценариях — {report['today']}.", "",
           "| Режим | Модель | Доведено до цели | Ложных необратимых действий | Уточняющих вопросов на сценарий | "
           "Реплика с первой рекомендацией (медиана) | Задержка p50 / p95, мс |",
           "| :--- | :--- | ---: | ---: | ---: | ---: | ---: |"]
    for mode, data in report["modes"].items():
        s = data["summary"]
        out.append(f"| {mode} | {data['model'] or '—'} | {s['ok']}/{s['scenarios']} | {s['wrong_irreversible']} | "
                   f"{s['questions_per_scenario']} | {s['first_reco_turn_median']} | {s['latency_ms_p50']} / {s['latency_ms_p95']} |")
    for mode, data in report["modes"].items():
        failed = [r for r in data["results"] if not r["ok"]]
        if failed:
            out += ["", f"## Не доведено: {mode}", ""]
            out += [f"- `{r['id']}` ({r['persona']}): " + "; ".join(r["problems"]) for r in failed]
    out += ["", "**chaos** — модель, которая в 15% ответов падает по таймауту, в 10% отвечает не JSON, в 10% "
            "присылает «схему» с подтверждением, в 20% повторяет действия и выдумывает поля («да», «на два дня "
            "позже», «с собакой», «дешевле»). Цель — 0 ложных покупок и отмен и тот же результат, что без модели.", ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="rules,llm,chaos")
    parser.add_argument("--out", type=Path, default=HERE / "report")
    args = parser.parse_args()
    data = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
    today = date.fromisoformat(data["today"])
    settings = get_settings()
    report: dict[str, Any] = {"commit": commit(), "date": time.strftime("%Y-%m-%d %H:%M"), "today": data["today"],
                              "scenarios": len(data["scenarios"]), "modes": {}}
    for mode in args.modes.split(","):
        if mode == "rules":
            llm, model = None, None
        elif mode == "chaos":
            llm, model = ChaosLLM(), "ChaosLLM"
        else:
            llm, model = build_llm(settings), settings.llm_model
            if llm is None:
                print("Режим llm пропущен: ключ LLM не задан")
                continue
        agent = Agent(TripsDomain(today=lambda: today), llm, today=lambda: today)
        results = [run_scenario(agent, sc) for sc in data["scenarios"]]
        report["modes"][mode] = {"model": model, "summary": summarize(results), "results": results}
        print(mode, json.dumps(report["modes"][mode]["summary"], ensure_ascii=False))
    args.out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    args.out.with_suffix(".md").write_text(render(report), encoding="utf-8")
    print("Отчёт:", args.out.with_suffix(".md"))
    hotels_for.cache_clear()


if __name__ == "__main__":
    main()
