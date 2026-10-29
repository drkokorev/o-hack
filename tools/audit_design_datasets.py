"""Compare source datasets without loading application services or private config.

Usage: python -m tools.audit_design_datasets --output path.json
Git refs are recorded as exact commits so the result remains interpretable later.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import subprocess

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--refs',nargs='+',default=['HEAD','origin/main','origin/daniil','origin/artemiy'])
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    def git(*values):return subprocess.check_output(['git',*values],cwd=root,stderr=subprocess.DEVNULL)
    paths=['domains/trips/data/'+name for name in ['geo.json','hotels.json','climate.json','world_cities.sqlite3','ourairports.json','campgrounds.json','guides.json','guides_vectors.npy']]+['apps/static/events.json','apps/static/heritage.json']
    result={'refs':{ref:git('rev-parse',ref).decode().strip() for ref in args.refs},'files':{},'geo':{},'events':{}}
    for path in paths:
        result['files'][path]={}
        for ref in args.refs:
            try:blob=git('show',ref+':'+path)
            except subprocess.CalledProcessError:result['files'][path][ref]=None;continue
            result['files'][path][ref]={'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)}
            if path.endswith('/geo.json'):
                data=json.loads(blob);origins=data['origins']
                result['geo'][ref]={'origins':len(origins),'destinations':len(data['destinations']),
                    'duplicate_origin_names':[k for k,v in Counter(o['name'] for o in origins).items() if v>1],
                    'shared_airport_codes':[k for k,v in Counter(o['iata'] for o in origins).items() if v>1]}
            if path.endswith('/events.json'):
                events=json.loads(blob)['events'];result['events'][ref]={'count':len(events),'unique_ids':len({e['id'] for e in events}),
                    'editorial_descriptions':sum(bool(e.get('description')) for e in events),'dedicated_event_photos':sum(bool(e.get('image')) for e in events)}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'refs':result['refs'],'geo':result['geo']},ensure_ascii=False))

if __name__=='__main__':main()
