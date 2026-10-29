"""Record genuine browser interactions; no mocked application responses."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import json,time,re,traceback

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'recordings'; OUT.mkdir(exist_ok=True)
BASE='http://127.0.0.1:8080'
records=[]; responses=[]; started=0; stage_start=0

CURSOR="""() => {
const c=document.createElement('div'); c.id='film-cursor';
c.style.cssText='position:fixed;left:50%;top:80%;width:20px;height:20px;background:#aef17a;border:3px solid #15304a;border-radius:50%;z-index:2147483647;pointer-events:none;transform:translate(-50%,-50%);box-shadow:0 0 0 6px #aef17a30';
document.body.append(c);document.addEventListener('mousemove',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px'});
document.addEventListener('mousedown',()=>c.animate([{boxShadow:'0 0 0 6px #aef17a90'},{boxShadow:'0 0 0 26px #aef17a00'}],{duration:500}));
}"""

def save():
 (OUT/'capture.json').write_text(json.dumps({'source_commit':'53a2aa7aeec46d54827411272d2b6f3ae333f9c1','shots':records,'responses':responses},ensure_ascii=False,indent=2),encoding='utf-8')
def begin(name):
 global stage_start
 stage_start=time.monotonic()-started
 print('BEGIN '+name,flush=True)
def finish(name,hold=2):
 page.wait_for_timeout(hold*1000)
 page.screenshot(path=str(OUT/(name+'.png')))
 records.append({'name':name,'start':round(stage_start,3),'end':round(time.monotonic()-started,3),'screenshot':name+'.png'})
 save(); print('DONE '+name,flush=True)
def move_to(loc):
 loc=loc.first
 loc.scroll_into_view_if_needed()
 b=loc.bounding_box()
 page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=20)
 page.wait_for_timeout(300)
def click(loc):
 loc=loc.first
 move_to(loc);loc.click()
def wait_idle():
 page.wait_for_function("!document.querySelector('#send').disabled",timeout=120000)
def record_data(d):
 responses.append({k:d.get(k) for k in ['stage','nlu','reply','trip_summary','understood']})
 responses[-1]['payload_kind']=(d.get('payload') or {}).get('kind')
 save()
 return d
def action(loc):
 with page.expect_response(lambda r: r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as response:
  click(loc)
 d=record_data(response.value.json());wait_idle();return d
def say(text,typing=True):
 loc=page.locator('#text');click(loc)
 if typing:loc.press_sequentially(text,delay=22)
 else:loc.fill(text)
 page.wait_for_timeout(700)
 return action(page.locator('#send'))

with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',f'--use-file-for-fake-audio-capture={ROOT / "voice-input.wav"}%noloop','--autoplay-policy=no-user-gesture-required'])
 context=browser.new_context(viewport={'width':1600,'height':900},device_scale_factor=1,permissions=['microphone'],locale='ru-RU',record_video_dir=str(OUT),record_video_size={'width':1600,'height':900})
 started=time.monotonic();page=context.new_page();page.set_default_timeout(20000)
 video=page.video
 try:
  page.goto(BASE+'/static/favicon.svg')
  page.evaluate("localStorage.setItem('odin.tour.v2','seen');localStorage.setItem('odin.theme','light');localStorage.setItem('odin.currency','RUB');")
  page.goto(BASE+'/');wait_idle();page.wait_for_function('tripMap.getView()?.models.length>0',timeout=60000)
  page.wait_for_timeout(2500);page.evaluate(CURSOR)
  begin('01_globe')
  b=page.locator('.map-surface').bounding_box()
  page.mouse.move(b['x']+b['width']*.48,b['y']+b['height']*.55)
  page.mouse.down();page.mouse.move(b['x']+b['width']*.39,b['y']+b['height']*.52,steps=50);page.mouse.up()
  page.wait_for_timeout(1800)
  click(page.get_by_role('button',name='Дизайнерская',exact=True));page.wait_for_timeout(1700)
  click(page.get_by_role('button',name='Географическая',exact=True))
  finish('01_globe',3)

  begin('02_event')
  page.get_by_role('combobox',name='Тип мест').select_option('event');page.wait_for_timeout(1000)
  # The event card is part of the interactive globe and moves the camera to Doha.
  click(page.locator('[data-event-id="f1-qatar-2026"]'))
  page.locator('.event-story').wait_for();page.wait_for_timeout(2200)
  page.screenshot(path=str(OUT/'02_event_detail.png'))
  d=action(page.get_by_role('button',name='Хочу на событие',exact=True))
  assert d['trip_summary']['destination']=='Доха'
  finish('02_event',2)

  begin('03_voice')
  click(page.get_by_role('button',name='Начать диктовку',exact=True));page.locator('#voice-dialog').wait_for()
  click(page.locator('#voice-allow'));page.wait_for_timeout(6200)
  click(page.get_by_role('button',name='Остановить диктовку',exact=True))
  page.wait_for_function("document.querySelector('#text').value.length>10",timeout=60000)
  transcript=page.locator('#text').input_value()
  assert 'взросл' in transcript.lower() and ('восьм' in transcript.lower() or '8' in transcript),transcript
  page.screenshot(path=str(OUT/'03_transcript.png'));page.wait_for_timeout(1800)
  action(page.locator('#send'));finish('03_voice',2)

  begin('04_complex')
  d=say('Из Москвы с 27 по 30 ноября 2026. Бюджет 300 тысяч рублей на всех. Без пересадок, нужен завтрак.')
  assert d['trip_summary']['children']==1 and d['trip_summary']['adults']==2,d['trip_summary']
  assert d['payload']['kind']=='packages'
  page.locator('#view').scroll_into_view_if_needed();page.wait_for_timeout(1800)
  finish('04_complex',3)

  begin('05_budget')
  click(page.locator('#trip-context-toggle'));page.wait_for_timeout(500)
  click(page.locator('[data-trip-field="budget"]'));page.locator('#condition-value').fill('250000')
  page.wait_for_timeout(1300);d=action(page.locator('#condition-form [type=submit]'))
  assert d['trip_summary']['budget_total']==250000
  finish('05_budget',2.5)

  begin('06_change')
  d=say('Передумали. Давай лучше в Дубай. Даты и состав оставь прежними.')
  assert d['trip_summary']['destination']=='Дубай' and d['trip_summary']['children']==1
  assert d['trip_summary']['date_from']=='2026-11-27' and d['trip_summary']['budget_total']==250000
  page.locator('#view').scroll_into_view_if_needed();finish('06_change',3)

  begin('07_rag')
  d=say('Что там посмотреть?')
  assert 'Wikivoyage' in d['reply'],d['reply']
  finish('07_rag',5)

  begin('08_compare')
  click(page.get_by_role('button',name='Сравнить',exact=True));page.wait_for_timeout(1400)
  page.locator('.compare-table').scroll_into_view_if_needed();page.wait_for_timeout(1800)
  page.screenshot(path=str(OUT/'08_table.png'))
  d=action(page.locator('.compare-table').get_by_role('button',name='Выбрать',exact=True).first)
  assert d['payload']['kind']=='cart';page.locator('.basket-total').scroll_into_view_if_needed();finish('08_compare',3)

  begin('09_checkout')
  d=action(page.get_by_role('button',name='Перейти к оплате',exact=True))
  page.wait_for_timeout(1200)
  d=action(page.get_by_role('button',name='Демо-СБП',exact=True));page.wait_for_timeout(1500)
  d=action(page.get_by_role('button',name='Подтвердить демонстрацию',exact=True))
  assert d['stage']=='booked';page.locator('.pass').scroll_into_view_if_needed();finish('09_checkout',4)

  begin('10_new_theme')
  click(page.locator('#reset'));page.wait_for_timeout(600);click(page.locator('#reset-confirm'));wait_idle()
  click(page.locator('#theme-toggle'));page.wait_for_timeout(2200)
  finish('10_new_theme',2)

  begin('11_accessibility')
  d=say('Хочу в Казань на выходные. Я пользуюсь креслом-коляской: нужен вход без ступенек и адаптированный номер.')
  assert 'не проверена' in d['reply'] or 'не проверены' in d['reply'],d['reply']
  finish('11_accessibility',5)

  begin('12_widget')
  page.goto(BASE+'/static/widget-demo.html');page.wait_for_timeout(2000);page.evaluate(CURSOR)
  click(page.get_by_role('button',name='Открыть помощника по поездкам',exact=True));page.wait_for_timeout(2500)
  frame=page.frame_locator('#o-trip-widget > iframe').frame_locator('iframe')
  frame.locator('#text').wait_for();page.wait_for_timeout(1500)
  finish('12_widget',3)
  print('CAPTURE PASS',flush=True)
 except Exception as e:
  page.screenshot(path=str(OUT/'failure.png'));save();print('CAPTURE FAIL '+str(e),flush=True);traceback.print_exc()
 finally:
  raw=str(video.path());context.close();browser.close()
  (OUT/'raw-path.txt').write_text(raw,encoding='utf-8');save()
  print('VIDEO '+raw,flush=True)
