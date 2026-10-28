/* Original architectural miniatures. Drop-in createLandmarkRenderer(map) API.
 * One WebGL context, lazy GLB loads, demand rendering, bounded bitmap cache.
 */
import * as THREE from './vendor/three/three.module.js';
import { GLTFLoader } from './vendor/three/GLTFLoader.js';
import { DRACOLoader } from './vendor/three/DRACOLoader.js';

export function createLandmarkRenderer(map, options = {}) {
  const assetBase = options.assetBase || new URL('./models/landmarks/', import.meta.url);
  const size = options.size || 320;
  const renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, preserveDrawingBuffer:true, powerPreference:'low-power'});
  renderer.setPixelRatio(1);
  renderer.setSize(size,size,false);
  renderer.setClearColor(0,0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.17;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-5,5,5,-5,.1,100);
  scene.add(new THREE.HemisphereLight(0xe8f4ff,0xb2a48e,2.2));
  const key = new THREE.DirectionalLight(0xffedcf,3.1);
  key.position.set(-6,12,8);key.castShadow=true;
  key.shadow.mapSize.set(1024,1024);
  Object.assign(key.shadow.camera,{left:-6,right:6,top:10,bottom:-6,near:.1,far:40});
  key.shadow.bias=-.0004;key.shadow.normalBias=.025;key.shadow.radius=3;
  scene.add(key);
  const fill=new THREE.DirectionalLight(0xd5e9ff,1.35);fill.position.set(6,7,-5);scene.add(fill);
  const shadowCanvas=document.createElement('canvas');shadowCanvas.width=shadowCanvas.height=128;
  const shadowContext=shadowCanvas.getContext('2d');
  const gradient=shadowContext.createRadialGradient(64,64,12,64,64,64);
  gradient.addColorStop(0,'rgba(28,48,35,.24)');gradient.addColorStop(.5,'rgba(28,48,35,.13)');gradient.addColorStop(1,'rgba(28,48,35,0)');
  shadowContext.fillStyle=gradient;shadowContext.fillRect(0,0,128,128);
  const shadowTexture=new THREE.CanvasTexture(shadowCanvas);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.MeshBasicMaterial({map:shadowTexture,transparent:true,depthWrite:false}));
  floor.rotation.x=-Math.PI/2;floor.position.y=-.018;scene.add(floor);
  const draco=new DRACOLoader().setDecoderPath(new URL('./vendor/three/draco/',import.meta.url).href).setWorkerLimit(2);
  const loader=new GLTFLoader();
  loader.setDRACOLoader(draco);
  const allowed=new Set(['tower','kremlin','spire','clocktower','colosseum','gate','pyramids','liberty','isaac','kulsharif','sochi_port','shamanka','kamchatka','russky_bridge','galata','cappadocia','registan','sagrada','parthenon','belem','great_wall','taj_mahal','marina_bay','petronas','fuji','bali_temple','maldives','christ','chichen_itza','golden_gate','opera','table_mountain']);
  const models=new Map(),jobs=new Map(),errors=new Map(),bitmaps=new Map();
  let targets=[],frame=0,disposed=false;
  let activeLoads=0;
  const queue=[];
  function pump(){
    while(!disposed&&activeLoads<3&&queue.length){
      const task=queue.shift();activeLoads++;
      loader.loadAsync(task.url).catch(()=>loader.loadAsync(task.url)).then(task.resolve,task.reject).finally(()=>{activeLoads--;pump();});
    }
  }
  function fetchModel(url){return new Promise((resolve,reject)=>{queue.push({url,resolve,reject});pump();});}
  function disposeModel(root) {
    root.traverse(o=>{if(o.isMesh){o.geometry.dispose();for(const m of [].concat(o.material))m.dispose();}});
  }
  function load(kind) {
    if(!allowed.has(kind)||models.has(kind)||jobs.has(kind)||errors.has(kind)||disposed)return;
    const job=fetchModel(new URL(kind+'.glb',assetBase).href).then(gltf=>{
      if(disposed){disposeModel(gltf.scene);return;}
      const root=gltf.scene;
      root.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});
      const bound=new THREE.Box3().setFromObject(root),center=bound.getCenter(new THREE.Vector3());
      root.position.set(-center.x,-bound.min.y,-center.z);
      const group=new THREE.Group();group.add(root);group.visible=false;scene.add(group);
      const dimension=bound.getSize(new THREE.Vector3());
      models.set(kind,{group,height:dimension.y,width:Math.max(dimension.x,dimension.z)});
      schedule();
    }).catch(error=>{errors.set(kind,error.message);schedule();}).finally(()=>jobs.delete(kind));
    jobs.set(kind,job);
  }
  function fallback(target) {
    const ctx=target.canvas.getContext('2d');if(!ctx)return;
    const w=target.canvas.width,h=target.canvas.height;ctx.clearRect(0,0,w,h);
    ctx.fillStyle='#edf3f0';ctx.beginPath();ctx.roundRect(w*.34,h*.24,w*.32,h*.54,w*.06);ctx.fill();
    ctx.fillStyle='#3358bd';ctx.beginPath();ctx.moveTo(w*.5,h*.15);ctx.lineTo(w*.28,h*.37);ctx.lineTo(w*.72,h*.37);ctx.closePath();ctx.fill();
    for(let i=0;i<3;i++)ctx.fillRect(w*.43,h*(.43+i*.10),w*.14,h*.05);
    target.canvas.dataset.modelState=errors.has(target.kind)?'fallback':'loading';
  }
  function angleFor(target) {
    const center=map.getCenter(),bearing=map.getBearing();
    // Quantization caches snapshots while the globe moves; no idle animation.
    const angle=Math.max(-40,Math.min(40,(center.lng-target.lon)*.45))-bearing;
    return Math.round(angle/3)*3;
  }
  function draw() {
    frame=0;if(disposed)return;
    for(const target of targets){
      if(!target.canvas.isConnected)continue;
      const model=models.get(target.kind);
      if(!model){fallback(target);continue;}
      const angle=angleFor(target),cacheKey=target.kind+':'+angle;
      let bitmap=bitmaps.get(cacheKey);
      if(!bitmap){
        const {group,height,width}=model;
        const scale=Math.max(height*1.19,width*1.53),mid=height*.44;
        floor.scale.set(width*1.55,width*1.55,1);
        camera.left=camera.bottom=-scale/2;camera.right=camera.top=scale/2;
        camera.position.set(11,mid+(target.kind==='colosseum'?15:10),17);
        camera.lookAt(0,mid,0);camera.updateProjectionMatrix();
        group.rotation.y=THREE.MathUtils.degToRad(angle);group.visible=true;
        renderer.render(scene,camera);group.visible=false;
        bitmap=document.createElement('canvas');bitmap.width=bitmap.height=size;
        bitmap.getContext('2d').drawImage(renderer.domElement,0,0);
        bitmaps.set(cacheKey,bitmap);
        while(bitmaps.size>32)bitmaps.delete(bitmaps.keys().next().value);
      }
      const ctx=target.canvas.getContext('2d');if(!ctx)continue;
      ctx.clearRect(0,0,target.canvas.width,target.canvas.height);
      ctx.drawImage(bitmap,0,0,target.canvas.width,target.canvas.height);
      target.canvas.dataset.modelState='ready';
    }
  }
  function schedule(){if(!frame&&!disposed)frame=requestAnimationFrame(draw);}
  function dispose(){
    if(disposed)return;disposed=true;if(frame)cancelAnimationFrame(frame);
    for(const task of queue.splice(0))task.reject(new Error('Renderer disposed'));
    map.off('move',schedule);map.off('remove',dispose);
    renderer.domElement.removeEventListener('webglcontextlost',onLost);
    renderer.domElement.removeEventListener('webglcontextrestored',onRestored);
    for(const {group} of models.values())disposeModel(group);
    models.clear();bitmaps.clear();floor.geometry.dispose();floor.material.dispose();shadowTexture.dispose();key.shadow.map?.dispose();draco.dispose();
    renderer.dispose();targets=[];
  }
  function onLost(event){event.preventDefault();for(const target of targets){errors.set(target.kind,'WebGL context lost');fallback(target);}}
  function onRestored(){bitmaps.clear();for(const kind of models.keys())errors.delete(kind);schedule();}
  renderer.domElement.addEventListener('webglcontextlost',onLost);
  renderer.domElement.addEventListener('webglcontextrestored',onRestored);
  map.on('move',schedule);map.on('remove',dispose);
  return {
    setTargets(next){targets=next;for(const target of next)load(target.kind);schedule();},
    dispose,
    async ready(){await Promise.allSettled([...jobs.values()]);draw();return {loaded:[...models.keys()],errors:Object.fromEntries(errors)};},
    stats(){return {loaded:models.size,failed:errors.size,bitmaps:bitmaps.size,webglContexts:1};}
  };
}
