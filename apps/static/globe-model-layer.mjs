/* Solid meshes in the map's own WebGL scene. Coordinates and altitude are
   projected by MapLibre, so objects turn with the globe rather than facing
   the screen like billboards. Sizes are deliberately enlarged for discovery. */
import * as THREE from './vendor/three/three.module.js';
import {GLTFLoader} from './vendor/three/GLTFLoader.js';
import {createLandmarkModels} from './landmarks-3d.mjs?v=globe-20261028-32';

function makeEventModels() {
  const material = (color) => new THREE.MeshStandardMaterial({color});
  const red = material(0xb96e5d), blue = material(0x859c94), gold = material(0xc9a56e);
  const dark = material(0x304748), jade = material(0x9caf96), pale = material(0xe9deca);
  const box = (group, w, h, d, x, y, z, mat) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w,h,d), mat);
    mesh.position.set(x,y,z); group.add(mesh); return mesh;
  };
  const wheel = (group, x, z) => {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(.46,.46,.32,12), dark);
    mesh.rotation.x = Math.PI / 2; mesh.position.set(x,.48,z); group.add(mesh);
  };
  const race = new THREE.Group();
  box(race,3.4,.38,.65,0,.62,0,red); box(race,1.35,.32,.82,-.1,.95,0,red);
  box(race,.65,.25,.5,-.25,1.18,0,dark); box(race,.3,.18,2.05,-1.65,.55,0,red);
  box(race,.3,.18,1.85,1.65,.65,0,red);
  for (const x of [-1.1,1.1]) for (const z of [-.86,.86]) wheel(race,x,z);
  const music = new THREE.Group();
  box(music,.2,2.8,.2,.8,1.75,0,blue); box(music,1.2,.27,.24,.3,3,0,blue);
  for (const [x,y] of [[-.15,.6],[.8,1.0]]) {
    const n=new THREE.Mesh(new THREE.SphereGeometry(.5,12,8),blue); n.scale.set(1,.65,.6); n.position.set(x,y,0); music.add(n);
  }
  const art = new THREE.Group();
  const palette = new THREE.Mesh(new THREE.CylinderGeometry(1.2,1.2,.24,20),pale);
  palette.position.y=1.2; palette.rotation.x=.35; art.add(palette);
  for (const [x,z,mat] of [[-.7,0,red],[0,-.7,blue],[.7,0,gold],[0,.7,jade]]) {
    const spot=new THREE.Mesh(new THREE.SphereGeometry(.18,8,6),mat); spot.position.set(x,1.4,z); art.add(spot);
  }
  const nature = new THREE.Group();
  box(nature,.35,1.5,.35,0,.75,0,dark);
  const crown=new THREE.Mesh(new THREE.ConeGeometry(1.1,2.2,7),jade); crown.position.y=2.2; nature.add(crown);
  const sport = new THREE.Group();
  const ball=new THREE.Mesh(new THREE.SphereGeometry(1.1,16,12),pale); ball.position.y=1.3; sport.add(ball);
  box(sport,1.5,.25,1.5,0,.15,0,blue);
  const culture = new THREE.Group();
  for (const x of [-.7,.7]) box(culture,.32,1.8,.32,x,1,0,blue);
  box(culture,2,.25,.55,0,1.95,0,gold);
  const roof=new THREE.Mesh(new THREE.ConeGeometry(1.35,.8,4),red); roof.rotation.y=Math.PI/4; roof.position.y=2.5; culture.add(roof);
  const tech = new THREE.Group();
  box(tech,1.8,1.8,.3,0,1.15,0,blue); box(tech,1.3,1.3,.1,0,1.15,.2,pale);
  const film = new THREE.Group();
  box(film,2,.95,.3,0,1,0,dark); box(film,2,.3,.35,0,1.75,0,pale);
  const festive = new THREE.Group();
  box(festive,1.7,1.5,1.4,0,.75,0,red); box(festive,.2,1.6,1.5,0,.8,0,gold); box(festive,1.8,.2,.2,0,1.55,0,gold);
  const segment = (group, from, to, radius, mat) => {
    const start = new THREE.Vector3(...from), end = new THREE.Vector3(...to), delta=end.clone().sub(start);
    const rod = new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,delta.length(),8),mat);
    rod.position.copy(start).add(end).multiplyScalar(.5);
    rod.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize()); group.add(rod);
  };
  const bicycle = new THREE.Group();
  for (const x of [-1.15,1.15]) {
    const tyre = new THREE.Mesh(new THREE.TorusGeometry(.66,.1,8,20),dark);
    tyre.position.set(x,.76,0); bicycle.add(tyre);
  }
  for (const [a,b] of [[[-1.15,.76,0],[0,1.55,0]],[[0,1.55,0],[.15,.76,0]],
    [[.15,.76,0],[-1.15,.76,0]],[[0,1.55,0],[.8,1.55,0]],[[.8,1.55,0],[1.15,.76,0]],
    [[.15,.76,0],[.8,1.55,0]]]) segment(bicycle,a,b,.065,red);
  box(bicycle,.5,.12,.23,-.1,1.72,0,dark); box(bicycle,.35,.1,.25,.85,1.72,0,dark);
  const sailing = new THREE.Group();
  box(sailing,3,.35,.95,0,.27,0,blue); segment(sailing,[0,.42,0],[0,3.2,0],.08,dark);
  const sailShape=new THREE.Shape(); sailShape.moveTo(.08,.6); sailShape.lineTo(.08,2.95); sailShape.lineTo(1.3,.6); sailShape.closePath();
  const sail=new THREE.Mesh(new THREE.ShapeGeometry(sailShape),pale); sailing.add(sail);
  const surfing = new THREE.Group();
  const board=new THREE.Mesh(new THREE.CapsuleGeometry(.34,2.6,4,10),gold);
  board.rotation.z=Math.PI/2; board.position.y=.42; board.scale.z=.45; surfing.add(board);
  const wave=new THREE.Mesh(new THREE.TorusGeometry(1,.16,8,16,Math.PI),blue);
  wave.rotation.x=Math.PI/2; wave.position.y=.17; surfing.add(wave);
  const flower = new THREE.Group();
  segment(flower,[0,.2,0],[0,2.1,0],.12,jade);
  for (let i=0;i<6;i++) {
    const angle=i*Math.PI/3, petal=new THREE.Mesh(new THREE.SphereGeometry(.35,10,7),red);
    petal.position.set(Math.cos(angle)*.52,2.2+Math.sin(angle)*.52,0); flower.add(petal);
  }
  const flowerCenter=new THREE.Mesh(new THREE.SphereGeometry(.32,10,7),gold); flowerCenter.position.y=2.2; flower.add(flowerCenter);
  const book = new THREE.Group();
  box(book,1.1,1.55,.22,-.57,1,0,blue); box(book,1.1,1.55,.22,.57,1,0,red);
  box(book,.1,1.62,.28,0,1,.05,gold);
  const food = new THREE.Group();
  const plate=new THREE.Mesh(new THREE.CylinderGeometry(1.05,1.05,.16,20),pale); plate.position.y=.25; food.add(plate);
  const meal=new THREE.Mesh(new THREE.SphereGeometry(.62,12,8),red); meal.scale.y=.5; meal.position.y=.58; food.add(meal);
  segment(food,[1.35,.15,0],[1.35,2.1,0],.09,dark); box(food,.45,.1,.15,1.35,2.05,0,dark);
  const paw = new THREE.Group();
  const pad=new THREE.Mesh(new THREE.SphereGeometry(.7,12,8),gold); pad.scale.set(1,.7,.4); pad.position.y=1; paw.add(pad);
  for (const [x,y] of [[-.85,1.8],[-.3,2.15],[.3,2.15],[.85,1.8]]) {
    const toe=new THREE.Mesh(new THREE.SphereGeometry(.3,10,6),gold); toe.position.set(x,y,0); paw.add(toe);
  }
  const heritage_culture = new THREE.Group();
  box(heritage_culture,2.8,.35,1.6,0,.2,0,pale);
  for (const x of [-1,0,1]) box(heritage_culture,.25,1.65,.25,x,1.15,0,blue);
  box(heritage_culture,2.9,.25,.7,0,2.05,0,gold);
  const heritage_nature = new THREE.Group();
  const mountain=new THREE.Mesh(new THREE.ConeGeometry(1.7,2.6,5),jade); mountain.position.y=1.3; heritage_nature.add(mountain);
  const models={race,music,art,nature,sport,culture,tech,film,festive,bicycle,sailing,surfing,flower,book,food,paw,
    heritage_culture,heritage_nature};
  // One restrained base ties event categories together visually.
  for (const [name,group] of Object.entries(models)) {
    if (name==='race' || name.startsWith('heritage_')) continue;
    for (const child of group.children) child.position.y+=.22;
    const base=new THREE.Mesh(new THREE.CylinderGeometry(1.65,1.78,.22,24),dark);base.position.y=.11;group.add(base);
    const rim=new THREE.Mesh(new THREE.TorusGeometry(1.65,.06,6,24),gold);rim.rotation.x=Math.PI/2;rim.position.y=.24;group.add(rim);
  }
  return models;
}

// Convert scene meshes into a small set of WebGL buffers. The original UVs and
// textures are retained; positions are normalized around the actual anchor.
function geometryData(group, kind, imported=false) {
  if (imported && kind==='race') group.rotation.set(.30,.65,0);
  if (imported && kind==='film') group.rotation.y=Math.PI/2;
  group.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(group), size=new THREE.Vector3();
  bounds.getSize(size);
  const horizontal=kind==='race' || kind==='colosseum' || kind==='art';
  const factor=imported ? (horizontal ? 5.0/Math.max(size.x,size.z) : 7.35/size.y) : 1;
  const midX=imported ? (bounds.min.x+bounds.max.x)/2 : 0;
  const midZ=imported ? (bounds.min.z+bounds.max.z)/2 : 0;
  const floor=imported ? bounds.min.y : 0;
  const pieces=new Map(), normalMatrix=new THREE.Matrix3(), pos=new THREE.Vector3(), normal=new THREE.Vector3();
  const materialColor=(material) => {
    const colours={tower:'#decaa6',spire:'#b7d0c5',clocktower:'#ead6b5',colosseum:'#e1d0b0',liberty:'#a5c4ad',music:'#e6c999'};
    if (imported && kind==='art') {
      const palette={Base:'#e5d3af',Color1:'#c78267',Color2:'#8aada0',Color3:'#d5ad68',Color4:'#6f9495',Color5:'#c5a58e',Color6:'#e4d2ac',Color7:'#9b8276'};
      return new THREE.Color(palette[material?.name] || palette.Base).convertLinearToSRGB();
    }
    if (imported && kind==='sport') return new THREE.Color(/black/i.test(material?.name || '') ? '#304b48' : '#e8ddc5').convertLinearToSRGB();
    if (imported && kind==='film' && material?.color && material.color.r + material.color.g + material.color.b < .3)
      return new THREE.Color('#304b48').convertLinearToSRGB();
    if (imported && colours[kind]) return new THREE.Color(colours[kind]).convertLinearToSRGB();
    return (material?.color || new THREE.Color('#dbcaa5')).clone().convertLinearToSRGB();
  };
  group.traverse((mesh) => {
    if (!mesh.isMesh || !mesh.geometry?.getAttribute('position')) return;
    const geometry=mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry;
    const positions=geometry.getAttribute('position'), uv=geometry.getAttribute('uv');
    if (!geometry.getAttribute('normal')) geometry.computeVertexNormals();
    const normalAttribute=geometry.getAttribute('normal');
    normalMatrix.getNormalMatrix(mesh.matrixWorld);
    const mats=Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const groups=geometry.groups.length && mats.length>1 ? geometry.groups : [{start:0,count:positions.count,materialIndex:0}];
    for (const section of groups) {
      const material=mats[section.materialIndex] || mats[0], color=materialColor(material);
      const texture=(material?.map && uv) ? material.map : null;
      if (!pieces.has(texture)) pieces.set(texture,{chunks:[],length:0});
      const end=Math.min(section.start+section.count,positions.count);
      const chunk=new Float32Array((end-section.start)*11); let at=0;
      for (let i=section.start;i<end;i++) {
        pos.fromBufferAttribute(positions,i).applyMatrix4(mesh.matrixWorld);
        normal.fromBufferAttribute(normalAttribute,i).applyNormalMatrix(normalMatrix);
        chunk[at++]=(pos.x-midX)*factor;chunk[at++]=(pos.y-floor)*factor;chunk[at++]=(pos.z-midZ)*factor;
        chunk[at++]=normal.x;chunk[at++]=normal.y;chunk[at++]=normal.z;
        chunk[at++]=color.r;chunk[at++]=color.g;chunk[at++]=color.b;
        chunk[at++]=uv ? uv.getX(i) : 0;chunk[at++]=uv ? uv.getY(i) : 0;
      }
      const piece=pieces.get(texture);piece.chunks.push(chunk);piece.length+=chunk.length;
    }
    if (geometry!==mesh.geometry) geometry.dispose();
  });
  const result=[...pieces].map(([texture,piece])=>{
    const data=new Float32Array(piece.length);let offset=0;
    for(const chunk of piece.chunks){data.set(chunk,offset);offset+=chunk.length;}
    return {texture,data};
  }).filter(piece=>piece.data.length);
  result.dimensions={x:size.x*factor,y:size.y*factor,z:size.z*factor};
  return result;
}

export function createGlobeModelLayer(map, lib, onModelState=()=>{}) {
  const assetFiles={tower:'eiffel-tower.glb',spire:'burj-khalifa.glb',clocktower:'big-ben.glb',
    colosseum:'colosseum.glb',liberty:'statue-liberty.glb',race:'formula-car.glb',
    film:'event-film.glb',art:'event-art.glb',music:'event-music.glb',sport:'event-sport.glb'};
  const geometries={...createLandmarkModels({illustrationsOnly:true}), ...makeEventModels()};
  // For supplied models show an accessible small marker while loading, rather
  // than constructing a crude temporary 3D model and then swapping it abruptly.
  for (const name of [...Object.keys(assetFiles),'heritage_culture','heritage_nature']) delete geometries[name];
  const parts=new Map(Object.entries(geometries).map(([name,mesh])=>[name,geometryData(mesh,name)]));
  const buffers=new Map(), programs=new Map(), textures=new Map(), loaded=new Set(), loading=new Set(), failed=new Set();
  const loader=new GLTFLoader();
  let landmarks=[], events=[], glContext=null, removed=false;
  function state(name) {return !assetFiles[name] ? 'stylised' : loaded.has(name) ? 'ready' : failed.has(name) ? 'failed' : 'loading';}
  function requestAsset(name) {
    const file=assetFiles[name];
    if (!file || loaded.has(name) || loading.has(name) || failed.has(name) || !glContext) return;
    loading.add(name);
    loader.load(new URL(`./assets/${file}?v=globe-20261028-32`,import.meta.url).href,(asset)=>{
      if (removed || !glContext) return;
      try {
        const imported=geometryData(asset.scene,name,true);
        if (!imported.length) throw Error('empty model');
        parts.set(name,imported);install(glContext,name,imported);loaded.add(name);
      } catch (error) {failed.add(name);console.warn(`3D model ${name} could not be prepared`,error);}
      loading.delete(name);onModelState(name,state(name));map.triggerRepaint();
    },undefined,(error)=>{
      loading.delete(name);failed.add(name);onModelState(name,state(name));
      console.warn(`3D model ${name} could not be loaded`,error);map.triggerRepaint();
    });
  }
  function requestAssets(targets) {for(const target of targets) requestAsset(target.kind);}
  // Estimate local projected metres in CSS pixels, so the same object does not
  // inflate with latitude, zoom level, or device pixel ratio.
  function scaleFor(target,dimensions,lean) {
    const lat=Math.max(-84.5,Math.min(84.5,target.lat)), sample=15000;
    const latitudeDelta=sample/111320, longitudeDelta=sample/(111320*Math.max(.1,Math.cos(lat*Math.PI/180)));
    const anchor=map.project([target.lon,lat]);
    const east=map.project([target.lon+longitudeDelta,lat]);
    const south=map.project([target.lon,lat-latitudeDelta]);
    const pixelsPerMeter=Math.max(Math.hypot(east.x-anchor.x,east.y-anchor.y),Math.hypot(south.x-anchor.x,south.y-anchor.y))/sample;
    const span=Math.max(dimensions.x,dimensions.z+dimensions.y*lean,dimensions.y,1);
    const width=map.getContainer().clientWidth, targetPixels=Math.min(70,Math.max(52,width*.16))*(target.event ? .85 : 1);
    if (!Number.isFinite(pixelsPerMeter) || pixelsPerMeter<1e-10) return 1;
    return Math.max(.05,Math.min(260000,targetPixels/(pixelsPerMeter*span)));
  }
  function shader(gl,type,code) {
    const result=gl.createShader(type); gl.shaderSource(result,code); gl.compileShader(result);
    if (!gl.getShaderParameter(result,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(result));
    return result;
  }
  function program(gl,desc) {
    if (programs.has(desc.variantName)) return programs.get(desc.variantName);
    const vertex=`#version 300 es\n${desc.vertexShaderPrelude}\n${desc.define}
      in vec3 a_position; in vec3 a_normal; in vec3 a_color; in vec2 a_uv;
      out vec3 v_normal; out vec3 v_color; out vec2 v_uv;
      uniform vec2 u_anchor; uniform float u_meter_scale; uniform float u_model_scale; uniform float u_model_lean;
      void main() {
        vec2 point=u_anchor+vec2(a_position.x,a_position.z-a_position.y*u_model_lean)*u_meter_scale*u_model_scale;
        gl_Position=projectTileFor3D(point,max(0.0,a_position.y)*u_model_scale);
        v_normal=a_normal; v_color=a_color; v_uv=a_uv;
      }`;
    const fragment=`#version 300 es\nprecision highp float;
      in vec3 v_normal; in vec3 v_color; in vec2 v_uv; out vec4 fragColor;
      uniform vec3 u_light; uniform sampler2D u_image; uniform float u_has_image; uniform float u_texture_lift;
      void main() {
        vec3 n=normalize(v_normal);
        float diffuse=.62+.38*max(0.0,dot(n,normalize(u_light)));
        vec3 tex=mix(vec3(1.0),texture(u_image,v_uv).rgb,u_has_image);
        tex=mix(tex,vec3(1.0),u_texture_lift*u_has_image);
        vec3 color=v_color*tex*diffuse;
        color+=vec3(.055,.047,.032)*pow(max(0.0,dot(n,normalize(u_light+vec3(0.0,1.0,1.0)))),12.0);
        fragColor=vec4(color,1.0);
      }`;
    const vs=shader(gl,gl.VERTEX_SHADER,vertex),fs=shader(gl,gl.FRAGMENT_SHADER,fragment);
    const p=gl.createProgram(); gl.attachShader(p,vs); gl.attachShader(p,fs); gl.linkProgram(p);
    gl.deleteShader(vs); gl.deleteShader(fs);
    if (!gl.getProgramParameter(p,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    programs.set(desc.variantName,p); return p;
  }
  function install(gl,name,items) {
    for (const piece of buffers.get(name) || []) gl.deleteBuffer(piece.buffer);
    buffers.set(name,items.map((piece)=>{
      const buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,piece.data,gl.STATIC_DRAW);
      let texture=null;
      if (piece.texture?.image) {
        texture=textures.get(piece.texture);
        if (!texture) {
          texture=gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,texture);
          gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
          gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,piece.texture.image);
          textures.set(piece.texture,texture);
        }
      }
      return {buffer,texture,count:piece.data.length/11};
    }));
  }
  const layer={id:'discovery-3d',type:'custom',renderingMode:'3d',
    onAdd(_map,gl) {
      glContext=gl;
      for (const [name,items] of parts) install(gl,name,items);
      requestAssets([...landmarks,...events]);
    },
    render(gl,args) {
      const p=program(gl,args.shaderData),projection=args.defaultProjectionData;
      gl.useProgram(p); const u=(name)=>gl.getUniformLocation(p,name);
      gl.uniformMatrix4fv(u('u_projection_fallback_matrix'),false,projection.fallbackMatrix);
      gl.uniformMatrix4fv(u('u_projection_matrix'),false,projection.mainMatrix);
      gl.uniform4f(u('u_projection_tile_mercator_coords'),...projection.tileMercatorCoords);
      gl.uniform4f(u('u_projection_clipping_plane'),...projection.clippingPlane);
      gl.uniform1f(u('u_projection_transition'),projection.projectionTransition);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.CULL_FACE); gl.disable(gl.BLEND);
      const aPosition=gl.getAttribLocation(p,'a_position'),aNormal=gl.getAttribLocation(p,'a_normal');
      const aColor=gl.getAttribLocation(p,'a_color'),aUV=gl.getAttribLocation(p,'a_uv');
      for (const a of [aPosition,aNormal,aColor,aUV]) gl.enableVertexAttribArray(a);
      const center=map.getCenter(), rad=Math.PI/180, phi=center.lat*rad, lambda=center.lng*rad;
      const view=[Math.cos(phi)*Math.cos(lambda),Math.cos(phi)*Math.sin(lambda),Math.sin(phi)];
      const east=[-Math.sin(lambda),Math.cos(lambda),0],north=[-Math.sin(phi)*Math.cos(lambda),-Math.sin(phi)*Math.sin(lambda),Math.cos(phi)];
      const light=view.map((v,i)=>v-.42*east[i]+.62*north[i]);
      for (const target of [...landmarks,...events]) {
        const targetBuffers=buffers.get(target.kind); if (!targetBuffers || state(target.kind)==='loading' || state(target.kind)==='failed') continue;
        const coord=lib.MercatorCoordinate.fromLngLat([target.lon,target.lat]);
        const facing=Math.sin(phi)*Math.sin(target.lat*rad)+Math.cos(phi)*Math.cos(target.lat*rad)*Math.cos((target.lon-center.lng)*rad);
        if (facing<=.40) continue;
        const lean=target.kind==='pyramids' ? 1.0 : target.kind==='spire' ? .8 : .58;
        // Shrink gently near the limb instead of letting large objects project
        // into empty space or vanish while they are still on the visible side.
        const horizonFactor=Math.max(.02,Math.min(1,(facing-.40)/.20));
        const scale=scaleFor(target,parts.get(target.kind).dimensions,lean)*horizonFactor;
        const lat=target.lat*rad,lon=target.lon*rad;
        const up=[Math.cos(lat)*Math.cos(lon),Math.cos(lat)*Math.sin(lon),Math.sin(lat)];
        const side=[-Math.sin(lon),Math.cos(lon),0],south=[Math.sin(lat)*Math.cos(lon),Math.sin(lat)*Math.sin(lon),-Math.cos(lat)];
        const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
        gl.uniform3f(u('u_light'),dot(light,side),dot(light,up),dot(light,south));
        gl.uniform2f(u('u_anchor'),coord.x,coord.y);
        gl.uniform1f(u('u_meter_scale'),coord.meterInMercatorCoordinateUnits()); gl.uniform1f(u('u_model_scale'),scale);
        gl.uniform1f(u('u_model_lean'),lean);
        for (const piece of targetBuffers) {
          gl.bindBuffer(gl.ARRAY_BUFFER,piece.buffer);
          gl.vertexAttribPointer(aPosition,3,gl.FLOAT,false,44,0); gl.vertexAttribPointer(aNormal,3,gl.FLOAT,false,44,12);
          gl.vertexAttribPointer(aColor,3,gl.FLOAT,false,44,24); gl.vertexAttribPointer(aUV,2,gl.FLOAT,false,44,36);
          gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D,piece.texture); gl.uniform1i(u('u_image'),0);
          gl.uniform1f(u('u_has_image'),piece.texture ? 1 : 0);
          gl.uniform1f(u('u_texture_lift'),target.kind==='clocktower' ? .25 : 0);
          gl.drawArrays(gl.TRIANGLES,0,piece.count);
        }
      }
      for (const a of [aPosition,aNormal,aColor,aUV]) gl.disableVertexAttribArray(a);
    },
    onRemove(_map,gl) {
      removed=true; for (const items of buffers.values()) for (const piece of items) gl.deleteBuffer(piece.buffer);
      programs.forEach((item)=>gl.deleteProgram(item)); textures.forEach((item)=>gl.deleteTexture(item));
      buffers.clear(); programs.clear(); textures.clear(); glContext=null;
      const materials=new Set();
      Object.values(geometries).forEach((group)=>group.traverse((mesh)=>{
        if (!mesh.isMesh) return; mesh.geometry.dispose();
        for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material])
          if (material && !materials.has(material)) {material.dispose(); materials.add(material);}
      }));
    },
  };
  map.addLayer(layer);
  return {
    setLandmarks(next) {landmarks=next;requestAssets(next);if (glContext) map.triggerRepaint();},
    setEvents(next) {events=next;requestAssets(next);if (glContext) map.triggerRepaint();},
    getLoadedModels() {return [...loaded];},
    getModelState(name) {return state(name);},
  };
}
