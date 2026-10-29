"""Deterministic 180-second edit of real browser footage and authored motion graphics."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np
import json,math,subprocess,sys,wave

ROOT=Path(__file__).resolve().parent; R=ROOT/'render'; R.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'media-deps'))
import imageio_ffmpeg
FF=imageio_ffmpeg.get_ffmpeg_exe()
W,H,FPS=1920,1080,30
BG='#081c2b'; WHITE='#f5f8f6'; MUTED='#a3b7c2'; LIME='#b5f58a'; BLUE='#2957ef'
FONT=Path('C:/Windows/Fonts/segoeui.ttf'); BOLD=Path('C:/Windows/Fonts/seguisb.ttf')
font_cache={}
def font(n,bold=False):
 k=(n,bold)
 if k not in font_cache:font_cache[k]=ImageFont.truetype(str(BOLD if bold else FONT),n)
 return font_cache[k]
def txt(d,xy,s,size=32,color=WHITE,bold=False):d.text(xy,s,font=font(size,bold),fill=color,stroke_width=0)
def ease(t):return 1-(1-max(0,min(1,t)))**3
def wrap(d,s,size,width,bold=False):
 lines=[];line=''
 for word in s.split():
  candidate=(line+' '+word).strip()
  if d.textlength(candidate,font=font(size,bold))>width and line:lines.append(line);line=word
  else:line=candidate
 if line:lines.append(line)
 return lines
def para(d,xy,s,size,width,color=MUTED,bold=False,gap=1.35):
 x,y=xy
 for line in wrap(d,s,size,width,bold):txt(d,(x,y),line,size,color,bold);y+=size*gap
 return y

def background():
 yy,xx=np.mgrid[0:H,0:W]; a=np.zeros((H,W,3),dtype=np.float32);a[:]=[8,28,43]
 glow=np.exp(-(((xx-1550)/700)**2+((yy-350)/800)**2))
 a+=glow[:,:,None]*np.array([3,18,26]);im=Image.fromarray(np.uint8(a.clip(0,255)))
 d=ImageDraw.Draw(im)
 for x in range(0,W,120):d.line((x,0,x,H),fill=(17,40,55),width=1)
 for y in range(0,H,120):d.line((0,y,W,y),fill=(17,40,55),width=1)
 return im
BASE=background()
def brand(d,x,y,size):
 f=font(size,True);p=x
 for s,c in [('О',WHITE),('!',LIME),('дин запрос',WHITE)]:
  d.text((p,y),s,font=f,fill=c);p+=d.textlength(s,font=f)

def orbit(d,t,cx=1440,cy=470,r=270):
 col=(47,88,110)
 d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(107,171,178),width=2)
 for k in [.25,.55,.82]:
  d.ellipse((cx-r*k,cy-r,cx+r*k,cy+r),outline=col,width=2)
  d.ellipse((cx-r,cy-r*k*.4,cx+r,cy+r*k*.4),outline=col,width=2)
 for j in range(3):
  ang=t*.22+j*2.094;x=cx+math.cos(ang)*(r+35);y=cy+math.sin(ang)*(r+35)*.63
  d.ellipse((x-9,y-9,x+9,y+9),fill=LIME if j==0 else '#5b8af4')
 d.arc((cx-r-35,cy-(r+35)*.63,cx+r+35,cy+(r+35)*.63),0,360,fill=(70,117,139),width=2)

def intro(t):
 im=BASE.copy();d=ImageDraw.Draw(im);orbit(d,t)
 txt(d,(120,105),'О! ХАКАТОН 2026',25,LIME,True)
 off=90*(1-ease(t/1.1));brand(d,120+off,245,112)
 if t>.65:para(d,(124,405+25*(1-ease((t-.65)/.8))),'Целая поездка. Одно желание.',43,1050,WHITE)
 if t>1.8:
  txt(d,(126,644),'ИСКУССТВЕННЫЙ ПРАЙМ',25,LIME,True)
  txt(d,(122,696),'Артемий и Даниил',51,WHITE,True)
  txt(d,(126,775),'Разработчики AI-агента для путешествий',29,MUTED)
 if t>3.3:
  for i,label in enumerate(['ГЛОБУС','ГОЛОС','ДИАЛОГ']):
   x=122+i*200;y=900+25*(1-ease((t-3.3-i*.15)/.6))
   d.rounded_rectangle((x,y,x+176,y+55),radius=27,fill=(20,48,63),outline=(49,80,96),width=1)
   txt(d,(x+22,y+12),label,20,WHITE,True)
 return im

def architecture(t):
 im=BASE.copy();d=ImageDraw.Draw(im)
 txt(d,(120,95),'ПОД КАПОТОМ',24,LIME,True)
 txt(d,(116,157),'Понимание + состояние + проверки',63,WHITE,True)
 labels=[('Ввод','Глобус · голос · чат'),('Агент','LLM · правила · контекст'),('Данные','Каталог · RAG · API')]
 for i,(title,sub) in enumerate(labels):
  u=ease((t-i*.3)/.8);x=120+i*580;y=335+35*(1-u)
  d.rounded_rectangle((x,y,x+520,y+210),radius=26,fill=(17,45,62),outline=(58,90,105),width=2)
  txt(d,(x+34,y+36),title,46,WHITE,True);txt(d,(x+34,y+119),sub,26,MUTED)
  if i<2:
   d.line((x+532,y+105,x+565,y+105),fill=LIME,width=3)
   d.polygon([(x+565,y+105),(x+555,y+97),(x+555,y+113)],fill=LIME)
 if t>.7:
  d.rounded_rectangle((120,614,1800,910),radius=24,fill=(13,35,50),outline=(45,73,89),width=1)
  txt(d,(158,650),'ОСТРОВОК API',25,LIME,True)
  para(d,(158,706),'Адаптер поиска подготовлен. Для живых тарифов и реальной брони нужно подключение поставщика.',37,1530,WHITE)
  txt(d,(158,844),'В ролике — демонстрационные предложения и оформление.',26,MUTED)
 txt(d,(120,986),'Интерфейс работает с одним сервером: полный сайт и встраиваемый чат.',25,MUTED)
 return im

def outro(t):
 im=BASE.copy();d=ImageDraw.Draw(im)
 txt(d,(120,72),'ИСКУССТВЕННЫЙ ПРАЙМ · АРТЕМИЙ И ДАНИИЛ',23,LIME,True)
 brand(d,117,122+35*(1-ease(t/.9)),92)
 txt(d,(123,255),'От идеи на глобусе — до собранной поездки.',40,WHITE)
 cards=[('Глобус и события','29 поводов отправиться в путешествие'),('Голос, чат и панель','Три способа управлять одной поездкой'),('65 924 объекта размещения','Открытый каталог, привязанный к карте'),('Ответы с источниками','RAG по путеводителям Wikivoyage'),('Контекст и пересборка','Меняем условие, сохраняем остальное'),('Полный сайт и виджет','Один агент в двух интерфейсах')]
 for i,(a,b) in enumerate(cards):
  x=120+(i%3)*580;u=ease((t-.6-i*.22)/.8);y=372+(i//3)*240+35*(1-u)
  if u<=0:continue
  d.rounded_rectangle((x,y,x+548,y+207),radius=24,fill=(17,44,60),outline=(45,75,92),width=1)
  d.rounded_rectangle((x+27,y+28,x+34,y+70),radius=3,fill=LIME)
  para(d,(x+52,y+28),a,32,465,WHITE,True,1.2)
  para(d,(x+28,y+118),b,24,485,MUTED,False,1.3)
 txt(d,(122,895),'Целая поездка. Одно желание.',42,WHITE,True)
 txt(d,(122,972),'Каталог открытых данных. Цены, наличие и оформление — демо.',25,MUTED)
 return im

def encode_frames(name,duration,fn):
 path=R/(name+'.mp4')
 cmd=[FF,'-y','-hide_banner','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 for n in range(round(duration*FPS)):
  frame=fn(n/FPS)
  if n==round(duration*FPS/2):frame.save(R/(name+'-preview.png'))
  proc.stdin.write(frame.tobytes())
 proc.stdin.close()
 if proc.wait()!=0:raise RuntimeError('encode '+name)
 print('RENDERED '+name,flush=True)

TIMELINE=[
('01_globe',12,'Вдохновение начинается с глобуса','Места и события помогают выбрать, ради чего поехать.'),
('02_event',10,'Нашли повод. Нажали «Хочу».','Формула-1 в Дохе → направление сразу появляется в диалоге.'),
('03_voice',13,'Можно просто сказать','GigaAM → распознанный текст → проверка → отправка. Записанный аудиопример.'),
('04_complex',18,'Одна поездка. Много условий.','2 взрослых + ребёнок 8 лет · Москва · 27–30 ноября · без пересадок · завтрак.'),
('05_budget',12,'Часть условий меняем в панели','300 000 → 250 000 ₽. Даты, направление и состав сохраняются.'),
('06_change',14,'Передумали? Продолжаем разговор.','Теперь Дубай. Агент сохраняет даты, состав и бюджет поездки.'),
('07_rag',12,'Объяснения с опорой на источник','RAG находит фрагменты путеводителя. Источник виден прямо в ответе.'),
('08_compare',12,'Сравниваем то, что важно','Отель, дорога, трансферы и компромиссы — в одном плане.'),
('09_checkout',16,'Доводим выбор до результата','Явное подтверждение → демонстрационный заказ. Без списания денег.'),
('10_new_theme',8,'Новая история — в вашей теме','Начинаем новую поездку и переключаем оформление.'),
('11_accessibility',10,'Особые условия — конкретно','Вход без ступенек, адаптированный номер. Доступность требует подтверждения.'),
('12_widget',10,'Тот же агент на другом сайте','Встраиваемый чат сохраняет логику, условия и возможности сервиса.')]

def make_overlay(idx,title,sub):
 im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im)
 # Footage is 1600x900 at (160,40); original UI and its disclosures remain visible.
 d.rounded_rectangle((159,39,1761,941),radius=3,outline=(80,110,125,210),width=1)
 txt(d,(160,9),'О!ДИН ЗАПРОС',17,LIME,True)
 txt(d,(1190,9),'ЗАПИСЬ ПРОТОТИПА · ОЖИДАНИЕ СОКРАЩЕНО',16,MUTED)
 d.rounded_rectangle((90,964,142,1016),radius=14,fill=LIME)
 txt(d,(102,973),f'{idx:02}',22,BG,True)
 txt(d,(160,953),title,35,WHITE,True)
 txt(d,(162,1005),sub,23,MUTED)
 d.line((160,1057,1760,1057),fill=(43,65,80,255),width=2)
 d.line((160,1057,160+int(1600*idx/12),1057),fill=LIME,width=3)
 path=R/f'overlay-{idx:02}.png';im.save(path);return path

def build_ui():
 data=json.loads((ROOT/'recordings'/'capture.json').read_text(encoding='utf-8'))
 shots={x['name']:x for x in data['shots']}
 raw=(ROOT/'recordings'/'raw-path.txt').read_text(encoding='utf-8')
 for idx,(name,duration,title,sub) in enumerate(TIMELINE,1):
  if len(sys.argv)>2 and name not in sys.argv[2:]:continue
  shot=shots[name];srcduration=shot['end']-shot['start'];speed=min(1.65,max(.85,srcduration/duration))
  raw=shot.get('raw') or (ROOT/'recordings'/'raw-path.txt').read_text(encoding='utf-8')
  overlay=make_overlay(idx,title,sub)
  focus={'03_voice':(.28,1360,650),'05_budget':(.16,1050,480),'06_change':(.22,1370,560),'07_rag':(.32,1370,500),'11_accessibility':(.35,1360,470),'12_widget':(.25,1390,500)}
  camera=''
  if name in focus:
   z,cx,cy=focus[name]
   camera=f",zoompan=z='1+{z}*(1-cos(PI*min(1,max(0,(on-25)/70))))/2':x='min(iw-iw/zoom,max(0,{cx}-iw/zoom/2))':y='min(ih-ih/zoom,max(0,{cy}-ih/zoom/2))':d=1:s=1600x900:fps=30"
  filt=f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30,scale=1600:900{camera},pad=1920:1080:160:40:color=0x081c2b,tpad=stop_mode=clone:stop_duration=30,trim=duration={duration}[v];[v][1:v]overlay=0:0,fade=t=in:st=0:d=0.25:color=0x081c2b,fade=t=out:st={duration-.25}:d=0.25:color=0x081c2b[out]'
  cmd=[FF,'-y','-hide_banner','-loglevel','error','-ss',str(shot['start']),'-t',str(srcduration),'-i',raw,'-loop','1','-i',str(overlay),'-filter_complex',filt,'-map','[out]','-t',str(duration),'-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(R/(name+'.mp4'))]
  subprocess.run(cmd,check=True);print('EDITED '+name,flush=True)

def soundtrack():
 sr=44100;dur=180;n=sr*dur;audio=np.zeros((n,2),dtype=np.float32);rng=np.random.default_rng(53)
 def tone(start,length,freq,amp,pan=0):
  count=int(length*sr);t=np.arange(count,dtype=np.float32)/sr
  envelope=np.minimum(t/.025,1)*np.exp(-t/(length*.30))*np.minimum((length-t)/.15,1).clip(0,1)
  sig=(np.sin(2*np.pi*freq*t)+.22*np.sin(2*np.pi*freq*2*t)+.08*np.sin(2*np.pi*freq*3*t))*envelope*amp
  i=int(start*sr);size=min(len(sig),n-i)
  if size>0:audio[i:i+size,0]+=sig[:size]*(1-pan*.3);audio[i:i+size,1]+=sig[:size]*(1+pan*.3)
 # Original restrained instrumental bed: four chords, bell arpeggio, soft pulse.
 beat=60/96;chords=[[50,57,62,65],[46,53,58,62],[53,60,65,69],[48,55,60,64]]
 for bar in range(math.ceil(dur/(beat*4))):
  chord=chords[bar%4];start=bar*beat*4
  for j,note in enumerate(chord):tone(start,beat*4,440*2**((note-69)/12),.020,(-1)**j*.65)
  for k in range(4):tone(start+k*beat,beat*1.7,440*2**((chord[k%4]+12-69)/12),.018,(-1)**k*.7)
  for k in [0,2]:tone(start+k*beat,.22,55,.024)
 fade=np.minimum(np.arange(n)/sr/3,1)*np.minimum((n-np.arange(n))/sr/5,1)
 audio*=fade[:,None];audio=np.tanh(audio*1.7)*.6
 with wave.open(str(R/'music.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((audio*32767).astype('<i2').tobytes())

def assemble():
 names=['intro']+[x[0] for x in TIMELINE]+['architecture','outro']
 (R/'concat.txt').write_text('\n'.join("file '"+str(R/(name+'.mp4')).replace('\\','/')+"'" for name in names),encoding='utf-8')
 soundtrack()
 target=ROOT.parent/'outputs'/'Один_запрос_демо_3мин.mp4'
 target.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run([FF,'-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(R/'concat.txt'),'-i',str(R/'music.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','160k','-t','180','-movflags','+faststart',str(target)],check=True)
 intro(5).save(ROOT.parent/'outputs'/'Один_запрос_обложка.png')
 print('FINAL '+str(target),flush=True)

if __name__=='__main__':
 mode=sys.argv[1] if len(sys.argv)>1 else 'all'
 if mode in ['graphics','all']:
  encode_frames('intro',9,intro);encode_frames('architecture',10,architecture);encode_frames('outro',14,outro)
 if mode in ['ui','all']:build_ui()
 if mode in ['assemble','all']:assemble()
