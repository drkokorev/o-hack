"""Fresh synthetic travel probes, distinct from the conversational development set."""
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
    {'id':'family', 'text':'Нас четверо: двое взрослых, дети 4 и 9 лет. Хотим в Казань из Москвы с 10 по 15 декабря',
     'expect':{'destination':'Казань','origin':'Москва','adults':2,'children':2}},
    {'id':'budget_and_origin','text':'В Казань из Перми с 12 по 17 декабря, 2 взрослых, 60 тысяч на всех',
     'expect':{'destination':'Казань','origin':'Пермь','adults':2,'budget_total':60000}},
    {'id':'exclusions','text':'Не Турция и не Египет, хочу на море',
     'expect':{'excluded_countries':['Египет','Турция']}},
    {'id':'edit_month','state':{'destination':'Казань','dest_id':'kazan','month':11},
     'text':'Вместо ноября декабрь, остальное оставь', 'expect':{'destination':'Казань','month':12}},
    {'id':'hotel_only','text':'Нужен только отель в Сочи с 5 по 12 декабря, двое взрослых, всего до 70000 рублей',
     'expect':{'destination':'Сочи','search_scope':'hotel_only','adults':2,'budget_total':70000}},
    {'id':'no_fake_confirmation','state':{'destination':'Казань','dest_id':'kazan','stage':'payment'},
     'text':'Выглядит хорошо, но ничего пока не оформляй', 'expect':{'order':None, 'stage':'payment'},
     'reply_any':['продолж']},
    {'id':'uncertain_party','text':'Возможно поедем втроём в Казань',
     'expect':{'adults':None},'contains':{'tentative_fields':'party_size'}},
    {'id':'typo_duration','text':'Из Москвы в стамбл на 11 дн в декабре, двое взрослых',
     'expect':{'destination':'Стамбул','origin':'Москва','month':12,'adults':2}},
    {'id':'unpriced_inspiration','text':'Предложи горы и спокойные прогулки, пока без дат',
     'expect':{'date_from':None,'date_to':None,'month':None,'relaxed_walks':True}},
    {'id':'unsupported_currency','text':'Хочу в Казань, бюджет 100 долларов',
     'expect':{'budget_total':None},'reply_any':['рубл','валют','доллар']},
]


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rules',action='store_true')
    parser.add_argument('--only', choices=[case['id'] for case in CASES])
    args=parser.parse_args()
    settings=get_settings()
    llm=None if args.rules else build_llm(settings)
    if not args.rules and llm is None:
        raise SystemExit('No configured model')
    today=lambda:date(2026,10,29)
    agent=Agent(TripsDomain(today=today),llm,today=today,nlg=True)
    rows=[]
    cases = [case for case in CASES if not args.only or case['id'] == args.only]
    for case in cases:
        session=agent.new_session()
        session.state=TripState(**case.get('state',{}))
        started=time.perf_counter()
        result=agent.handle(session,case['text'])
        state=session.state.model_dump(mode='json')
        problems=[]
        for key,wanted in case['expect'].items():
            value=state[key]
            if (sorted(value) if isinstance(value,list) else value)!=(sorted(wanted) if isinstance(wanted,list) else wanted):
                problems.append({'field':key,'expected':wanted,'actual':value})
        for key,wanted in case.get('contains',{}).items():
            if wanted not in (state[key] or []):
                problems.append({'field':key,'missing':wanted,'actual':state[key]})
        if case.get('reply_any') and not any(word in result.reply.lower() for word in case['reply_any']):
            problems.append({'reply_missing_any':case['reply_any']})
        rows.append({'id':case['id'],'input':case['text'],'pass':not problems,'problems':problems,
                     'nlu':session.last_nlu,'reply':result.reply,'seconds':round(time.perf_counter()-started,2)})
        print(json.dumps({k:rows[-1][k] for k in ('id','pass','nlu','problems')},ensure_ascii=False),flush=True)
        if llm and llm.breaker.state!='ok':
            break
    output={'kind':'synthetic_exploratory_probe','mode':'rules' if args.rules else 'live',
            'model':settings.llm_model if llm else None,'planned':len(cases),'completed':len(rows),
            'passed':sum(row['pass'] for row in rows),'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    run()
