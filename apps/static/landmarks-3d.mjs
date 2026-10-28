/* Small local Three.js models rendered as animated, geographically anchored map markers. */
import * as THREE from './vendor/three/three.module.js';

export function createLandmarkModels({illustrationsOnly=false} = {}) {
  const iron = new THREE.MeshStandardMaterial({color:0x9a8b70, roughness:0.75, metalness:0.2});
  const lightIron = new THREE.MeshStandardMaterial({color:0xd6c8ac, roughness:0.72});
  const red = new THREE.MeshStandardMaterial({color:0xa46553, roughness:0.82});
  const stone = new THREE.MeshStandardMaterial({color:0xe0d8c5, roughness:0.86});
  const gold = new THREE.MeshStandardMaterial({color:0xd0ab6f, roughness:0.65});
  const glass = new THREE.MeshStandardMaterial({color:0x97b6b0, roughness:0.5, metalness:0.35});
  const dark = new THREE.MeshStandardMaterial({color:0x304748, roughness:0.8});
  const jade = new THREE.MeshStandardMaterial({color:0x9fb7a4, roughness:0.8});
  const unitY = new THREE.Vector3(0,1,0);
  function box(group,w,h,d,x,y,z,material) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w,h,d), material);
    mesh.position.set(x,y,z); group.add(mesh); return mesh;
  }
  function beam(group, a, b, radius, material=iron) {
    const from = new THREE.Vector3(...a), to = new THREE.Vector3(...b), delta = to.clone().sub(from);
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,delta.length(),6), material);
    mesh.position.copy(from).add(to).multiplyScalar(.5); mesh.quaternion.setFromUnitVectors(unitY,delta.normalize()); group.add(mesh);
  }
  function eiffel() {
    const group = new THREE.Group();
    const width = (h) => 1.35 - Math.min(h,6.2)/6.2*1.12;
    for (const x of [-1,1]) for (const z of [-1,1]) {
      beam(group,[x*1.35,0,z*1.35],[x*.23,6.2,z*.23],.095);
      for (let h=0;h<6;h+=1) {
        const a=width(h),b=width(h+1);
        beam(group,[x*a,h,z*a],[x*b,h+1,z*b],.035,lightIron);
      }
    }
    for (let h=.8;h<=6;h+=.8) {
      const a=width(h), n=width(Math.min(h+.8,6.2));
      for (const side of [-1,1]) {
        beam(group,[-a,h,side*a],[a,h,side*a],.045);
        beam(group,[side*a,h,-a],[side*a,h,a],.045);
        if (h<5.7) {
          beam(group,[-a,h,side*a],[n,h+.8,side*n],.028,lightIron);
          beam(group,[side*a,h,-a],[side*n,h+.8,n],.028,lightIron);
        }
      }
    }
    box(group,2.75,.18,2.75,0,2.35,0,iron); box(group,1.45,.16,1.45,0,4.65,0,iron);
    box(group,.58,.16,.58,0,6.2,0,iron); beam(group,[0,6.25,0],[0,7.35,0],.06,gold);
    return group;
  }
  function kremlin() {
    // Hand-built Spasskaya-inspired silhouette: this is an illustration of
    // the Kremlin, not a survey model of the whole architectural complex.
    const group=new THREE.Group();
    const brick=new THREE.MeshStandardMaterial({color:0xa65f4d});
    const brickLight=new THREE.MeshStandardMaterial({color:0xbd806b});
    const trim=new THREE.MeshStandardMaterial({color:0xdec8a5});
    const roofMat=new THREE.MeshStandardMaterial({color:0x608b78});
    const clock=new THREE.MeshStandardMaterial({color:0x323e38});
    const starMat=new THREE.MeshStandardMaterial({color:0xb55e4d});
    box(group,5.2,1.05,1.0,0,.525,0,brick);
    for (let x=-2.45;x<=2.45;x+=.42) box(group,.23,.25,1.02,x,1.16,0,brickLight);
    box(group,1.75,3.6,1.55,0,1.8,0,brick);
    box(group,1.93,.17,1.72,0,3.55,0,trim);
    box(group,1.68,1.12,1.48,0,4.12,0,brickLight);
    box(group,1.87,.15,1.66,0,4.72,0,trim);
    for (const side of [0,Math.PI/2,Math.PI,Math.PI*1.5]) {
      const facade=new THREE.Group();facade.rotation.y=side;group.add(facade);
      const face=new THREE.Mesh(new THREE.CircleGeometry(.49,32),clock);
      face.position.set(0,4.12,.76);facade.add(face);
      const ring=new THREE.Mesh(new THREE.RingGeometry(.48,.54,32),gold);
      ring.position.set(0,4.12,.77);facade.add(ring);
      for(let i=0;i<12;i++) {
        const ang=i*Math.PI/6;
        const tick=box(facade,.045,.095,.018,Math.sin(ang)*.38,4.12+Math.cos(ang)*.38,.785,trim);
        tick.rotation.z=-ang;
      }
      box(facade,.05,.3,.018,0,4.22,.8,trim);box(facade,.22,.05,.018,.10,4.12,.8,trim);
      for(const y of [1.45,2.35,3.05]) for(const x of [-.5,.5]) {
        box(facade,.20,.40,.025,x,y,.79,clock);
        box(facade,.25,.06,.035,x,y+.23,.80,trim);
      }
      for(let y=.3;y<3.4;y+=.3) box(facade,1.74,.018,.02,0,y,.786,brickLight);
    }
    box(group,1.50,.2,1.35,0,4.88,0,brick);
    const roof=new THREE.Mesh(new THREE.ConeGeometry(1.16,2.05,4),roofMat);
    roof.rotation.y=Math.PI/4;roof.position.y=6.0;group.add(roof);
    for(const x of [-.74,.74]) for(const z of [-.65,.65]) {
      box(group,.18,.72,.18,x,5.15,z,trim);
      const top=new THREE.Mesh(new THREE.ConeGeometry(.18,.35,4),roofMat);
      top.rotation.y=Math.PI/4;top.position.set(x,5.68,z);group.add(top);
    }
    beam(group,[0,6.98,0],[0,7.36,0],.055,gold);
    const shape=new THREE.Shape();
    for(let i=0;i<10;i++) {
      const angle=Math.PI/2+i*Math.PI/5,r=i%2===0 ? .35 : .15;
      if(i===0) shape.moveTo(Math.cos(angle)*r,Math.sin(angle)*r);
      else shape.lineTo(Math.cos(angle)*r,Math.sin(angle)*r);
    }
    shape.closePath();const star=new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:.09,bevelEnabled:false}),starMat);
    star.position.set(0,7.55,-.045);group.add(star);
    return group;
  }
  function spire() {
    const group = new THREE.Group();
    box(group,2.9,1.2,2.3,0,.6,0,glass); box(group,2.25,1.6,1.8,0,2,0,glass);
    box(group,1.65,1.5,1.4,0,3.55,0,lightIron); box(group,1.1,1.2,1,0,4.9,0,glass);
    box(group,.55,1.1,.55,0,6.05,0,lightIron); beam(group,[0,6.6,0],[0,7.5,0],.06,gold);
    return group;
  }
  function clocktower() {
    const group = new THREE.Group();
    box(group,1.8,5.2,1.8,0,2.6,0,stone); box(group,2,.25,2,0,4.2,0,gold);
    box(group,1.9,1,1.9,0,5.65,0,stone);
    for (const angle of [0,Math.PI/2,Math.PI,Math.PI*1.5]) {
      const face = new THREE.Mesh(new THREE.CircleGeometry(.5,20),new THREE.MeshStandardMaterial({color:0xf6f2e5}));
      face.position.set(Math.sin(angle)*.96,5.65,Math.cos(angle)*.96); face.rotation.y=angle; group.add(face);
    }
    const roof=new THREE.Mesh(new THREE.ConeGeometry(1.38,1.55,4),dark);
    roof.position.y=6.9; roof.rotation.y=Math.PI/4; group.add(roof);
    beam(group,[0,7.65,0],[0,8,0],.055,gold); return group;
  }
  function colosseum() {
    const group = new THREE.Group();
    const base=new THREE.Mesh(new THREE.CylinderGeometry(2.4,2.5,3.4,24),stone);
    base.position.y=1.7; base.scale.z=.76; group.add(base);
    for (const h of [1,2.05]) for (let i=0;i<16;i++) {
      const a=i*Math.PI/8, arch=box(group,.34,.66,.08,Math.sin(a)*2.4,h,Math.cos(a)*1.84,dark);
      arch.rotation.y=a;
    }
    return group;
  }
  function gate() {
    // Kaminarimon-inspired gate: layered curved roof, pillars and lantern.
    const group=new THREE.Group();
    const lacquer=new THREE.MeshStandardMaterial({color:0xb36a56});
    const roofMat=new THREE.MeshStandardMaterial({color:0x405b55});
    const lanternMat=new THREE.MeshStandardMaterial({color:0xc9785b});
    for (const x of [-1.75,1.75]) {
      box(group,.64,3.85,.70,x,1.95,0,lacquer);
      box(group,.83,.28,.85,x,.14,0,stone);
      box(group,.82,.20,.85,x,3.86,0,gold);
    }
    box(group,4.35,.42,.9,0,4.15,0,lacquer);
    box(group,4.60,.13,1.05,0,4.40,0,stone);
    const roofShape=new THREE.Shape();
    roofShape.moveTo(-2.65,4.42);roofShape.quadraticCurveTo(0,4.73,2.65,4.42);
    roofShape.lineTo(2.30,5.08);roofShape.quadraticCurveTo(0,5.40,-2.30,5.08);roofShape.closePath();
    const roof=new THREE.Mesh(new THREE.ExtrudeGeometry(roofShape,{depth:1.06,bevelEnabled:true,bevelSize:.08,bevelThickness:.04,bevelSegments:2}),roofMat);
    roof.position.z=-.53;group.add(roof);
    box(group,3.45,.11,.72,0,5.25,0,gold);
    const lanternShape=[new THREE.Vector2(.25,-.72),new THREE.Vector2(.52,-.55),new THREE.Vector2(.64,-.22),
      new THREE.Vector2(.64,.24),new THREE.Vector2(.50,.58),new THREE.Vector2(.25,.72)];
    const lantern=new THREE.Mesh(new THREE.LatheGeometry(lanternShape,20),lanternMat);lantern.position.set(0,3.13,0);group.add(lantern);
    for(const y of [2.43,3.83]) {const ring=new THREE.Mesh(new THREE.CylinderGeometry(.28,.28,.13,16),dark);ring.position.set(0,y,0);group.add(ring);}
    beam(group,[0,3.9,0],[0,4.2,0],.055,gold);
    for(const x of [-1.1,1.1]) {box(group,.48,1.12,.06,x,2.4,.40,stone);box(group,.38,.85,.08,x,2.4,.45,dark);}
    return group;
  }
  function pyramids() {
    const group=new THREE.Group();
    const sand=new THREE.MeshStandardMaterial({color:0xd2b685});
    const lines=new THREE.MeshStandardMaterial({color:0xe3d1ae});
    for (const [x,z,size] of [[-1.05,0,2.25],[1.35,-.15,1.52],[2.65,.50,.90]]) {
      const h=size*1.30;
      const pyramid=new THREE.Mesh(new THREE.ConeGeometry(size,h,4),sand);
      pyramid.rotation.y=Math.PI/4;pyramid.position.set(x,h/2,z);group.add(pyramid);
      for (const f of [.27,.52,.75]) {
        const radius=size*Math.SQRT1_2*(1-f)*1.012,y=h*f;
        for (const side of [-1,1]) {
          beam(group,[x-radius,y,z+side*radius],[x+radius,y,z+side*radius],.018,lines);
          beam(group,[x+side*radius,y,z-radius],[x+side*radius,y,z+radius],.018,lines);
        }
      }
    }
    return group;
  }
  function liberty() {
    const group = new THREE.Group();
    box(group,2.3,1.5,2.3,0,.75,0,stone); box(group,1.7,.35,1.7,0,1.65,0,gold);
    const body=new THREE.Mesh(new THREE.ConeGeometry(.75,3.2,7),jade); body.position.y=3.35; group.add(body);
    const head=new THREE.Mesh(new THREE.SphereGeometry(.45,10,8),jade); head.position.y=5.25; group.add(head);
    beam(group,[.5,4.2,0],[1.2,6.3,0],.18,jade); beam(group,[1.2,6.3,0],[1.2,6.9,0],.09,gold);
    const flame=new THREE.Mesh(new THREE.ConeGeometry(.24,.6,6),gold); flame.position.set(1.2,7.15,0); group.add(flame);
    return group;
  }
  const models={kremlin:kremlin(),gate:gate(),pyramids:pyramids()};
  if (!illustrationsOnly) Object.assign(models,{tower:eiffel(),spire:spire(),clocktower:clocktower(),
    colosseum:colosseum(),liberty:liberty()});
  return models;
}

export function createLandmarkRenderer(map) {
  const renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, preserveDrawingBuffer:true, powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(160, 160, false);
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-4.8,4.8,4.8,-4.8,0.1,60);
  camera.position.set(10,8,14); camera.lookAt(0,3.2,0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x98a8ae, 2.2));
  const light = new THREE.DirectionalLight(0xffffff, 2); light.position.set(6,12,8); scene.add(light);
  const models = createLandmarkModels();
  Object.values(models).forEach((model) => { model.visible=false; scene.add(model); });
  let targets = [], frame = 0;
  function draw() {
    frame = 0;
    const center = map.getCenter(), bearing = map.getBearing();
    for (const target of targets) {
      if (!target.canvas.isConnected) continue;
      const model = models[target.kind]; if (!model) continue;
      model.visible = true;
      model.rotation.y = THREE.MathUtils.degToRad(Math.max(-40, Math.min(40, (center.lng-target.lon)*.45)) - bearing);
      renderer.render(scene,camera);
      const context = target.canvas.getContext('2d'); context.clearRect(0,0,target.canvas.width,target.canvas.height);
      context.drawImage(renderer.domElement,0,0,target.canvas.width,target.canvas.height);
      model.visible = false;
    }
  }
  function schedule() { if (!frame) frame=requestAnimationFrame(draw); }
  map.on('move',schedule);
  map.on('remove',() => { map.off('move',schedule); if (frame) cancelAnimationFrame(frame); renderer.dispose(); });
  return {setTargets(next) {targets=next; schedule();}};
}
