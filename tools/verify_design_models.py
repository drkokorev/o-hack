"""Bounded live-model smoke check. Synthetic inputs, no checkout or payment.

Usage: python -m tools.verify_design_models --base http://127.0.0.1:18191 --output result.json
Only sanitized result metadata is saved, never a session ID or provider config.
"""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:18191')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    steps = []
    session_id = None

    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        with urlopen(Request(args.base+path, data=data, headers={'Content-Type':'application/json'}), timeout=60) as response:
            return json.load(response)

    try:
        voice = call('/api/voice')
        started = time.monotonic()
        first = call('/api/chat', {'text':'Хочу на море из Москвы на 7 ночей с 15 июня 2027, двое взрослых, бюджет 180 тысяч рублей на всю поездку, без визы.'})
        session_id = first['session_id']
        assert first['payload']['kind'] == 'destinations', first['payload']['kind']
        assert first['nlu'] in {'llm','llm+rules'}, first['nlu']
        steps.append({'action':'natural-language trip request','result':'PASS','nlu':first['nlu'],'seconds':round(time.monotonic()-started,2)})
        place = next(item for item in call('/api/info')['places'] if item['name']=='Анталья')
        selected = call('/api/chat',{'session_id':session_id,'text':'Хочу в Анталью','destination_id':place['id']})
        assert selected['payload']['kind']=='packages'
        assert selected['map_selection']['accepted'] is True
        assert selected['trip_summary']['destination']=='Анталья'
        steps.append({'action':'structured Antalya selection','result':'PASS','nlu':selected['nlu'],'variants':len(selected['payload']['items'])})
        basket = call('/api/chat',{'session_id':session_id,'text':'беру 1 вариант'})
        assert basket['payload']['kind']=='cart'
        changed = call('/api/trip/transfer',{'session_id':session_id,'revision':basket['revision'],'kind':'shuttle'})
        before, after = basket['payload']['package'], changed['payload']['package']
        assert before['hotel']==after['hotel'] and before['out']==after['out'] and before['back']==after['back']
        assert after['transfer']['in']['kind']=='shuttle'
        steps.append({'action':'group transfer in model-enabled app','result':'PASS','before_rub':before['total_rub'],'after_rub':after['total_rub']})
        restored = call('/api/session',{'session_id':session_id})
        assert restored['revision']==changed['revision'] and restored['payload']==changed['payload']
        steps.append({'action':'resume without state advance','result':'PASS'})
        result={'result':'PASS','steps':steps,'voice_backend':voice.get('backend'),'voice_status':voice.get('status'),'voice_audio_tested':False,'checkout_performed':False}
    except Exception as error:
        result={'result':'FAIL','steps':steps,'error_type':type(error).__name__,'message':str(error)[:500]}
        raise
    finally:
        if session_id:
            try:
                call('/api/reset',{'session_id':session_id})
            except Exception:
                pass
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
