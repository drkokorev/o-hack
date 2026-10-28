/* Small local Three.js models rendered as animated, geographically anchored map markers. */
import * as THREE from './vendor/three/three.module.js';

export function createLandmarkModels() {
  const iron = new THREE.MeshStandardMaterial({color:0x3153aa, roughness:0.75, metalness:0.2});
  const lightIron = new THREE.MeshStandardMaterial({color:0x8ba0d4, roughness:0.72});
  const red = new THREE.MeshStandardMaterial({color:0xa94742, roughness:0.82});
  const stone = new THREE.MeshStandardMaterial({color:0xd9d4c1, roughness:0.86});
  const gold = new THREE.MeshStandardMaterial({color:0xe3ae4c, roughness:0.65});
  const glass = new THREE.MeshStandardMaterial({color:0x607f9b, roughness:0.5, metalness:0.35});
  const dark = new THREE.MeshStandardMaterial({color:0x263c48, roughness:0.8});
  const jade = new THREE.MeshStandardMaterial({color:0x6da998, roughness:0.8});
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
    const group = new THREE.Group();
    box(group,4.4,1.1,1.8,0,.55,0,red); box(group,1.45,2.9,1.4,0,1.45,0,red);
    box(group,1.65,.2,1.6,0,2.85,0,stone);
    const roof=new THREE.Mesh(new THREE.ConeGeometry(1.05,2.5,4),iron); roof.position.set(0,4.2,0); roof.rotation.y=Math.PI/4; group.add(roof);
    beam(group,[0,5.5,0],[0,6.5,0],.06,gold);
    for (const x of [-1.75,1.75]) {box(group,.65,2.3,.8,x,1.15,0,red);
      const top=new THREE.Mesh(new THREE.ConeGeometry(.65,1.2,4),iron);top.position.set(x,2.9,0);top.rotation.y=Math.PI/4;group.add(top);}
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
    const group = new THREE.Group();
    for(const x of [-1.7,1.7]) box(group,.55,4.3,.55,x,2.15,0,red);
    box(group,4.5,.45,1.05,0,4.3,0,dark); box(group,4.1,.38,.9,0,4.75,0,red);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(3.1,1.05,4),dark);
    roof.scale.z=.45; roof.position.y=5.45; roof.rotation.y=Math.PI/4; group.add(roof);
    const lantern=new THREE.Mesh(new THREE.SphereGeometry(.65,12,8),gold);
    lantern.scale.y=1.15; lantern.position.set(0,3.25,0); group.add(lantern); return group;
  }
  function pyramids() {
    const group = new THREE.Group();
    for(const [x,z,size] of [[-.65,0,2.7],[1.6,-.5,1.35]]) {
      const pyramid = new THREE.Mesh(new THREE.ConeGeometry(size,size*1.35,4),gold);
      pyramid.rotation.y=Math.PI/4; pyramid.position.set(x,size*.675,z); group.add(pyramid);
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
  const models = {tower:eiffel(), kremlin:kremlin(), spire:spire(), clocktower:clocktower(),
    colosseum:colosseum(), gate:gate(), pyramids:pyramids(), liberty:liberty()};
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
