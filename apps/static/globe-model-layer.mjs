/* Solid meshes in the map's own WebGL scene. Coordinates and altitude are
   projected by MapLibre, so objects turn with the globe rather than facing
   the screen like billboards. Sizes are deliberately enlarged for discovery. */
import * as THREE from './vendor/three/three.module.js';
import {GLTFLoader} from './vendor/three/GLTFLoader.js';
import {DRACOLoader} from './vendor/three/DRACOLoader.js';

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
    const colours={}; // Preserve the mineral palette supplied with the 32 original miniatures.
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

export function createGlobeModelLayer(map, lib, onModelState=()=>{}, modelIds=[]) {
  const assetFiles=Object.fromEntries(modelIds.filter(id=>/^[a-z_]+$/.test(id)).map(id=>[id,`${id}.glb`]));
  const geometries={};
  // For supplied models show an accessible small marker while loading, rather
  // than constructing a crude temporary 3D model and then swapping it abruptly.
  for (const name of [...Object.keys(assetFiles),'heritage_culture','heritage_nature']) delete geometries[name];
  const parts=new Map(Object.entries(geometries).map(([name,mesh])=>[name,geometryData(mesh,name)]));
  const buffers=new Map(), programs=new Map(), textures=new Map(), loaded=new Set(), loading=new Set(), failed=new Set();
  const draco=new DRACOLoader();draco.setDecoderPath(new URL('./vendor/three/draco/',import.meta.url).href);draco.setWorkerLimit(2);
  const loader=new GLTFLoader();loader.setDRACOLoader(draco);
  let landmarks=[], events=[], glContext=null, removed=false;
  function state(name) {return !assetFiles[name] ? 'stylised' : loaded.has(name) ? 'ready' : failed.has(name) ? 'failed' : 'loading';}
  function requestAsset(name) {
    const file=assetFiles[name];
    if (!file || loaded.has(name) || loading.has(name) || failed.has(name) || !glContext) return;
    loading.add(name);
    loader.load(new URL(`./models/landmarks/${file}?v=landmarks-32`,import.meta.url).href,(asset)=>{
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
    p._uniforms={};p._attributes={};programs.set(desc.variantName,p); return p;
  }
  function attribute(gl,p,name) {return p._attributes[name] ??= gl.getAttribLocation(p,name);}
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
      buffers.clear();programs.clear();textures.clear();removed=false;
      glContext=gl;
      for (const [name,items] of parts) install(gl,name,items);
      requestAssets([...landmarks,...events]);
    },
    render(gl,args) {
      if(gl.isContextLost()||!args.shaderData||!args.defaultProjectionData)return;
      const p=program(gl,args.shaderData),projection=args.defaultProjectionData;
      gl.useProgram(p); const u=(name)=>(p._uniforms[name] ??= gl.getUniformLocation(p,name));
      gl.uniformMatrix4fv(u('u_projection_fallback_matrix'),false,projection.fallbackMatrix);
      gl.uniformMatrix4fv(u('u_projection_matrix'),false,projection.mainMatrix);
      gl.uniform4f(u('u_projection_tile_mercator_coords'),...projection.tileMercatorCoords);
      gl.uniform4f(u('u_projection_clipping_plane'),...projection.clippingPlane);
      gl.uniform1f(u('u_projection_transition'),projection.projectionTransition);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.CULL_FACE); gl.disable(gl.BLEND);
      const aPosition=attribute(gl,p,'a_position'),aNormal=attribute(gl,p,'a_normal');
      const aColor=attribute(gl,p,'a_color'),aUV=attribute(gl,p,'a_uv');
      for (const a of [aPosition,aNormal,aColor,aUV]) gl.enableVertexAttribArray(a);
      const center=map.getCenter(), rad=Math.PI/180, phi=center.lat*rad, lambda=center.lng*rad;
      const view=[Math.cos(phi)*Math.cos(lambda),Math.cos(phi)*Math.sin(lambda),Math.sin(phi)];
      const east=[-Math.sin(lambda),Math.cos(lambda),0],north=[-Math.sin(phi)*Math.cos(lambda),-Math.sin(phi)*Math.sin(lambda),Math.cos(phi)];
      const light=view.map((v,i)=>v-.42*east[i]+.62*north[i]);
      for (const target of [...landmarks,...events]) {
        const targetBuffers=buffers.get(target.kind); if (!targetBuffers || state(target.kind)==='loading' || state(target.kind)==='failed') continue;
        const coord=lib.MercatorCoordinate.fromLngLat([target.lon,target.lat]);
        const facing=Math.sin(phi)*Math.sin(target.lat*rad)+Math.cos(phi)*Math.cos(target.lat*rad)*Math.cos((target.lon-center.lng)*rad);
        if (facing<=.60) continue;
        const lean=target.kind==='pyramids' ? 1.0 : target.kind==='spire' ? .8 : .58;
        // Shrink gently near the limb instead of letting large objects project
        // into empty space or vanish while they are still on the visible side.
        const horizonFactor=1;
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
    restore(){if(!map.getLayer(layer.id))map.addLayer(layer);else layer.onAdd(map,map.getCanvas().getContext('webgl2'));map.triggerRepaint();},
    setLandmarks(next) {landmarks=next;requestAssets(next);if (glContext) map.triggerRepaint();},
    setEvents(next) {events=next;requestAssets(next);if (glContext) map.triggerRepaint();},
    getLoadedModels() {return [...loaded];},
    getModelState(name) {return state(name);},
  };
}
