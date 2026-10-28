"""Twenty-four original additions. Reuses the collection's mineral materials."""
import math
from math import sin,cos,pi,sqrt

def column(b,x,y,z,h,r=.11,mat='ivory'):
    b.lathe([(z,r*1.4),(z+.10,r*1.4),(z+.16,r),(z+h-.16,r*.85),(z+h-.12,r*1.3),(z+h,r*1.3)],mat,pos=(x,y,0),n=12)
    for i in range(8):
        a=i*pi/4;b.beam((x+r*cos(a),y+r*sin(a),z+.20),(x+r*.85*cos(a),y+r*.85*sin(a),z+h-.2),.012,'stone',n=4)

def dome(b,x,y,z,r,h,mat='gold',onion=False):
    p=[(z,r*.94),(z+h*.08,r),(z+h*.25,r*1.02),(z+h*.50,r*.94),(z+h*.72,r*.72),(z+h*.88,r*.40),(z+h,r*.015)] if onion else [(z+h*sin(i*pi/2/16),r*cos(i*pi/2/16)) for i in range(17)]
    b.lathe(p,mat,pos=(x,y,0),n=40)
    for i in range(12):
        a=i*pi/6;b.path([(x+rr*cos(a),y+rr*sin(a),zz+.006) for zz,rr in p],.012,'gold' if mat=='gold' else 'stone',n=4)
    b.beam((x,y,z+h),(x,y,z+h+.32),.024,'gold',r2=.008)

def portal(b,x,y,z,w,h,mat='ivory',outline='stone'):
    # Recessed pointed arch facade with pronounced frame and inner geometry.
    b.box((x,y,z+h*.43),(w,.07,h*.86),'ink')
    b.arch(x,y-.05,z,w*.78,h*.58,w*.09,.10,outline,steps=14)
    for xx in [-w*.52,w*.52]:b.box((x+xx,y-.06,z+h*.52),(w*.08,.12,h*1.04),mat)
    b.box((x,y-.06,z+h*1.04),(w*1.13,.12,.09),mat)

def pediment(b,x,y,z,w,d,h,mat='ivory'):
    vs=[(x-w/2,y-d/2,z),(x+w/2,y-d/2,z),(x,y-d/2,z+h),(x-w/2,y+d/2,z),(x+w/2,y+d/2,z),(x,y+d/2,z+h)]
    b.add(vs,[(0,2,1),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)],mat)

def isaac():
    b=Builder('isaac');foundation(b,6.3,5.9)
    for j in range(3):b.box((0,0,.30+j*.13),(5.8-j*.25,5.4-j*.25,.13),'stone')
    b.box((0,0,1.73),(3.55,3.55,2.5),'stone')
    for a in [0,pi/2,pi,3*pi/2]:
        for x in [-1.4,-.84,-.28,.28,.84,1.4]:
            column(b,x*cos(a)+2.05*sin(a),x*sin(a)-2.05*cos(a),.64,2.18,.14,'bronze')
        # Four classical porticoes.
        if a in [0,pi]:
            y=-2.05 if a==0 else 2.05;b.box((0,y,2.9),(3.6,.8,.22),'ivory');pediment(b,0,y,3.03,3.7,.85,.62)
        else:
            x=2.05 if a==pi/2 else -2.05;b.box((x,0,2.9),(.8,3.6,.22),'ivory')
    b.box((0,0,3.12),(3.8,3.8,.18),'ivory')
    b.lathe([(3.2,1.34),(3.4,1.34),(3.42,1.13),(4.52,1.13),(4.65,1.36)],'stone',n=48)
    for i in range(20):
        a=2*pi*i/20;column(b,1.23*cos(a),1.23*sin(a),3.43,1.03,.065,'bronze')
    dome(b,0,0,4.67,1.32,1.26,'gold')
    b.lathe([(5.92,.21),(6.15,.21),(6.24,.13)],'ivory',n=20);dome(b,0,0,6.23,.18,.22,'gold')
    b.beam((-.12,0,6.73),(.12,0,6.73),.025,'gold')
    for x in [-1.38,1.38]:
        for y in [-1.38,1.38]:
            b.lathe([(3.24,.33),(3.75,.33)],'ivory',pos=(x,y,0),n=20);dome(b,x,y,3.75,.39,.32,'gold')
    for x in [-1,0,1]:portal(b,x,-1.79,.73,.54,1.48)
    return b

def kulsharif():
    b=Builder('kulsharif');foundation(b,5.8,5.3)
    b.box((0,0,.48),(4.7,4.1,.46),'stone');b.box((0,0,1.75),(2.65,2.65,2.3),'ivory')
    b.lathe([(2.9,1.3),(3.33,1.16)],'ivory',n=8);dome(b,0,0,3.34,1.22,1.12,'glass',onion=True)
    for a in [0,pi/2,pi,3*pi/2]:
        x,y=1.33*sin(a),-1.33*cos(a)
        if a==0:portal(b,x,y-.04,.70,1.30,1.93,'ivory','gold')
    for x in [-1.91,1.91]:
        for y in [-1.72,1.72]:
            b.lathe([(.70,.32),(.91,.32),(1.0,.23),(4.3,.18),(4.35,.32),(4.53,.32),(4.62,.18),(5.26,.15)],'ivory',pos=(x,y,0),n=16)
            b.lathe([(5.26,.26),(6.28,.005)],'glass',pos=(x,y,0),n=16)
            b.beam((x,y,6.28),(x,y,6.52),.018,'gold')
            for i in range(8):
                a=i*pi/4;b.beam((x+.23*cos(a),y+.23*sin(a),1.1),(x+.18*cos(a),y+.18*sin(a),4.25),.018,'stone',n=4)
    for x in [-.97,.97]:
        for z in [1.25,2.05]:portal(b,x,-1.35,z,.26,.45,'ivory','glass')
    for x in [-1.17,1.17]:
        for y in [-1.17,1.17]:dome(b,x,y,2.92,.35,.50,'glass',onion=True)
    for j in range(4):b.box((0,-1.9-j*.18,.67-j*.10),(1.35,.4,.12),'ivory')
    return b

def sochi():
    b=Builder('sochi_port');foundation(b,7.5,3.9)
    b.box((0,0,.36),(7.2,3.6,.24),'stone')
    for x in [-2.15,2.15]:
        b.box((x,.2,1.3),(2.5,1.6,1.8),'ivory');b.box((x,.2,2.27),(2.7,1.8,.15),'stone')
        for i in range(5):
            xx=x-1+i*.5;b.arch(xx,-.67,.5,.30,.83,.065,.15,'ivory',steps=10)
            b.box((xx,-.62,1.05),(.29,.05,.83),'ink')
            b.box((xx,-.63,1.88),(.24,.04,.34),'glass')
    b.box((0,0,1.7),(1.65,2,2.6),'ivory');portal(b,0,-1.02,.5,1.05,1.55)
    for z,w,h in [(3.02,1.95,.18),(3.37,1.35,.50),(3.83,1.58,.16),(4.45,.96,1.1),(5.05,1.24,.18)]:b.box((0,0,z),(w,w,h),'ivory')
    for x in [-.55,.55]:
        for y in [-.55,.55]:column(b,x,y,3.92,1.02,.065,'stone')
    b.lathe([(5.14,.55),(5.43,.44),(5.55,.28)],'gold',n=24)
    b.beam((0,0,5.55),(0,0,7.55),.085,'gold',r2=.008,n=16)
    for s in [-1,1]:
        b.box((s*3.28,-1.2,.72),(.45,.45,.65),'ivory')
        b.ellipsoid((s*3.28,-1.2,1.22),(.19,.16,.35),'ivory',n=12,rings=10)
    return b

def rock(b,cx,cy,z,rx,ry,h,mat='stone',seed=1):
    n=13;profiles=[(0,1),(.18,1.05),(.52,.82),(.82,.65),(1,.26)]
    vs=[]
    for k,(t,r) in enumerate(profiles):
        for i in range(n):
            a=i*2*pi/n;noise=1+.16*sin(i*2.7+seed)+.08*cos(k+i*1.3)
            vs.append((cx+rx*r*cos(a)*noise+sin(t*4+seed)*.12,cy+ry*r*sin(a)*noise,z+h*t+(sin(i*2.2+seed)*.12 if k else 0)))
    fs=[(k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i) for k in range(4) for i in range(n)]
    fs+=[tuple(reversed(range(n))),tuple(4*n+i for i in range(n))];b.add(vs,fs,mat)

def baikal():
    b=Builder('shamanka');foundation(b,6.6,5.3)
    b.box((0,0,.28),(6.45,5.15,.12),'glass')
    for x,y,rx,ry,h,s in [(-.65,.25,1.35,1.1,3.7,1),(.9,.35,.85,.82,2.85,5),(-1.65,.35,.75,.8,1.35,7),(.2,-.65,.8,.65,1.2,8)]:rock(b,x,y,.34,rx,ry,h,'stone',s)
    for i in range(8):
        y=-2.2+i*.54;b.path([(-3,y,.35),(-2.3,y+.12,.35),(-1.9,y-.1,.35)],.018,'silver',n=4)
    for pts in [[(-2,-2,.36),(-1.5,-1.65,.36),(-.7,-2,.36),(.3,-1.65,.36),(1.6,-2.3,.36)],[(1.9,-2.4,.36),(1.6,-1.5,.36),(2.3,-.6,.36),(2.5,1.2,.36)]]:b.path(pts,.025,'ivory',n=4)
    return b

def volcano(b,cx,cy,z,r,h,snow=False,seed=1):
    n=48;layers=15;vs=[]
    for j in range(layers):
        t=j/(layers-1);rr=r*(1-t)**1.25+.12*t
        for i in range(n):
            a=2*pi*i/n;wav=1+.06*sin(7*a+seed)+.04*sin(13*a-2*t)
            vs.append((cx+rr*wav*cos(a),cy+rr*wav*sin(a),z+h*t+.045*sin(9*a)*(t**3)))
    for j in range(layers-1):
        for i in range(n):
            material='ivory' if snow and j>layers*.65+(sin(i*1.7)*1.1) else ('roof' if j<2 else 'roof' if i%11<2 else 'basalt')
            b.add([vs[j*n+i],vs[j*n+(i+1)%n],vs[(j+1)*n+(i+1)%n],vs[(j+1)*n+i]],[(0,1,2),(0,2,3)],material)
    b.lathe([(z+h-.16,.13),(z+h-.14,.13)],'ink',pos=(cx,cy,0),n=24)

def kamchatka():
    b=Builder('kamchatka');foundation(b,7.5,5.7)
    b.box((0,0,.28),(7.3,5.5,.10),'mint')
    volcano(b,-.75,.4,.34,2.45,4.7,True,2);volcano(b,1.90,.5,.34,1.35,2.9,True,6)
    for i in range(6):rock(b,-2.9+i*.9,-2.0,.34,.24,.28,.33,'stone',i)
    return b

def bridge(suspension=True):
    key='golden_gate' if suspension else 'russky_bridge';b=Builder(key);foundation(b,9,3.8)
    b.box((0,0,.29),(8.85,3.65,.12),'glass');mat='brick' if suspension else 'ivory'
    b.box((0,0,1.76),(8.3,.78,.14),'ink');b.box((0,0,1.66),(8.35,.90,.12),mat)
    for x in [-2.4,2.4]:
        b.box((x,0,.64),(.85,1.3,.60),'stone')
        for y in [-.52,.52]:b.box((x,y,2.76),(.24,.24,4.28),mat)
        for z in [1.9,3.15,4.35,4.85]:b.box((x,0,z),(.30,1.28,.16),mat)
        if not suspension:
            b.beam((x,-.52,.95),(x,-.17,5.2),.12,mat,n=6);b.beam((x,.52,.95),(x,.17,5.2),.12,mat,n=6)
    for y in [-.46,.46]:
        b.beam((-4.15,y,1.95),(4.15,y,1.95),.022,mat,n=5)
        if suspension:
            points=[(x,y,2.65+(4.87-2.65)*(x/2.4)**2) for x in [-2.4+i*.15 for i in range(33)]]
            b.path(points,.045,mat,n=6)
            for x,yy,z in points[::2]:b.beam((x,yy,1.9),(x,yy,z),.015,mat,n=4)
            for s in [-1,1]:b.path([(s*2.4,y,4.87),(s*3.4,y,3.12),(s*4.14,y,2.08)],.045,mat)
        else:
            for x in [-2.4,2.4]:
                for s in [-1,1]:
                    for j in range(1,9):
                        xx=x+s*j*.22
                        b.beam((x,y,4.85-j*.075),(xx,y,1.84),.012,'silver',n=4)
    for i in range(20):b.box((-3.85+i*.4,0,1.84),(.18,.028,.008),'ivory')
    return b

def galata():
    b=Builder('galata');foundation(b,4.7,4.3)
    b.lathe([(.24,1.35),(.43,1.35),(.43,1.13),(4.05,1.04),(4.10,1.30),(4.30,1.30),(4.35,1.04),(5.05,.97)],'stone',n=48)
    for z in [.72,1.65,2.58,3.51]:
        b.lathe([(z,1.135-(z-.43)*.025),(z+.05,1.135-(z-.43)*.025)],'bronze',n=48)
        for i in range(8):
            a=i*pi/4;xx=1.12*cos(a);yy=1.12*sin(a);b.box((xx,yy,z+.37),(.22,.045,.38),'ink',a-pi/2)
    for i in range(24):
        a=i*pi/12;column(b,1.1*cos(a),1.1*sin(a),4.35,.66,.045,'ivory')
    b.lathe([(5.08,1.25),(5.23,1.25)],'bronze',n=48)
    b.lathe([(5.24,1.29),(7.05,.015)],'roof',n=48)
    for i in range(16):
        a=i*pi/8;b.beam((1.29*cos(a),1.29*sin(a),5.24),(.02*cos(a),.02*sin(a),7.05),.015,'bronze',n=4)
    b.beam((0,0,7.05),(0,0,7.55),.025,'gold')
    for i in range(24):
        a=i*pi/12;b.beam((1.28*cos(a),1.28*sin(a),4.30),(1.28*cos(a),1.28*sin(a),4.52),.018,'ink',n=4)
    b.ring(1.30,1.30,4.5,.04,.04,'ink',n=48)
    portal(b,0,-1.14,.28,.48,.87)
    return b

def cappadocia():
    b=Builder('cappadocia');foundation(b,6.2,5.0)
    b.box((0,0,.29),(6,4.8,.12),'sand')
    for x,y,h,r in [(-1.65,0,2.7,.55),(-.5,.6,3.2,.62),(1.4,.7,2.3,.50),(2,-.65,1.6,.36),(-1.0,-1.3,1.5,.42)]:
        b.lathe([(.35,r*1.4),(.7,r),(h*.72,r*.53),(h*.87,r*.65),(h,r*.15)],'stone',pos=(x,y,0),n=9,smooth=False)
        b.lathe([(h*.72,r*.75),(h*.86,r*.84),(h+.24,.01)],'bronze',pos=(x,y,0),n=9,smooth=False)
        if h>2:b.box((x,y-r*.85,1.02),(.18,.06,.25),'ink')
    x,y,z=.60,-.55,4.2
    b.box((x,y,z-.59),(.48,.48,.38),'bronze')
    for sx in [-1,1]:
        for sy in [-1,1]:b.beam((x+sx*.20,y+sy*.20,z-.4),(x+sx*.35,y+sy*.35,z+.05),.018,'ink',n=4)
    n=32;prof=[(0,.36),(.34,.72),(.82,1.02),(1.40,1.08),(1.85,.88),(2.12,.45),(2.2,.01)]
    for i in range(n):
        a=2*pi*i/n;aa=2*pi*(i+1)/n;mat=['brick','ivory','gold','ivory'][i//2%4]
        vs=[(x+r*cos(t),y+r*sin(t),z+zz) for zz,r in prof for t in [a,aa]]
        b.add(vs,[(2*j,2*j+1,2*j+3,2*j+2) for j in range(len(prof)-1)],mat,True)
    return b

def registan():
    b=Builder('registan');foundation(b,7.3,5.5)
    b.box((0,0,.30),(7.1,5.3,.13),'stone')
    for x in [-2.3,2.3]:
        b.box((x,.45,1.55),(1.7,3.4,2.45),'sand');b.box((x,.45,2.83),(1.82,3.5,.16),'glass')
        for i in range(5):portal(b,x,-1.29,.65+i*.01,.9,1.55,'glass','ivory') if i==0 else None
        for y in [-1.05,1.95]:
            b.lathe([(.35,.28),(3.2,.22),(3.3,.32),(3.55,.22)],'sand',pos=(x,y,0),n=16)
            for z in [.7,1.3,1.9,2.5,3.1]:b.lathe([(z,.285-(z-.35)*.02),(z+.065,.285-(z-.35)*.02)],'glass',pos=(x,y,0),n=16)
    b.box((0,1.55,1.7),(3.25,1.16,2.65),'sand');b.box((0,.88,2.26),(1.75,.35,3.8),'glass')
    portal(b,0,.68,.35,1.36,3.05,'ivory','glass')
    for x in [-.78,.78]:
        for z in [.6,1.0,1.4,1.8,2.2,2.6,3.0,3.4]:b.box((x,.65,z),(.095,.035,.12),'gold')
    b.lathe([(2.95,.73),(3.4,.73)],'ivory',pos=(0,1.55,0),n=32);dome(b,0,1.55,3.42,.86,1.05,'glass',True)
    for x in [-1.3,1.3]:portal(b,x,.94,.64,.51,1.6,'ivory','glass')
    for j in range(8):b.box((0,-1.9+j*.36,.39),(.52,.17,.025),'ivory')
    return b

def parthenon():
    b=Builder('parthenon');foundation(b,6.4,5.2)
    for i in range(3):b.box((0,0,.3+i*.14),(6.0-i*.3,4.8-i*.3,.14),'ivory')
    for x in [-2.42+i*.69 for i in range(8)]:
        for y in [-1.85,1.85]:column(b,x,y,.65,2.85,.16,'stone')
    for y in [-1.23+i*.61 for i in range(5)]:
        for x in [-2.42,2.42]:column(b,x,y,.65,2.85,.16,'stone')
    b.box((0,0,1.95),(3.1,2.2,2.55),'stone')
    for y in [-1.93,1.93]:
        b.box((0,y,3.57),(5.4,.42,.25),'ivory');pediment(b,0,y,3.80,5.55,.48,.9)
        for i in range(18):b.box((-2.5+i*.29,y-.25,3.65),(.09,.06,.23),'stone')
    for x in [-2.47,2.47]:b.box((x,0,3.57),(.42,3.9,.25),'ivory')
    # Surviving roof slabs, open center evokes the archaeological ruin.
    for x in [-1.95,1.95]:b.box((x,0,3.82),(.64,3.8,.18),'stone')
    return b

def belem():
    b=Builder('belem');foundation(b,5.0,4.7)
    b.box((0,0,.29),(4.85,4.55,.12),'glass');b.box((0,-.65,.69),(3.8,2.8,.74),'stone')
    b.box((0,.50,2.48),(2.4,2.2,3.75),'ivory')
    for z in [1.28,2.28,3.24,4.28]:b.box((0,.50,z),(2.58,2.36,.14),'stone')
    for x in [-.78,0,.78]:
        for z in [1.50,2.5,3.45]:portal(b,x,-.62,z,.38,.60,'ivory','stone')
    for x in [-1.1,1.1]:
        for y in [-.55,1.55]:
            b.lathe([(4.32,.27),(4.8,.27)],'ivory',pos=(x,y,0),n=16);dome(b,x,y,4.8,.28,.42,'stone',True)
    for x in [-.8,-.4,0,.4,.8]:
        for y in [-.68,1.68]:b.box((x,y,4.5),(.22,.2,.32),'ivory')
    for x in [-1.65,1.65]:
        for y in [-1.7,.1]:
            b.lathe([(1.05,.3),(1.62,.3)],'ivory',pos=(x,y,0),n=16);dome(b,x,y,1.62,.31,.32,'stone',True)
    for x in [-1.3,-.65,0,.65,1.3]:b.arch(x,-1.95,.44,.34,.24,.10,.16,'ivory',steps=10)
    return b

def sagrada():
    b=Builder('sagrada');foundation(b,5.5,4.9)
    b.box((0,.2,1.45),(3.6,3.2,2.4),'stone')
    # Tall perforated organic towers around the basilica's main spire.
    for x,y,h,r in [(-1.4,-1.1,5.4,.35),(-.5,-1.1,6.0,.37),(.5,-1.1,6.0,.37),(1.4,-1.1,5.4,.35),(-1.2,1.15,4.9,.31),(1.2,1.15,4.9,.31),(0,.45,7.8,.54)]:
        b.lathe([(2.1,r*1.3),(h*.72,r),(h*.87,r*.70),(h*.97,r*.25),(h,.02)],'stone',pos=(x,y,0),n=20)
        for j in range(7):
            zz=2.45+j*(h-2.7)/7;rr=r*(1-.32*j/7)
            for i in range(8):
                a=i*pi/4;b.box((x+rr*cos(a),y+rr*sin(a),zz),(.075,.035,.18),'ink',a-pi/2)
        b.ellipsoid((x,y,h+.07),(r*.30,r*.30,.17),'gold',n=12,rings=8)
    for x in [-1.0,0,1.0]:portal(b,x,-1.46,.28,.76,1.9,'ivory','bronze')
    for x in [-1.8,-1.2,-.6,0,.6,1.2,1.8]:
        b.beam((x,-1.42,.45),(x*.65,-1.42,2.9),.08,'ivory',n=6)
        b.pyramid((x*.76,-1.26,2.85),.45,.5,.9,'stone')
    b.beam((-.25,.45,8.0),(.25,.45,8.0),.055,'gold');b.beam((0,.45,7.75),(0,.45,8.35),.055,'gold')
    return b

def extend(namespace):
    globals().update({k:namespace[k] for k in ['Builder','foundation']})
    return {
      'isaac':(isaac,'Исаакиевский собор'), 'kulsharif':(kulsharif,'Мечеть Кул-Шариф'),
      'sochi_port':(sochi,'Морской вокзал Сочи'), 'shamanka':(baikal,'Скала Шаманка'),
      'kamchatka':(kamchatka,'Вулканы Камчатки'), 'russky_bridge':(lambda:bridge(False),'Русский мост'),
      'galata':(galata,'Галатская башня'), 'cappadocia':(cappadocia,'Скалы и воздушный шар Каппадокии'),
      'registan':(registan,'Регистан'), 'sagrada':(sagrada,'Саграда-Фамилия'),
      'parthenon':(parthenon,'Парфенон'), 'belem':(belem,'Башня Белен'),
      **more_models(),
    }

def more_models():
    return {
      'great_wall':(greatwall,'Великая Китайская стена'), 'taj_mahal':(taj,'Тадж-Махал'),
      'marina_bay':(marina,'Marina Bay Sands'), 'petronas':(petronas,'Башни Петронас'),
      'fuji':(fuji,'Гора Фудзи'), 'bali_temple':(bali,'Храм Улун-Дану'),
      'maldives':(maldives,'Виллы над водой'), 'christ':(christ,'Статуя Христа-Искупителя'),
      'chichen_itza':(chichen,'Пирамида Кукулькана'), 'golden_gate':(lambda:bridge(True),'Мост Золотые Ворота'),
      'opera':(opera,'Сиднейский оперный театр'), 'table_mountain':(tablemountain,'Столовая гора'),
    }

def greatwall():
    b=Builder('great_wall');foundation(b,8,5.6)
    for x,y,rx,ry,h,s in [(-2,.5,2,1.8,1.2,3),(.1,.8,2,2,1.9,6),(2.3,.6,1.6,1.8,1.25,9)]:rock(b,x,y,.24,rx,ry,h,'jade',s)
    points=[(-3.4,-.85,1.15),(-2.5,-.8,1.4),(-1.6,-.3,1.75),(-.7,.5,2.05),(.2,.6,2.2),(1.1,.1,1.95),(2,-.4,1.65),(3.1,-.15,1.3)]
    for j,(p,q) in enumerate(zip(points,points[1:])):
        x,y,z=p;xx,yy,zz=q;dx,dy=xx-x,yy-y;length=sqrt(dx*dx+dy*dy);a=math.atan2(dy,dx)
        b.box(((x+xx)/2,(y+yy)/2,(z+zz)/2-.13),(length+.12,.83,.27),'stone',a)
        for side in [-1,1]:
            nx,ny=-sin(a)*side*.40,cos(a)*side*.40
            b.box(((x+xx)/2+nx,(y+yy)/2+ny,(z+zz)/2+.18),(length+.13,.12,.50),'ivory',a)
            for k in range(5):
                t=k/4;b.box((x+(xx-x)*t+nx,y+(yy-y)*t+ny,z+(zz-z)*t+.50),(.14,.17,.22),'stone',a)
    for idx in [1,4,6]:
        x,y,z=points[idx];b.box((x,y,z+.65),(1.0,1.0,1.3),'stone')
        portal(b,x,y-.51,z+.15,.38,.65,'ivory','stone')
        b.box((x,y,z+1.35),(1.17,1.17,.12),'ivory');b.pyramid((x,y,z+1.42),1.35,1.35,.55,'roof',top=.20)
        for s in [-1,1]:b.box((x+s*.43,y-.51,z+.85),(.12,.04,.24),'ink')
    return b

def taj():
    b=Builder('taj_mahal');foundation(b,7.0,6.8)
    b.box((0,0,.44),(6.6,6.35,.40),'ivory');b.box((0,.55,1.90),(3.0,3.0,2.5),'ivory')
    b.box((0,.55,3.20),(3.2,3.2,.16),'stone')
    for x in [-.98,0,.98]:portal(b,x,-.98,.76,.57 if x else 1.04,1.37 if x else 2.05,'ivory','stone')
    for a in [pi/2,pi,3*pi/2]:
        for offset in [-.87,0,.87]:
            xx=offset*cos(a)+1.51*sin(a);yy=.55+offset*sin(a)-1.51*cos(a)
            b.box((xx,yy,1.72),(.42,.04,1.13),'stone',a)
            b.box((xx,yy-.012,1.70),(.30,.06,.94),'ink',a)
    b.lathe([(3.28,1.02),(3.61,1.02)],'ivory',pos=(0,.55,0),n=40);dome(b,0,.55,3.60,1.15,1.48,'ivory',True)
    for x in [-1.11,1.11]:
        for y in [-.55,1.66]:
            for a in [0,pi/2,pi,3*pi/2]:column(b,x+.24*cos(a),y+.24*sin(a),3.24,.52,.04,'ivory')
            dome(b,x,y,3.78,.36,.43,'ivory',True)
    for x in [-2.65,2.65]:
        for y in [-2.1,2.65]:
            b.lathe([(.65,.28),(.84,.28),(4.36,.18)],'ivory',pos=(x,y,0),n=20)
            for z,r in [(1.85,.27),(3.05,.24),(4.30,.26)]:
                b.lathe([(z,r),(z+.1,r)],'stone',pos=(x,y,0),n=24)
                for i in range(12):
                    a=i*pi/6;b.beam((x+r*cos(a),y+r*sin(a),z+.1),(x+r*cos(a),y+r*sin(a),z+.23),.012,'ivory',n=4)
            dome(b,x,y,4.44,.26,.37,'ivory',True)
    b.box((0,-2.07,.665),(.66,1.35,.025),'glass')
    for x in [-.65,.65]:
        for y in [-1.60,-2.1,-2.60]:b.lathe([(.67,.13),(1.15,.025)],'roof',pos=(x,y,0),n=10)
    return b

def loft_box(b,sections,mat):
    vs=[(x+sx*w/2,y+sy*d/2,z) for x,y,z,w,d in sections for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    fs=[(j*4+i,j*4+(i+1)%4,(j+1)*4+(i+1)%4,(j+1)*4+i) for j in range(len(sections)-1) for i in range(4)]
    fs += [(0,3,2,1),tuple((len(sections)-1)*4+i for i in range(4))];b.add(vs,fs,mat)

def marina():
    b=Builder('marina_bay');foundation(b,7.7,3.5)
    for x in [-2.18,0,2.18]:
        sections=[(x+.22*sin(t*pi),0,.24+t*5.3,1.20,.98+.28*(1-t)) for t in [i/10 for i in range(11)]]
        loft_box(b,sections,'glass')
        for k in range(27):
            t=k/26;xx=x+.22*sin(t*pi);z=.30+t*5.22;b.box((xx,0,z),(1.24,1.03+.28*(1-t),.035),'silver')
        for side in [-1,1]:
            b.path([(xx+side*w/2,-d/2-.012,z) for xx,yy,z,w,d in sections],.047,'ivory',n=6)
    # Boat-shaped sky park, with pointed bow and overhanging stern.
    profile=[(-3.65,0),(-3.1,-.67),(2.85,-.67),(3.85,-.08),(3.4,.50),(-2.9,.62)]
    vs=[(x*(.94 if j==0 else 1),y*(.82 if j==0 else 1),5.48+j*.35) for j in range(2) for x,y in profile]
    n=len(profile);b.add(vs,[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],'ivory')
    b.box((0,-.17,5.86),(5.80,.55,.055),'glass')
    for x in [-2.6,-1.9,-1.2,-.5,.2,.9,1.6,2.3]:
        b.beam((x,.40,5.86),(x,.40,6.12),.025,'bronze',n=6);b.ellipsoid((x,.40,6.19),(.16,.15,.20),'roof',n=10,rings=8)
    for y in [-.65,.61]:b.beam((-2.95,y,5.98),(2.85,y,5.98),.017,'silver',n=4)
    return b

def petronas():
    b=Builder('petronas');foundation(b,5.2,3.9)
    for x in [-1.25,1.25]:
        for j in range(27):
            z=.25+j*.215;r=.67 if j<14 else .67-(j-13)*.026
            n=16;vs=[(x+r*(1 if i%2==0 else .84)*cos(i*pi/8),r*(1 if i%2==0 else .84)*sin(i*pi/8),zz) for zz in [z,z+.21] for i in range(n)]
            b.add(vs,[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],'glass')
            b.lathe([(z+.18,r*1.04),(z+.22,r*1.04)],'silver',pos=(x,0,0),n=16)
        for i in range(8):
            a=i*pi/4;b.beam((x+.67*cos(a),.67*sin(a),.3),(x+.67*cos(a),.67*sin(a),3.2),.018,'silver',n=4)
        b.lathe([(6.1,.30),(6.3,.30),(6.45,.20),(6.7,.16),(6.85,.08)],'silver',pos=(x,0,0),n=24)
        b.beam((x,0,6.85),(x,0,7.65),.037,'silver',r2=.006,n=10)
    b.box((0,0,3.33),(2.1,.38,.34),'silver');b.box((0,-.205,3.35),(2.05,.018,.17),'glass')
    for s in [-1,1]:b.beam((s*1.22,0,2.1),(s*.27,0,3.18),.06,'silver')
    return b

def fuji():
    b=Builder('fuji');foundation(b,7.6,6.0);b.box((0,0,.29),(7.4,5.8,.12),'mint')
    volcano(b,0,.45,.35,3.0,4.35,True,1)
    b.box((0,-2.15,.37),(6.2,.72,.08),'glass')
    for x in [-2.9,-2.45,2.45,2.9]:
        b.beam((x,-1.95,.4),(x,-1.95,1.1),.045,'bronze')
        for z,r in [(.7,.28),(.9,.23),(1.08,.16)]:b.lathe([(z,r),(z+.42,.0)],'roof',pos=(x,-1.95,0),n=9)
    return b

def bali():
    b=Builder('bali_temple');foundation(b,5.7,4.9);b.box((0,0,.28),(5.5,4.7,.12),'glass')
    b.box((-.35,.15,.55),(2.8,2.8,.45),'stone');b.box((-.35,.15,1.03),(2.1,2.1,.55),'bronze')
    for j in range(9):
        z=1.4+j*.48;w=3.35-j*.29
        b.box((-.35,.15,z+.06),(w*.45,w*.45,.28),'brick')
        b.pyramid((-.35,.15,z+.16),w,w,.38,'roof',top=w*.32)
        b.box((-.35,.15,z+.14),(w*1.02,w*1.02,.07),'ink')
        for s in [-1,1]:b.beam((-.35+s*w/2,.15-w/2,z+.17),(-.35+s*(w/2+.08),.15-w/2-.08,z+.28),.022,'gold',n=4)
    b.beam((-.35,.15,5.72),(-.35,.15,6.18),.03,'gold')
    for x in [1.65,2.35]:
        b.box((x,-1.1,1.1),(.44,.68,1.5),'stone')
        for j in range(4):b.box((x,-1.1,1.85+j*.15),(.50-j*.07,.74-j*.07,.12),'stone')
    for i in range(4):b.box((-.35,-1.5-i*.16,.74-i*.10),(1.3,.45,.12),'ivory')
    return b

def palm(b,x,y,z,h):
    b.path([(x+.16*sin(t*pi),y,z+t*h) for t in [i/8 for i in range(9)]],.06,'bronze',n=8)
    for i in range(9):
        a=i*2*pi/9;pts=[]
        for j in range(7):
            t=j/6;length=.95*t;zz=z+h+.25*sin(t*pi)-.30*t;cx=x+length*cos(a);cy=y+length*sin(a);w=.16*sin(t*pi)
            pts.extend([(cx-w*sin(a),cy+w*cos(a),zz),(cx+w*sin(a),cy-w*cos(a),zz)])
        b.add(pts,[(2*j,2*j+1,2*j+3,2*j+2) for j in range(6)],'roof')

def maldives():
    b=Builder('maldives');foundation(b,7.5,5.9);b.box((0,0,.29),(7.3,5.7,.13),'glass')
    b.lathe([(.36,1.4),(.46,1.15)],'sand',pos=(-2,.4,0),n=32,sx=.85,sy=1.3)
    palm(b,-2.1,.55,.48,2.6);palm(b,-2.45,-.35,.48,2.15)
    b.box((.40,-.5,.69),(4.2,.45,.14),'bronze')
    for x in [-1.5+i*.22 for i in range(19)]:b.box((x,-.5,.78),(.16,.48,.04),'stone')
    for x,y in [(.25,.60),(2.25,.60)]:
        for sx in [-1,1]:
            for sy in [-1,1]:b.beam((x+sx*.7,y+sy*.65,.32),(x+sx*.7,y+sy*.65,1.4),.06,'bronze',n=8)
        b.box((x,y,.89),(1.8,1.7,.19),'bronze');b.box((x,y,1.50),(1.35,1.2,1.03),'stone')
        b.box((x,y-.61,1.50),(.85,.04,.82),'glass');b.box((x,y-.65,1.50),(.045,.05,.82),'bronze')
        b.pyramid((x,y,2.05),1.9,1.75,.95,'bronze',top=.15)
        for j in range(7):
            w=1.9*(1-j/9);b.box((x,y-.875*(1-j/9),2.07+j*.10),(w,.028,.027),'sand')
    return b

def christ():
    b=Builder('christ');foundation(b,5.8,4.7);rock(b,0,0,.24,2.5,1.9,1.7,'roof',4)
    for z,w,h in [(1.45,2.1,.35),(1.76,1.65,.28),(2.0,1.36,.25)]:b.box((0,0,z),(w,w,h),'stone')
    n=48;layers=16;vs=[]
    for j in range(layers):
        t=j/(layers-1);r=.58-.13*t
        for i in range(n):
            a=i*2*pi/n;f=1+.075*sin(a*13+1.2*t);vs.append((r*cos(a)*f,.34*sin(a)*f,2.16+2.76*t))
    b.add(vs,[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(layers-1) for i in range(n)],'ivory',True)
    for side in [-1,1]:
        b.beam((side*.34,0,4.74),(side*1.9,0,4.74),.26,'ivory',r2=.15,n=16)
        b.ellipsoid((side*2.02,-.02,4.76),(.20,.12,.12),'ivory',n=16,rings=10)
        for j in range(4):b.beam((side*2.01,-.09+j*.055,4.77),(side*2.25,-.09+j*.055,4.77),.025,'ivory',n=6)
        b.path([(side*.25,-.32,4.7),(side*.7,-.20,4.65),(side*1.55,-.16,4.64)],.018,'stone',n=4)
    b.beam((0,0,4.9),(0,0,5.24),.16,'ivory',n=16)
    b.ellipsoid((0,-.025,5.53),(.27,.25,.39),'ivory');b.ellipsoid((0,.15,5.52),(.28,.16,.34),'stone')
    b.add([(-.05,-.26,5.62),(.05,-.26,5.62),(0,-.34,5.46),(-.055,-.25,5.43),(.055,-.25,5.43)],[(0,1,2),(0,2,3),(1,4,2),(2,4,3)],'ivory')
    for x in [-.11,.11]:b.beam((x-.055,-.26,5.61),(x+.055,-.26,5.61),.012,'stone',n=4)
    return b

def chichen():
    b=Builder('chichen_itza');foundation(b,7.6,7.2)
    for j in range(9):
        w=6.7-j*.48;z=.25+j*.34
        b.pyramid((0,0,z),w,w,.30,'stone',top=w-.22);b.box((0,0,z+.29),(w-.12,w-.12,.07),'ivory')
    b.box((0,0,3.70),(2.15,1.86,.92),'stone');b.box((0,0,4.22),(2.4,2.1,.15),'ivory')
    for y in [-.95,.95]:
        for x in [-.66,0,.66]:b.box((x,y,3.68),(.39,.04,.65),'ink')
    for a in [0,pi/2,pi,3*pi/2]:
        for j in range(27):
            y=-3.4+j*.09;z=.3+j*.112
            b.box((-y*sin(a),y*cos(a),z),(.88,.16,.13),'ivory',a)
        for x in [-.52,.52]:b.beam((x*cos(a)+3.4*sin(a),x*sin(a)-3.4*cos(a),.4),(x*cos(a)+.98*sin(a),x*sin(a)-.98*cos(a),3.48),.09,'stone',n=4)
    return b

def sail(b,cx,cy,z,length,width,h,flip=1):
    # Double-curved vaulted shell. Each rib converges on the high apex.
    u_count,v_count=18,16;vs=[]
    for j in range(u_count+1):
        t=j/u_count;x=cx+flip*length*(t-.5);ridge=z+h*(t**.78)
        for k in range(v_count+1):
            u=-1+2*k/v_count;y=cy+width*.5*u*(sin(pi*t)**.48)
            zz=z+(ridge-z)*(cos(u*pi/2)**.62)
            vs.append((x,y,zz))
    faces=[(j*(v_count+1)+k,j*(v_count+1)+k+1,(j+1)*(v_count+1)+k+1,(j+1)*(v_count+1)+k) for j in range(u_count) for k in range(v_count)]
    b.add(vs,faces,'ivory',True)
    for k in range(0,v_count+1,2):b.path([vs[j*(v_count+1)+k] for j in range(u_count+1)],.015,'stone',n=4)
    # Dark glass arch under each shell's broad front.
    b.box((cx,cy,z+.18),(length*.70,width*.65,.35),'ink')

def opera():
    b=Builder('opera');foundation(b,7.6,6.3);b.box((0,0,.29),(7.4,6.1,.12),'glass')
    b.box((0,0,.52),(6.7,5.2,.38),'bronze')
    for j in range(6):b.box((0,-2.76+j*.17,.35+j*.08),(5.0,.38,.12),'stone')
    for y in [-.95,.95]:
        for x,length,w,h in [(-1.7,2.7,1.7,1.6),(-.3,3.2,2.0,2.9),(1.45,2.9,2.0,3.8)]:sail(b,x,y,.72,length,w,h)
    sail(b,-2.25,0,.72,1.5,1.3,1.35,-1)
    return b

def tablemountain():
    b=Builder('table_mountain');foundation(b,7.8,5.9);b.box((0,0,.29),(7.6,5.7,.12),'mint')
    n=36;vs=[]
    for k,(z,rx,ry) in enumerate([(.34,3.4,2.2),(1.1,3.1,1.9),(2.5,2.75,1.55),(3.55,2.65,1.32)]):
        for i in range(n):
            a=i*2*pi/n;wav=1+.06*sin(i*3.9)+.035*cos(i*1.7);vs.append((rx*cos(a)*wav,ry*sin(a)*wav,z+(.05*sin(i*3) if k==3 else .12*sin(i*2.1))))
    for k in range(3):
        for i in range(n):b.add([vs[k*n+i],vs[k*n+(i+1)%n],vs[(k+1)*n+(i+1)%n],vs[(k+1)*n+i]],[(0,1,2),(0,2,3)],'stone' if k else 'roof')
    b.add(vs[3*n:],[tuple(range(n))],'mint')
    for i in range(n):
        a=i*2*pi/n
        b.path([(rx*cos(a)*(1+.06*sin(i*3.9)+.035*cos(i*1.7)),ry*sin(a)*(1+.06*sin(i*3.9)+.035*cos(i*1.7)),z) for z,rx,ry in [(1.12,3.1,1.9),(2.5,2.75,1.55),(3.52,2.65,1.32)]],.018,'bronze',n=4)
    # Cable station and descending cable make the characteristic plateau legible.
    b.box((-2.2,-.5,3.72),(.54,.45,.27),'ivory')
    b.beam((-2.2,-.55,3.75),(-3.35,-2.4,.75),.015,'ink',n=4)
    b.box((-2.82,-1.6,1.97),(.22,.22,.25),'brick')
    return b
