"""Reproduce the licensed thematic event covers (stdlib; no image transforms).

Downloads Commons-generated thumbnails. Attribution and the original photo date
stay beside each asset; covers illustrate the topic, not the announced edition.
"""
import concurrent.futures
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import urllib.error
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'apps/static/img/events'
FILES = {
    'race': 'Charles Leclerc 2020 Tuscan Grand Prix - race day.jpg',
    'classical': 'Concert Orchestra Cellos and Bassses.jpg',
    'art': '07 The Museum of Contemporary Art & Planning Exhibition in 2025.jpg',
    'village': 'A Friday in Global Village.jpg',
    'running': 'Berlin-Marathon 2015 Runners 14.jpg',
    'golf': 'Golfer swing.jpg',
    'football': 'Football match at Dasharath Rangashala stadium.jpg',
    'film': 'Interior of Latchis Theater from Balcony (August 2025).jpg',
    'music': 'Pattaya Zoom Music Festival, Main stage in lights.jpg',
    'nature': 'Siberian Tiger enjoying snow 10.jpg',
}


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'OdinTravelHackathon/1.0 (educational prototype; Commons attribution)'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == 2:
                raise
            delay = min(55, int(error.headers.get('Retry-After') or 15) * (attempt+1))
            time.sleep(delay)


def download(entry):
    key, name = entry
    params = dict(action='query', format='json', prop='imageinfo', iiprop='url|extmetadata|size', iiurlwidth=640, titles='File:'+name)
    data = json.loads(fetch('https://commons.wikimedia.org/w/api.php?'+urllib.parse.urlencode(params)))
    page = next(iter(data['query']['pages'].values()))
    info = page['imageinfo'][0]
    meta = info['extmetadata']
    value = lambda key: html.unescape(re.sub('<[^>]+>', '', meta.get(key, {}).get('value', ''))).strip()
    license_name = value('LicenseShortName')
    if not license_name.startswith(('CC BY', 'CC0', 'Public domain')):
        raise ValueError(f'Unreviewed license: {name}: {license_name}')
    content = fetch(info.get('thumburl') or info['url'])
    if not content.startswith(b'\xff\xd8'):
        raise ValueError('Expected JPEG: '+name)
    (OUT / (key+'.jpg')).write_bytes(content)
    return key, dict(file='File:'+name, page=info['descriptionurl'], download=info.get('thumburl') or info['url'],
                     author=value('Artist'), license=license_name, license_url=value('LicenseUrl'),
                     photo_date=value('DateTimeOriginal'), changes='Commons thumbnail; displayed with CSS object-fit; no retouching',
                     sha256=hashlib.sha256(content).hexdigest())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        credits = dict(pool.map(download, FILES.items()))
    (OUT / 'credits.json').write_text(json.dumps(credits, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(credits)} licensed covers, {sum(p.stat().st_size for p in OUT.glob("*.jpg"))} bytes')


if __name__ == '__main__':
    main()
