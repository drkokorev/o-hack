from pathlib import Path
from playwright.sync_api import sync_playwright
import json,time
ROOT=Path(__file__).resolve().parent;out=ROOT/'recordings';base='http://127.0.0.1:8080'
data=json.loads((out/'capture.json').read_text(encoding='utf-8'))
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True)
 context=browser.new_context(viewport={'width':1600,'height':900},locale='ru-RU',record_video_dir=str(out),record_video_size={'width':1600,'height':900})
 t=time.monotonic();page=context.new_page();video=page.video
 page.goto(base+'/static/favicon.svg');page.evaluate("localStorage.setItem('odin.tour.v2','seen');localStorage.setItem('odin.theme','light');")
 page.goto(base+'/static/widget-demo.html');page.wait_for_timeout(1500)
 start=time.monotonic()-t
 page.get_by_role('button',name='Открыть помощника по поездкам').click()
 frame=page.frame_locator('#o-trip-widget > iframe').frame_locator('iframe')
 frame.locator('#text').wait_for();page.wait_for_timeout(1500)
 frame.locator('#text').fill('В Казань из Москвы с 5 по 8 декабря 2026, двое взрослых.')
 page.wait_for_timeout(1200)
 with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as reply:frame.locator('#send').click()
 d=reply.value.json();assert d['payload']['kind']=='packages'
 page.wait_for_timeout(1800)
 frame.locator('button[data-panel="results"]').click();page.wait_for_timeout(2200)
 page.screenshot(path=str(out/'12_widget.png'));end=time.monotonic()-t
 raw=str(video.path());context.close();browser.close()
 data['shots']=[x for x in data['shots'] if x['name']!='12_widget']+[{'name':'12_widget','start':start,'end':end,'screenshot':'12_widget.png','raw':raw}]
 data['widget_check']={'result':'PASS','kind':d['payload']['kind'],'destination':d['trip_summary']['destination'],'nlu':d['nlu']}
 (out/'capture.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 print('WIDGET PASS',round(end-start,2))
