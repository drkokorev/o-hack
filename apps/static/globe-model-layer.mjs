/* Solid meshes in the map's own WebGL scene. Coordinates and altitude are
   projected by MapLibre, so objects turn with the globe rather than facing
   the screen like billboards. Sizes are deliberately enlarged for discovery. */
import * as THREE from './vendor/three/three.module.js';
import {createLandmarkModels} from './landmarks-3d.mjs?v=globe-20261028-3';

function makeEventModels() {
  const material = (color) => new THREE.MeshStandardMaterial({color});
  const red = material(0xdf5147), blue = material(0x3153aa), gold = material(0xe3ae4c);
  const dark = material(0x263c48), jade = material(0x5d9c7a), pale = material(0xf1ead6);
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
  return {race,music,art,nature,sport,culture,tech,film,festive,bicycle,sailing,surfing,flower,book,food,paw,
    heritage_culture,heritage_nature};
}

function geometryData(group) {
  const data = [];
  group.updateMatrixWorld(true);
  const light = new THREE.Vector3(.45,.8,.35).normalize();
  const normalMatrix = new THREE.Matrix3(), p = new THREE.Vector3(), n = new THREE.Vector3();
  group.traverse((mesh) => {
    if (!mesh.isMesh) return;
    const geometry = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry;
    const positions = geometry.getAttribute('position'), normals = geometry.getAttribute('normal');
    normalMatrix.getNormalMatrix(mesh.matrixWorld);
    // Three.js stores material colors in linear space; this layer writes
    // directly to MapLibre's sRGB canvas, so convert before packing colors.
    const color = mesh.material.color.clone().convertLinearToSRGB();
    for (let i=0; i<positions.count; i++) {
      p.fromBufferAttribute(positions,i).applyMatrix4(mesh.matrixWorld);
      n.fromBufferAttribute(normals,i).applyNormalMatrix(normalMatrix);
      const shade = .58 + .42 * Math.max(0,n.dot(light));
      data.push(p.x,p.y,p.z, color.r*shade,color.g*shade,color.b*shade);
    }
    if (geometry !== mesh.geometry) geometry.dispose();
  });
  return new Float32Array(data);
}

export function createGlobeModelLayer(map, lib) {
  const geometries = {...createLandmarkModels(), ...makeEventModels()};
  const arrays = Object.fromEntries(Object.entries(geometries).map(([name, mesh]) => [name, geometryData(mesh)]));
  const buffers = new Map(), programs = new Map();
  let landmarks = [], events = [], glContext;
  function shader(gl, type, code) {
    const result=gl.createShader(type); gl.shaderSource(result,code); gl.compileShader(result);
    if (!gl.getShaderParameter(result,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(result));
    return result;
  }
  function program(gl, desc) {
    if (programs.has(desc.variantName)) return programs.get(desc.variantName);
    const vertex = `#version 300 es\n${desc.vertexShaderPrelude}\n${desc.define}
      in vec3 a_position; in vec3 a_color; out vec3 v_color;
      uniform vec2 u_anchor; uniform float u_meter_scale; uniform float u_model_scale;
      void main() {
        // A modest stylised lean makes small landmarks recognisable from a
        // global viewpoint; their base stays at the sourced coordinates.
        vec2 point = u_anchor + vec2(a_position.x,a_position.z - a_position.y * .38) * u_meter_scale * u_model_scale;
        gl_Position = projectTileFor3D(point,max(0.0,a_position.y) * u_model_scale);
        v_color = a_color;
      }`;
    const fragment = `#version 300 es\nprecision highp float; in vec3 v_color; out vec4 fragColor;
      void main() { fragColor=vec4(v_color,1.0); }`;
    const vs=shader(gl,gl.VERTEX_SHADER,vertex), fs=shader(gl,gl.FRAGMENT_SHADER,fragment);
    const p=gl.createProgram(); gl.attachShader(p,vs); gl.attachShader(p,fs); gl.linkProgram(p);
    gl.deleteShader(vs); gl.deleteShader(fs);
    if (!gl.getProgramParameter(p,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    programs.set(desc.variantName,p); return p;
  }
  const layer = {
    id:'discovery-3d', type:'custom', renderingMode:'3d',
    onAdd(_map,gl) {
      glContext=gl;
      for (const [name,array] of Object.entries(arrays)) {
        const buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
        gl.bufferData(gl.ARRAY_BUFFER,array,gl.STATIC_DRAW); buffers.set(name,buffer);
      }
    },
    render(gl,args) {
      const p=program(gl,args.shaderData), projection=args.defaultProjectionData;
      gl.useProgram(p);
      const uniform=(name) => gl.getUniformLocation(p,name);
      gl.uniformMatrix4fv(uniform('u_projection_fallback_matrix'),false,projection.fallbackMatrix);
      gl.uniformMatrix4fv(uniform('u_projection_matrix'),false,projection.mainMatrix);
      gl.uniform4f(uniform('u_projection_tile_mercator_coords'),...projection.tileMercatorCoords);
      gl.uniform4f(uniform('u_projection_clipping_plane'),...projection.clippingPlane);
      gl.uniform1f(uniform('u_projection_transition'),projection.projectionTransition);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.CULL_FACE);
      const aPosition=gl.getAttribLocation(p,'a_position'), aColor=gl.getAttribLocation(p,'a_color');
      gl.enableVertexAttribArray(aPosition); gl.enableVertexAttribArray(aColor);
      for (const target of [...landmarks,...events]) {
        const buffer=buffers.get(target.kind); if (!buffer) continue;
        const coord=lib.MercatorCoordinate.fromLngLat([target.lon,target.lat]);
        const center=map.getCenter(), r=Math.PI/180;
        if (Math.sin(center.lat*r)*Math.sin(target.lat*r) + Math.cos(center.lat*r)*Math.cos(target.lat*r)*Math.cos((target.lon-center.lng)*r) <= .03) continue;
        const scale=Math.max(1, 310000 * Math.pow(2,1.3-map.getZoom())) * (target.event ? 1.05 : 1);
        gl.uniform2f(uniform('u_anchor'),coord.x,coord.y);
        gl.uniform1f(uniform('u_meter_scale'),coord.meterInMercatorCoordinateUnits());
        gl.uniform1f(uniform('u_model_scale'),scale);
        gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
        gl.vertexAttribPointer(aPosition,3,gl.FLOAT,false,24,0);
        gl.vertexAttribPointer(aColor,3,gl.FLOAT,false,24,12);
        gl.drawArrays(gl.TRIANGLES,0,arrays[target.kind].length/6);
      }
      gl.disableVertexAttribArray(aPosition); gl.disableVertexAttribArray(aColor);
    },
    onRemove(_map,gl) {
      buffers.forEach((buffer) => gl.deleteBuffer(buffer));
      programs.forEach((item) => gl.deleteProgram(item));
      buffers.clear(); programs.clear(); glContext=null;
      const disposedMaterials = new Set();
      Object.values(geometries).forEach((group) => group.traverse((mesh) => {
        if (!mesh.isMesh) return;
        mesh.geometry.dispose();
        if (!disposedMaterials.has(mesh.material)) { mesh.material.dispose(); disposedMaterials.add(mesh.material); }
      }));
    },
  };
  map.addLayer(layer);
  return {
    setLandmarks(next) { landmarks=next; if (glContext) map.triggerRepaint(); },
    setEvents(next) { events=next; if (glContext) map.triggerRepaint(); },
  };
}
