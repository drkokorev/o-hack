"""Оценка понимания запросов: точность параметров, доля запросов, решённых с первого сообщения, задержка.

    .venv/bin/python -m eval.run                 # все доступные режимы
    .venv/bin/python -m eval.run --modes rules   # только правила, без сети

Режимы: rules — только правила; llm — только LLM; hybrid — LLM, дополненная правилами (как в демо).
Отчёт пишется в eval/report.md и eval/report.json с пометкой коммита.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from core.agent import Agent
from core.config import get_settings
from core.llm import OpenAICompatLLM
from domains.hotels.domain import HotelsDomain
from domains.hotels.search import SearchResult
from domains.hotels.state import PARAM_FIELDS

HERE = Path(__file__).parent


class LLMOnly:
    """Домен без правил: чтобы честно измерить вклад LLM отдельно."""

    def __init__(self, domain: HotelsDomain):
        self._domain = domain

    def __getattr__(self, name: str) -> Any:
        if name == "rule_extract":
            raise AttributeError(name)
        return getattr(self._domain, name)


def _value(v: Any) -> Any:
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, list):
        return sorted(v)
    return v


def run_case(agent: Agent, case: dict) -> dict:
    session = agent.new_session()
    latencies, first_ok = [], None
    for i, text in enumerate(case["turns"]):
        started = time.perf_counter()
        step = agent.handle(session, text)
        latencies.append((time.perf_counter() - started) * 1000)
        if i == 0:
            first_ok = isinstance(step.payload, SearchResult) and bool(step.payload.matches)
    got = {f: _value(getattr(session.state, f)) for f in PARAM_FIELDS if getattr(session.state, f) not in (None, [])}
    expect = {k: _value(v) for k, v in case["expect"].items()}
    optional = set(case.get("optional", []))
    correct = [f for f in expect if got.get(f) == expect[f]]
    wrong = {f: {"expected": expect[f], "got": got.get(f)} for f in expect if got.get(f) != expect[f]}
    spurious = {f: got[f] for f in got if f not in expect and f not in optional}
    return {
        "id": case["id"], "turns": case["turns"], "ok": not wrong and not spurious,
        "correct": len(correct), "expected": len(expect), "wrong": wrong, "spurious": spurious,
        "first_message_results": first_ok, "single_turn": len(case["turns"]) == 1,
        "nlu": session.last_nlu, "ms": [round(x) for x in latencies],
    }


def summarize(results: list[dict]) -> dict:
    expected = sum(r["expected"] for r in results)
    correct = sum(r["correct"] for r in results)
    extracted = correct + sum(len(r["wrong"]) - sum(1 for w in r["wrong"].values() if w["got"] is None)
                              for r in results) + sum(len(r["spurious"]) for r in results)
    single = [r for r in results if r["single_turn"] and r["expected"]]
    ms = sorted(x for r in results for x in r["ms"])
    return {
        "cases": len(results),
        "cases_ok": sum(r["ok"] for r in results),
        "field_recall": round(correct / expected, 3) if expected else None,
        "field_precision": round(correct / extracted, 3) if extracted else None,
        "first_message_results": round(sum(bool(r["first_message_results"]) for r in single) / len(single), 3)
        if single else None,
        "latency_ms_p50": round(median(ms)) if ms else None,
        "latency_ms_p95": ms[int(len(ms) * 0.95) - 1] if ms else None,
    }


def commit() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.call(["git", "diff", "--quiet", "HEAD"]) != 0
        return sha + ("+изменения" if dirty else "")
    except Exception:
        return "unknown"


def render(report: dict) -> str:
    out = [f"# Оценка понимания запросов", "",
           f"Коммит `{report['commit']}`, {report['date']}. Набор: {report['cases']} диалогов "
           f"(`eval/cases.json`), сегодня в наборе — {report['today']}.", ""]
    out += ["| Режим | Модель | Диалогов без ошибок | Полнота полей | Точность полей | "
            "Выдача с первого сообщения | Задержка p50 / p95, мс |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: |"]
    for mode, data in report["modes"].items():
        s = data["summary"]
        out.append(f"| {mode} | {data['model'] or '—'} | {s['cases_ok']}/{s['cases']} | {s['field_recall']:.0%} | "
                   f"{s['field_precision']:.0%} | {s['first_message_results']:.0%} | "
                   f"{s['latency_ms_p50']} / {s['latency_ms_p95']} |")
    for mode, data in report["modes"].items():
        failed = [r for r in data["results"] if not r["ok"]]
        if not failed:
            continue
        out += ["", f"## Ошибки: {mode}", ""]
        for r in failed:
            details = [f"{f}: ждали {w['expected']}, получили {w['got']}" for f, w in r["wrong"].items()]
            details += [f"лишнее {f}={v}" for f, v in r["spurious"].items()]
            out.append(f"- `{r['id']}` «{' / '.join(r['turns'])}» — " + "; ".join(details))
    out += ["", "Полнота — доля ожидаемых параметров, извлечённых верно. Точность — доля верных среди всех "
            "извлечённых. Выдача с первого сообщения — доля однострочных запросов, на которые агент сразу "
            "показал отели (без уточняющих вопросов).", ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="rules,llm,hybrid")
    parser.add_argument("--cases", type=Path, default=HERE / "cases.json")
    parser.add_argument("--out", type=Path, default=HERE / "report")
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    today = date.fromisoformat(data["today"])
    settings = get_settings()
    llm = OpenAICompatLLM(settings) if settings.llm_enabled else None
    domain = HotelsDomain()

    report: dict[str, Any] = {"commit": commit(), "date": time.strftime("%Y-%m-%d %H:%M"),
                              "today": data["today"], "cases": len(data["cases"]), "modes": {}}
    for mode in args.modes.split(","):
        if mode != "rules" and llm is None:
            print(f"Режим {mode} пропущен: LLM_API_KEY не задан")
            continue
        agent = Agent(LLMOnly(domain) if mode == "llm" else domain,  # type: ignore[arg-type]
                      None if mode == "rules" else llm, today=lambda: today)
        results = [run_case(agent, c) for c in data["cases"]]
        report["modes"][mode] = {"model": None if mode == "rules" else settings.llm_model,
                                 "summary": summarize(results), "results": results}
        print(mode, json.dumps(report["modes"][mode]["summary"], ensure_ascii=False))

    args.out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    args.out.with_suffix(".md").write_text(render(report), encoding="utf-8")
    print(f"Отчёт: {args.out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
