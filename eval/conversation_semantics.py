"""Bounded synthetic probe of actual model routing; reads normal app settings.

Run: python -m eval.conversation_semantics --output result.json
No raw model responses, credentials or real user conversations are persisted.
"""
import argparse
import json
import time
from datetime import date
from pathlib import Path

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain
from domains.trips.state import TripState

CASES = [
    ('capabilities', 'Расскажите, какие задачи можно поручить этому помощнику?', ['Могу']),
    ('thanks', 'Благодарствую за подсказку', ['Пожалуйста']),
    ('explain', 'Объясни, для чего уточнять город старта', ['Город', 'Например']),
    ('pause', 'Давайте прервёмся и вернёмся к выбору вечером', ['продолжим']),
    ('summary', 'Собери в одном сообщении всё, что я уже указал', ['Казань']),
    ('repair', 'Не совсем то, о чём я спрашивал', ['поправим']),
    ('data_provenance', 'А стоимость здесь от поставщика или вы её рассчитываете сами?', ['демонстрационные']),
    ('preview', 'Как бы выглядел вариант с поездом?', ['текущую поездку пока не меняю', 'поезд']),
]


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rules', action='store_true')
    args = parser.parse_args()
    settings = get_settings()
    model = None if args.rules else build_llm(settings)
    if not args.rules and model is None:
        raise SystemExit('Live model is unavailable; use --rules to explicitly test offline routing')
    today = lambda: date(2026,10,29)
    agent = Agent(TripsDomain(today=today), model, today=today, nlg=True)
    rows = []
    for expected, text, fragments in CASES:
        session = agent.new_session()
        session.state = TripState(destination='Казань', dest_id='kazan', month=12, nights=7, pending_question='origin')
        before = session.state.model_dump(mode='json')
        started = time.perf_counter()
        result = agent.handle(session, text)
        state_unchanged = before == session.state.model_dump(mode='json')
        rows.append({'expected_intent':expected, 'input':text, 'reply':result.reply,
                     'nlu':session.last_nlu, 'answer_by':session.last_answer_by,
                     'state_unchanged':state_unchanged,
                     'pass':state_unchanged and all(fragment in result.reply for fragment in fragments),
                     'seconds':round(time.perf_counter()-started,2)})
        print(json.dumps({k:rows[-1][k] for k in ('expected_intent','nlu','pass','seconds')},ensure_ascii=False),flush=True)
        if model and model.breaker.state != 'ok':
            break  # Do not keep querying after a provider failure or rate limit.
    output = {'kind':'synthetic_development_probe', 'mode':'rules' if args.rules else 'live',
              'model':settings.llm_model if model else None, 'planned':len(CASES),
              'completed':len(rows),'passed':sum(row['pass'] for row in rows),'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    run()
