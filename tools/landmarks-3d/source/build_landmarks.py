"""Original stylized landmark sculptures for О!дин запрос.
Run: blender --background --factory-startup --python build_landmarks.py
Creates GLB meshes, editable .blend and individual studio PNGs. No paid assets.
Geometry uses Blender Z up; glTF exporter converts to standard Y up.
"""
import bpy, bmesh, math, json, sys
from pathlib import Path
from mathutils import Vector
from math import sin, cos, pi, sqrt

ROOT = Path(__file__).resolve().parents[1]
for folder in ['models', 'previews']:
    (ROOT / folder).mkdir(exist_ok=True)
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ONLY = next((s.split('=')[1] for s in ARGS if s.startswith('only=')), None)
NO_RENDER = 'no-render' in ARGS
# This script is intentionally executed in a new --factory-startup process.
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
COLORS = {
    'ivory': '#ede5d5', 'stone': '#cbb894', 'bronze': '#9d7554',
    'gold': '#d3a653', 'brick': '#ad5142', 'red': '#c34535',
    'jade': '#70a99b', 'roof': '#385f5d', 'glass': '#77aebb',
    'silver': '#b7d0d1', 'ink': '#243c43', 'sand': '#d3ad71',
    'mint': '#b1c6af', 'blue': '#3358bd', 'basalt':'#657773',
}
def linear(x):
    return x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4
MATS = {}
for name, value in COLORS.items():
    c = tuple(linear(int(value[i:i+2],16)/255) for i in (1,3,5)) + (1,)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = c
    n = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    n.inputs['Base Color'].default_value = c
    n.inputs['Roughness'].default_value = .60 if name not in ['gold','glass','silver'] else .38
    n.inputs['Metallic'].default_value = .25 if name in ['gold','bronze','silver'] else .04
    MATS[name] = m

class Builder:
    def __init__(self, name):
        self.name, self.parts = name, {}
    def add(self, verts, faces, mat, smooth=False):
        v, f, s = self.parts.setdefault(mat, ([],[],[]))
        start = len(v)
        v.extend(verts); f.extend(tuple(start+i for i in face) for face in faces)
        s.extend(smooth if isinstance(smooth,list) else [smooth]*len(faces))
    def box(self, pos, dims, mat='ivory', angle=0):
        x,y,z = pos; a,b,c = [d/2 for d in dims]
        vs = [(u,v,w) for w in [-c,c] for v in [-b,b] for u in [-a,a]]
        vs = [(x+u*cos(angle)-v*sin(angle),y+u*sin(angle)+v*cos(angle),z+w) for u,v,w in vs]
        self.add(vs, [(0,2,3,1),(4,5,7,6),(0,1,5,4),(1,3,7,5),(3,2,6,7),(2,0,4,6)],mat)
    def beam(self, a, b, radius, mat='bronze', r2=None, n=8):
        a,b = Vector(a),Vector(b); axis=(b-a).normalized()
        seed=Vector((0,0,1)) if abs(axis.z)<.9 else Vector((1,0,0))
        u=axis.cross(seed).normalized(); v=axis.cross(u)
        rr=radius if r2 is None else r2
        vs=[tuple(p+r*(cos(i*2*pi/n)*u+sin(i*2*pi/n)*v)) for p,r in [(a,radius),(b,rr)] for i in range(n)]
        fs=[tuple(reversed(range(n))),tuple(range(n,2*n))]
        fs += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        self.add(vs,fs,mat,[False,False]+[True]*n)
    def path(self, points, radius, mat='bronze', n=8):
        for a,b in zip(points,points[1:]): self.beam(a,b,radius,mat,n=n)
    def lathe(self, profile, mat='ivory', pos=(0,0,0), n=32, sx=1, sy=1, smooth=True):
        vs=[(pos[0]+r*cos(i*2*pi/n)*sx,pos[1]+r*sin(i*2*pi/n)*sy,pos[2]+z) for z,r in profile for i in range(n)]
        fs=[]
        for k in range(len(profile)-1):
            fs.extend((k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i) for i in range(n))
        fs += [tuple(reversed(range(n))),tuple((len(profile)-1)*n+i for i in range(n))]
        self.add(vs,fs,mat,[smooth]*(len(fs)-2)+[False,False])
    def ring(self, rx, ry, z, thickness, h, mat='stone', start=0, end=2*pi, n=64):
        vs=[]
        for dz in [0,h]:
            for r in [0,thickness]:
                vs.extend(((rx-r)*cos(start+(end-start)*i/n),(ry-r)*sin(start+(end-start)*i/n),z+dz) for i in range(n+1))
        m=n+1; fs=[]
        for i in range(n):
            fs.extend([(i,i+1,2*m+i+1,2*m+i),(m+i,3*m+i,3*m+i+1,m+i+1),
                       (i,m+i,m+i+1,i+1),(2*m+i,2*m+i+1,3*m+i+1,3*m+i)])
        fs.extend([(0,2*m,3*m,m),(n,m+n,3*m+n,2*m+n)])
        self.add(vs,fs,mat)
    def arch(self, cx, cy, z, width, spring, thick, depth, mat='stone', angle=0, steps=12):
        # True opening: pillars plus an annular semicircle, open through its depth.
        r=width/2
        for x in [-r-thick/2,r+thick/2]:
            self.box((cx+x*cos(angle),cy+x*sin(angle),z+spring/2),(thick,depth,spring),mat,angle)
        vs=[]
        for y in [-depth/2,depth/2]:
            for radius in [r,r+thick]:
                for i in range(steps+1):
                    t=i*pi/steps; x=radius*cos(t)
                    vs.append((cx+x*cos(angle)-y*sin(angle),cy+x*sin(angle)+y*cos(angle),z+spring+radius*sin(t)))
        m=steps+1;fs=[]
        for i in range(steps):
            fs.extend([(i,i+1,m+i+1,m+i),(2*m+i,3*m+i,3*m+i+1,2*m+i+1),
                       (i,2*m+i,2*m+i+1,i+1),(m+i,m+i+1,3*m+i+1,3*m+i)])
        fs += [(0,m,3*m,2*m),(steps,2*m-1,4*m-1,3*m-1)]
        self.add(vs,fs,mat)
    def ellipsoid(self, pos, scale, mat='jade', n=24, rings=14):
        vs=[(pos[0]+scale[0]*sin(pi*j/rings)*cos(2*pi*i/n),pos[1]+scale[1]*sin(pi*j/rings)*sin(2*pi*i/n),pos[2]+scale[2]*cos(pi*j/rings)) for j in range(rings+1) for i in range(n)]
        fs=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(rings) for i in range(n)]
        self.add(vs,fs,mat,True)
    def pyramid(self, pos, w, d, h, mat='roof', top=.001):
        x,y,z=pos
        vs=[(x+sx*a/2,y+sy*b/2,z+zz) for a,b,zz in [(w,d,0),(top,top,h)] for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        self.add(vs,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat)
    def finish(self):
        coll=bpy.data.collections.new(self.name);scene.collection.children.link(coll)
        objs=[]
        for mat,(verts,faces,smooth) in self.parts.items():
            mesh=bpy.data.meshes.new(self.name+'_'+mat);mesh.from_pydata(verts,[],faces);mesh.update()
            bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
            for poly,flag in zip(mesh.polygons,smooth): poly.use_smooth=flag
            obj=bpy.data.objects.new(self.name+'_'+mat,mesh);coll.objects.link(obj);obj.data.materials.append(MATS[mat])
            if mat in ['ivory','stone','brick','sand'] and self.name not in ['colosseum','isaac','kulsharif','parthenon','belem','taj_mahal','opera']:
                bevel=obj.modifiers.new('Soft architectural edges','BEVEL');bevel.width=.018;bevel.segments=2
                bevel.limit_method='ANGLE';bevel.angle_limit=.65
                bpy.context.view_layer.objects.active=obj;obj.select_set(True)
                bpy.ops.object.modifier_apply(modifier=bevel.name);obj.select_set(False)
            objs.append(obj)
        return coll,objs

def foundation(b,w,d):
    b.box((0,0,.08),(w,d,.16),'stone')
    b.box((0,0,.19),(w-.08,d-.08,.10),'ivory')

def dial(b,center,r,angle=0):
    # Clock lies in local X/Z plane, the front normal is -Y.
    x,y,z=center
    def at(u,v,w=0): return (x+u*cos(angle)-w*sin(angle),y+u*sin(angle)+w*cos(angle),z+v)
    for radius,depth,mat in [(r+.055,.04,'gold'),(r,.055,'ink'),(r*.86,.065,'ivory')]:
        b.beam(at(0,0,-depth),at(0,0,depth),radius,mat,n=48)
    for i in range(12):
        t=i*pi/6;rad=r*.72
        b.beam(at(sin(t)*rad,cos(t)*rad,-.07),at(sin(t)*(rad+.065),cos(t)*(rad+.065),-.07),.014,'ink',n=5)
    for t,length in [(pi*.6,r*.63),(-pi*.1,r*.45)]:
        b.beam(at(0,0,-.09),at(sin(t)*length,cos(t)*length,-.09),.022,'ink',n=6)
    b.ellipsoid(at(0,0,-.105),(.045,.025,.045),'gold',n=12,rings=8)

def eiffel():
    b=Builder('tower');foundation(b,4.6,4.6)
    for x in [-1,1]:
        for y in [-1,1]: b.box((x*1.62,y*1.62,.35),(.68,.68,.22),'stone')
    levels=[(.46,1.62),(1.2,1.43),(1.95,1.06),(2.95,.60),(3.5,.46),(4.25,.34),(4.95,.25),(5.65,.18),(6.65,.13)]
    for x in [-1,1]:
        for y in [-1,1]:
            for (z,a),(zz,aa) in zip(levels,levels[1:]): b.beam((x*a,y*a,z),(x*aa,y*aa,zz),.075 if z<3 else .052,'bronze',n=6)
    for k,((z,a),(zz,aa)) in enumerate(zip(levels,levels[1:])):
        for axis in [0,1]:
            for s in [-1,1]:
                def p(x,y,z): return (x,y,z) if axis==0 else (y,x,z)
                # Lower openings remain open; crossed lattice begins above the arch.
                if k>=2:
                    b.beam(p(-a,s*a,z),p(aa,s*aa,zz),.027,'bronze',n=5)
                    b.beam(p(a,s*a,z),p(-aa,s*aa,zz),.027,'bronze',n=5)
                else:
                    for sign in [-1,1]:
                        b.beam(p(sign*(a-.15),s*a,z),p(sign*(aa+.1),s*aa,zz),.035,'bronze',n=5)
                if k>1: b.beam(p(-a,s*a,z),p(a,s*a,z),.043,'bronze',n=6)
    for axis in [0,1]:
        for s in [-1,1]:
            pts=[]
            for i in range(21):
                t=pi*i/20; u=1.44*cos(t);z=.65+1.12*sin(t)
                pts.append((u,s*1.3,z) if axis==0 else (s*1.3,u,z))
            b.path(pts,.068,'bronze')
            for i in range(1,10):
                u=-1.30+i*.26;z=.65+1.12*sqrt(max(0,1-(u/1.44)**2))
                p=(u,s*1.3,z) if axis==0 else (s*1.3,u,z)
                q=(u,s*1.03,1.95) if axis==0 else (s*1.03,u,1.95)
                b.beam(p,q,.024,'bronze',n=5)
    for z,w in [(1.95,2.55),(2.95,1.52),(6.65,.57)]:
        b.box((0,0,z),(w,w,.13),'bronze')
        b.box((0,0,z+.1),(w+.04,w+.04,.065),'gold')
        for axis in [0,1]:
            for s in [-1,1]:
                def p(u,z): return (u,s*w/2,z) if axis==0 else (s*w/2,u,z)
                b.beam(p(-w/2,z+.28),p(w/2,z+.28),.022,'bronze',n=5)
                for i in range(9):b.beam(p(-w/2+w*i/8,z+.13),p(-w/2+w*i/8,z+.28),.014,'bronze',n=4)
    b.box((0,0,6.84),(.38,.38,.28),'bronze')
    b.pyramid((0,0,6.98),.45,.45,.26,'bronze')
    b.beam((0,0,7.24),(0,0,7.85),.035,'gold',r2=.012)
    return b

def kremlin():
    b=Builder('kremlin');foundation(b,5.6,2.6)
    for x in [-1.78,1.78]:
        b.box((x,0,.99),(1.95,.58,1.5),'brick')
        b.box((x,0,1.76),(2.04,.7,.14),'ivory')
        for j in range(6):
            xx=x-.81+j*.32
            b.box((xx,0,1.96),(.22,.64,.34),'brick')
            for sx in [-1,1]:b.box((xx+sx*.075,0,2.17),(.07,.64,.15),'brick')
        for j in range(6):b.box((x-.82+j*.33,-.299,1.12),(.03,.035,.75),'stone')
    b.box((0,0,2.05),(1.65,1.4,3.62),'brick')
    for z,w in [(1.85,1.72),(3.6,1.82),(3.91,1.9),(4.15,1.68),(5.12,1.42)]: b.box((0,0,z),(w,w*.87,.12),'ivory')
    b.arch(0,-.72,.25,.72,1.1,.12,.06,'ivory')
    b.box((0,-.72,.92),(.68,.08,1.30),'ink')
    for x in [-.69,.69]:
        b.box((x,-.72,2.3),(.14,.09,2.65),'ivory')
        for z in [2.4,2.9,3.4]: b.box((x*.60,-.725,z),(.15,.06,.24),'ink')
    b.box((0,0,4.54),(1.48,1.28,1.15),'brick')
    for a in [0,pi/2,pi,3*pi/2]:dial(b,(-sin(a)*.75,-cos(a)*.75,4.56),.42,-a)
    b.box((0,0,5.35),(1.16,1.04,.40),'ivory')
    for x in [-.40,0,.4]:b.arch(x,-.54,5.20,.21,.22,.045,.06,'brick',steps=8)
    b.pyramid((0,0,5.55),1.4,1.4,1.90,'roof',top=.23)
    for s in [-1,1]:
        for t in [-1,1]:
            b.beam((s*.7,t*.7,5.55),(s*.115,t*.115,7.45),.027,'gold',n=5)
            b.pyramid((s*.65,t*.65,5.23),.24,.24,.60,'roof')
    b.lathe([(7.45,.15),(7.65,.12),(7.73,.04)],'gold',n=16)
    b.beam((0,0,7.65),(0,0,8.12),.025,'gold')
    pts=[(sin(i*pi/5)*(.23 if i%2==0 else .10),-.015,8.13+cos(i*pi/5)*(.23 if i%2==0 else .10)) for i in range(10)]
    b.add(pts,[tuple(range(10))],'red')
    return b

def burj():
    b=Builder('spire');foundation(b,3.7,3.7)
    b.lathe([(.25,1.52),(.38,1.52),(.48,1.38)],'silver',n=48)
    # Buttressed three-wing silhouette with staggered setbacks and rounded ends.
    for j in range(12):
        z=.48+j*.49; r=.66-j*.038; reach=1.02-j*.071
        b.lathe([(z,r),(z+.50,r*.965)],'glass',n=36)
        for k in range(3):
            a=2*pi*k/3; cap=r*.61
            if j>=10 and k>0: continue
            x,y=reach*cos(a),reach*sin(a)
            h=.51-(k*.047 if j%3==k else 0)
            b.lathe([(z,cap),(z+h,cap*.95)],'glass',pos=(x,y,0),n=24)
            b.lathe([(z+h,cap*.95),(z+h+.018,cap*.95)],'silver',pos=(x,y,0),n=24)
            for floor in range(4):
                zz=z+floor*.115
                b.lathe([(zz,cap*1.012),(zz+.025,cap*1.012)],'silver',pos=(x,y,0),n=24)
            for m in range(8):
                t=2*pi*m/8
                b.beam((x+cap*cos(t),y+cap*sin(t),z),(x+cap*.95*cos(t),y+cap*.95*sin(t),z+h),.012,'silver',n=4)
        b.lathe([(z+.46,r*1.015),(z+.49,r*1.015)],'silver',n=36)
    for z,r,h in [(6.36,.22,.48),(6.84,.15,.45),(7.29,.085,.40)]:b.lathe([(z,r),(z+h,r*.8)],'silver',n=24)
    b.beam((0,0,7.6),(0,0,8.55),.035,'silver',r2=.008,n=12)
    return b

def bigben():
    b=Builder('clocktower');foundation(b,2.9,2.9)
    b.box((0,0,.44),(2.0,2.0,.4),'stone')
    b.box((0,0,2.5),(1.48,1.48,3.8),'stone')
    for angle in [0,pi/2,pi,3*pi/2]:
        def pos(x,y,z):return (x*cos(angle)-y*sin(angle),x*sin(angle)+y*cos(angle),z)
        for x in [-.62,-.23,.23,.62]: b.box(pos(x,-.78,2.49),(.09,.12,3.72),'ivory',angle)
        for x in [-.43,0,.43]:
            for z in [1.02,2.02,3.02]:
                b.box(pos(x,-.752,z+.2),(.19,.04,.64),'ink',angle)
                b.box(pos(x,-.79,z+.2),(.035,.06,.64),'stone',angle)
        for x in [-.63,.63]:
            b.box(pos(x,-.78,4.83),(.15,.16,1.38),'ivory',angle)
        b.box(pos(0,-.76,4.72),(1.1,.04,1.05),'gold',angle)
        dial(b,pos(0,-.82,4.75),.46,angle)
        for x in [-.4,-.13,.13,.4]:b.arch(*pos(x,-.68,5.51),.15,.35,.045,.07,'ivory',angle,8)
    for z,w,h in [(.7,1.72,.12),(1.55,1.62,.10),(2.55,1.62,.10),(3.55,1.62,.12),(4.12,1.82,.19),(5.34,1.85,.2),(5.55,1.62,.10),(6.12,1.64,.15)]:
        b.box((0,0,z),(w,w,h),'ivory')
    b.box((0,0,4.72),(1.54,1.54,1.1),'stone')
    b.box((0,0,5.8),(1.32,1.32,.5),'roof')
    b.pyramid((0,0,6.2),1.6,1.6,1.28,'roof',top=.58)
    b.box((0,0,7.48),(.65,.65,.12),'gold')
    b.pyramid((0,0,7.55),.62,.62,.78,'roof')
    for z,w in [(6.51,1.25),(6.89,.95),(7.24,.76)]:b.box((0,0,z),(w,w,.05),'gold')
    for x in [-.80,.80]:
        for y in [-.80,.80]:
            b.box((x,y,6.20),(.17,.17,.65),'ivory')
            b.pyramid((x,y,6.52),.22,.22,.56,'roof')
            b.beam((x,y,7.05),(x,y,7.22),.019,'gold',n=6)
    b.beam((0,0,8.3),(0,0,8.64),.027,'gold',r2=.008)
    return b

def colosseum():
    b=Builder('colosseum');foundation(b,7.9,6.4)
    rx,ry=3.65,2.82
    b.ring(rx,ry,.26,.45,.20,'stone',n=80)
    bays=36
    for tier in range(3):
        z=.47+tier*.83
        for i in range(bays):
            # Preserve the iconic broken upper wall and exposed interior.
            if tier==2 and 19<=i<=30: continue
            a=2*pi*i/bays; tangent=math.atan2(ry*cos(a),-rx*sin(a))
            step=sqrt((rx*sin(a))**2+(ry*cos(a))**2)*2*pi/bays
            x,y=rx*cos(a),ry*sin(a)
            b.arch(x,y,z,step*.57,.40,.095,.28,'stone',tangent,10)
            for rr in [.0,-.33]:
                if rr:
                    b.arch((rx+rr)*cos(a),(ry+rr)*sin(a),z,step*.51,.40,.07,.13,'ivory',tangent,8)
            # Engaged columns between each arch.
            aa=a+pi/bays;xx=(rx+.1)*cos(aa);yy=(ry+.1)*sin(aa)
            b.beam((xx,yy,z+.05),(xx,yy,z+.64),.045,'ivory',n=8)
            b.box((xx,yy,z+.68),(.14,.15,.07),'ivory',tangent)
        if tier<2: b.ring(rx+.13,ry+.13,z+.73,.64,.10,'ivory',n=80)
        else:
            for aa,bb in [(0,19*2*pi/bays),(31*2*pi/bays,2*pi)]:
                b.ring(rx+.13,ry+.13,z+.73,.64,.1,'ivory',aa,bb,40)
                b.ring(rx+.04,ry+.04,z+.83,.35,.45,'stone',aa,bb,40)
                b.ring(rx+.10,ry+.10,z+1.26,.49,.09,'ivory',aa,bb,40)
    for i in list(range(0,19))+list(range(31,36)):
        a=2*pi*(i+.5)/bays;t=math.atan2(ry*cos(a),-rx*sin(a))
        b.box(((rx+.045)*cos(a),(ry+.045)*sin(a),3.19),(.13,.06,.19),'ink',t)
    # Concentric seating terraces and an open arena, visible through the ruin.
    b.lathe([(.25,1),(.29,1)],'sand',n=64,sx=2.13,sy=1.34)
    for k in range(7):b.ring(2.15+k*.155,1.38+k*.155,.31+k*.13,.16,.14,'ivory',n=64)
    for a in [pi*.16,pi*.55,pi*.9,pi*1.3,pi*1.65]:
        b.beam((2.2*cos(a),1.45*sin(a),.37),(3.08*cos(a),2.27*sin(a),1.24),.075,'stone',n=4)
    return b

def japanese_roof(b,z,w,d,h):
    # Curved hipped roof with overhanging eaves and rows of glazed tiles.
    rings=[]
    for t in [0,.17,.38,.62,.81,1]:
        rings.append((w*(1-.79*t),d*(1-.86*t),z+h*(t**.65)))
    vs=[(sx*ww/2,sy*dd/2,zz) for ww,dd,zz in rings for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    fs=[(k*4+i,k*4+(i+1)%4,(k+1)*4+(i+1)%4,(k+1)*4+i) for k in range(len(rings)-1) for i in range(4)]
    fs+=[(0,3,2,1),tuple(range(20,24))];b.add(vs,fs,'roof')
    for side in [-1,1]:
        for i in range(31):
            f=-1+i/15
            pts=[(f*ww/2,side*dd/2,zz+.025) for ww,dd,zz in rings]
            b.path(pts,.022,'ink',n=5)
        pts=[(-w/2,side*d/2,z+.06),(0,side*d/2,z-.06),(w/2,side*d/2,z+.06)]
        b.path(pts,.075,'ink',n=8)
    b.beam((-w*.11,0,z+h+.08),(w*.11,0,z+h+.08),.095,'ink',n=12)
    for s in [-1,1]:b.beam((s*w*.11,0,z+h+.08),(s*w*.15,0,z+h+.23),.07,'ink')

def kaminarimon():
    b=Builder('gate');foundation(b,6.7,3.65)
    b.box((0,0,.36),(5.85,2.8,.24),'stone')
    for x in [-2.35,-1.22,1.22,2.35]:
        for y in [-.78,.78]:
            b.lathe([(.48,.24),(.64,.24),(.68,.19),(3.18,.19),(3.27,.24)],'red',pos=(x,y,0),n=20)
            b.lathe([(.46,.27),(.61,.27)],'ink',pos=(x,y,0),n=20)
            b.box((x,y,3.3),(.65,.5,.17),'red')
            b.box((x,y,3.53),(.82,.55,.15),'ivory')
    for x in [-1.78,1.78]:
        b.box((x,.1,1.81),(.93,1.45,2.25),'ink')
        for i in range(7):b.box((x-.42+i*.14,-.665,1.82),(.032,.035,2.17),'bronze')
        for zz in [.83,1.3,1.78,2.26,2.75]:b.box((x,-.69,zz),(.95,.045,.032),'bronze')
        b.box((x,-.65,.64),(1.13,.25,.20),'red')
    for y in [-.83,.83]:
        b.box((0,y,3.08),(5.4,.32,.25),'red')
        b.box((0,y,3.62),(5.8,.45,.24),'red')
        for x in [-2.35,-1.22,1.22,2.35]:
            b.box((x,y,3.78),(.5,.68,.12),'ivory')
    b.beam((0,0,3.61),(0,0,3.07),.055,'gold')
    b.lathe([(1.22,.34),(1.30,.48),(1.50,.62),(2.02,.69),(2.56,.61),(2.85,.47),(2.93,.31)],'red',pos=(0,-.10,0),n=48)
    for z,r in [(1.25,.39),(2.91,.34)]:b.lathe([(z-.07,r),(z+.07,r)],'ink',pos=(0,-.1,0),n=32)
    for i in range(24):
        a=2*pi*i/24
        b.path([(r*cos(a),-.1+r*sin(a),z) for z,r in [(1.34,.51),(1.53,.63),(2.02,.7),(2.54,.62),(2.81,.49)]],.012,'brick',n=4)
    b.lathe([(1.08,.20),(1.19,.30),(1.24,.28)],'gold',pos=(0,-.1,0),n=24)
    japanese_roof(b,3.96,6.7,3.6,1.45)
    return b

def pyramids():
    b=Builder('pyramids');foundation(b,8.3,6.7)
    b.box((0,0,.29),(8.15,6.55,.13),'sand')
    for x,y,size,h in [(-1.65,.60,3.75,2.75),(1.60,.45,3.12,2.38),(.78,-2.03,1.48,1.10)]:
        rows=int(h/.10)
        for j in range(rows):
            z=.36+h*j/rows; w=size*(1-j/rows);top=size*(1-(j+1)/rows)
            b.pyramid((x,y,z),w,w,h/rows*.99,'sand' if j%4 else 'stone',top=max(.015,top))
        # Fine masonry joins, staggered on the two prominent faces.
        for j in range(1,rows-1,2):
            z=.36+h*j/rows;ww=size*(1-j/rows)
            for k in range(1,max(2,int(ww/.38))):
                u=-ww/2+k*ww/max(2,int(ww/.38))
                b.beam((x+u,y-ww/2-.006,z),(x+u,y-(ww-size/rows)/2-.006,z+h/rows),.007,'bronze',n=4)
        if h>2.4: b.pyramid((x,y,.36+h*.89),size*.11,size*.11,h*.11,'ivory')
    for x in [-2.85,-2.18,-1.52]:b.pyramid((x,-2.37,.36),.52,.52,.40,'stone')
    return b

def liberty():
    b=Builder('liberty');foundation(b,3.4,3.3)
    for z,w,d,h in [(.39,2.75,2.50,.30),(.68,2.40,2.16,.28),(.96,2.0,1.84,.28),(1.47,1.62,1.55,.76),(1.92,1.88,1.81,.16),(2.10,1.65,1.60,.20)]:
        b.box((0,0,z),(w,d,h),'stone' if z<1.9 else 'ivory')
    for a in [0,pi/2,pi,3*pi/2]:
        for x in [-.45,0,.45]:
            u=x*cos(a)+.795*sin(a);v=x*sin(a)-.795*cos(a)
            b.box((u,v,1.5),(.22,.035,.40),'bronze',a)
    # Sculpted drapery with changing elliptical sections and irregular pleats.
    vs=[];nr=22;ns=48
    for j in range(nr):
        t=j/(nr-1);z=2.24+2.78*t
        rx=.75*(1-t)+.40*t;ry=.43*(1-t)+.32*t
        for i in range(ns):
            a=2*pi*i/ns;fold=1+.12*sin(11*a+1.5*t)+.035*cos(19*a-3*t)
            vs.append((rx*cos(a)*fold+.1*sin(t*pi),ry*sin(a)*fold,z+.055*sin(3*a)*(1-t)))
    fs=[(j*ns+i,j*ns+(i+1)%ns,(j+1)*ns+(i+1)%ns,(j+1)*ns+i) for j in range(nr-1) for i in range(ns)]
    fs+=[tuple(reversed(range(ns))),tuple((nr-1)*ns+i for i in range(ns))];b.add(vs,fs,'jade',True)
    for shift in [0,.13,.26]:
        b.path([(-.46+.90*t,-.34-.055*sin(t*pi),4.69-shift-.8*t) for t in [i/14 for i in range(15)]],.032,'jade')
    b.ellipsoid((-.27,-.22,2.25),(.19,.35,.12),'jade');b.ellipsoid((.29,-.19,2.25),(.19,.33,.12),'jade')
    b.beam((0,0,4.95),(0,0,5.28),.19,'jade',n=20)
    b.ellipsoid((0,-.025,5.55),(.32,.285,.43),'jade')
    b.ellipsoid((0,.20,5.55),(.31,.17,.34),'roof')
    # Face, nose, brow and mouth are actual geometry, no painted billboard.
    b.add([(-.055,-.28,5.64),(.055,-.28,5.64),(0,-.40,5.48),(-.07,-.28,5.45),(.07,-.28,5.45)],[(0,1,2),(0,2,3),(1,4,2),(2,4,3)],'jade')
    for x in [-.13,.13]:
        b.beam((x-.07,-.273,5.66),(x+.07,-.273,5.65),.022,'roof',n=6)
        b.ellipsoid((x,-.28,5.61),(.055,.014,.017),'ink',n=12,rings=6)
    b.beam((-.07,-.29,5.36),(.07,-.29,5.36),.014,'roof',n=6)
    # Seven rays spread on the crown.
    b.lathe([(5.79,.31),(5.91,.32)],'jade',pos=(0,0,0),n=32,sy=.85)
    for i in range(7):
        t=-pi*.48+i*pi*.96/6;u=sin(t);v=cos(t)
        b.beam((u*.26,0,5.78+v*.13),(u*.70,0,5.78+v*.70),.055,'jade',r2=.006,n=8)
    for i in range(7):
        a=pi+pi*(i+1)/8;b.box((.30*cos(a),.26*sin(a),5.84),(.045,.035,.07),'ink',a-pi/2)
    # Raised right arm, bent wrist and modeled hand gripping the torch.
    b.beam((-.35,0,4.86),(-.76,0,5.39),.25,'jade',r2=.17,n=16)
    b.beam((-.76,0,5.39),(-1.13,0,6.37),.17,'jade',r2=.11,n=16)
    b.ellipsoid((-1.13,0,6.38),(.15,.14,.22),'jade')
    for i in range(4):b.beam((-1.21+i*.055,-.1,6.25),(-1.23+i*.055,-.12,6.48),.031,'jade',n=8)
    b.beam((-1.14,0,6.32),(-1.14,0,6.99),.065,'bronze',n=16)
    b.lathe([(6.79,.12),(6.89,.28),(7.03,.31),(7.10,.22)],'gold',pos=(-1.14,0,0),n=24)
    b.lathe([(7.10,.10),(7.23,.21),(7.40,.16),(7.63,.04),(7.77,.001)],'gold',pos=(-1.14,0,0),n=16)
    # Bent left forearm and the tablet tucked against the torso.
    b.beam((.36,0,4.86),(.69,-.02,4.35),.23,'jade',r2=.16,n=16)
    b.beam((.69,-.02,4.35),(.45,-.49,4.48),.16,'jade',r2=.11,n=16)
    b.box((.47,-.43,4.54),(.50,.16,.85),'roof',angle=-.2)
    b.ellipsoid((.52,-.57,4.38),(.16,.095,.14),'jade')
    for z in [4.59,4.68,4.77]:b.box((.46,-.524,z),(.28,.018,.019),'jade',angle=-.2)
    return b

BUILDERS={'tower':eiffel,'kremlin':kremlin,'spire':burj,'clocktower':bigben,'colosseum':colosseum,'gate':kaminarimon,'pyramids':pyramids,'liberty':liberty}
NAMES={'tower':'Эйфелева башня','kremlin':'Московский Кремль · Спасская башня','spire':'Бурдж-Халифа','clocktower':'Биг-Бен','colosseum':'Колизей','gate':'Каминаримон','pyramids':'Пирамиды Гизы','liberty':'Статуя Свободы'}
sys.path.insert(0,str(Path(__file__).resolve().parent))
from extra_landmarks import extend
for _key,(_fn,_name) in extend(globals()).items():
    BUILDERS[_key]=_fn;NAMES[_key]=_name
MODELS={};stats=[]
for key,fn in BUILDERS.items():
    if ONLY and key!=ONLY:continue
    print('BUILD',key,flush=True)
    coll,objs=fn().finish();MODELS[key]=(coll,objs)
    # Kanji inscription is geometry; system font is used for outline generation only.
    if key=='gate':
        font_path=Path('C:/Windows/Fonts/msgothic.ttc')
        if font_path.exists():
            font=bpy.data.fonts.load(str(font_path))
            for char,z in [('雷',2.13),('門',1.67)]:
                curve=bpy.data.curves.new('Lantern inscription','FONT');curve.body=char;curve.font=font;curve.align_x='CENTER';curve.size=.44;curve.extrude=.002
                ob=bpy.data.objects.new('Kaminarimon_'+char,curve);coll.objects.link(ob);ob.location=(0,-.797,z);ob.rotation_euler=(pi/2,0,0);ob.data.materials.append(MATS['ink'])
                bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.convert(target='MESH');ob.select_set(False);objs.append(ob)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:obj.select_set(True)
    bpy.context.view_layer.objects.active=objs[0]
    filepath=ROOT/'models'/f'{key}.glb'
    bpy.ops.export_scene.gltf(filepath=str(filepath),export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_animations=False,export_cameras=False,export_lights=False,export_texcoords=False,export_normals=True,export_draco_mesh_compression_enable=True,export_draco_mesh_compression_level=6)
    triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in objs)
    stats.append({'id':key,'name':NAMES[key],'triangles':triangles,'bytes':filepath.stat().st_size,'objects':len(objs)})
    for o in objs:o.select_set(False);o.hide_render=True
    print('EXPORTED',json.dumps(stats[-1],ensure_ascii=False),flush=True)

if not ONLY:(ROOT/'models'/'manifest.json').write_text(json.dumps({'style':'Architectural miniatures · matte mineral palette','created':'2026-10-29','source':'Original procedural geometry; no marketplace model meshes or textures','models':stats},ensure_ascii=False,indent=2),encoding='utf-8')

# Studio lighting: large warm key, cool fill, rim and softly lit sage paper.
try:scene.render.engine='CYCLES'
except TypeError:pass
if scene.render.engine=='CYCLES':
    scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=720;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.film_transparent=False
world=bpy.data.worlds.new('Soft sage studio');scene.world=world;world.use_nodes=True
wn=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');wn.inputs['Color'].default_value=(.55,.66,.62,1);wn.inputs['Strength'].default_value=.6
try:scene.view_settings.view_transform='AgX'
except TypeError:pass
def area(name,pos,power,size,color):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size;data.color=color
    ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob);ob.location=pos;ob.rotation_euler=(Vector((0,0,2.5))-ob.location).to_track_quat('-Z','Y').to_euler()
area('Key',(-6,-8,13),1600,7,(1,.88,.73));area('Fill',(7,-3,9),1050,8,(.75,.87,1));area('Rim',(1,7,12),1900,6,(1,.96,.86))
floor_mat=bpy.data.materials.new('Studio paper');floor_mat.use_nodes=True
pn=next(n for n in floor_mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');pn.inputs['Base Color'].default_value=(.64,.72,.66,1);pn.inputs['Roughness'].default_value=.95
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.025));floor=bpy.context.object;floor.name='Studio floor';floor.data.materials.append(floor_mat)
cam_data=bpy.data.cameras.new('Camera');cam=bpy.data.objects.new('Camera',cam_data);scene.collection.objects.link(cam);scene.camera=cam;cam_data.type='ORTHO'
for key,(coll,objs) in MODELS.items():
    for o in objs:o.hide_render=False
    coords=[o.matrix_world@Vector(v) for o in objs for v in o.bound_box]
    zmax=max(v.z for v in coords);width=max(max(v.x for v in coords)-min(v.x for v in coords),max(v.y for v in coords)-min(v.y for v in coords))
    target=Vector((0,0,zmax*.44));cam.location=target+Vector((11,-17,11));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam_data.ortho_scale=max(zmax*1.22,width*1.43)
    if key=='colosseum':cam.location=target+Vector((9,-15,15));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    if not NO_RENDER:
        scene.render.filepath=str(ROOT/'previews'/f'{key}.png');print('RENDER',key,flush=True);bpy.ops.render.render(write_still=True)
    for o in objs:o.hide_render=True

# Editable source scene arranged as a gallery (each landmark in its own collection).
for i,(key,(coll,objs)) in enumerate(MODELS.items()):
    for o in objs:o.hide_render=False;o.location.x+=(i%4)*12;o.location.y+=(i//4)*12
scene.render.filepath=''
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'odin-landmarks.blend'))
print('DONE',json.dumps(stats,ensure_ascii=False),flush=True)
