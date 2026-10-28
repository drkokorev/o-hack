/* A translucent, subdivided surface gives the globe a soft terminator while
   MapLibre remains responsible for geography, projection and hit testing. */
export function addGlobeShading(map) {
  const vertices=[];
  const mercatorY=(lat) => (1-Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))/Math.PI)/2;
  function vertex(lon,lat) {
    const lambda=lon*Math.PI/180, phi=lat*Math.PI/180;
    vertices.push((lon+180)/360,mercatorY(lat),Math.cos(phi)*Math.cos(lambda),Math.cos(phi)*Math.sin(lambda),Math.sin(phi));
  }
  for (let lat=-85;lat<85;lat+=5) for (let lon=-180;lon<180;lon+=5) {
    const north=Math.min(lat+5,85), east=lon+5;
    vertex(lon,lat); vertex(east,lat); vertex(east,north);
    vertex(lon,lat); vertex(east,north); vertex(lon,north);
  }
  const programs=new Map(); let buffer;
  function compile(gl,type,source) {
    const s=gl.createShader(type); gl.shaderSource(s,source); gl.compileShader(s);
    if (!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function getProgram(gl,desc) {
    if (programs.has(desc.variantName)) return programs.get(desc.variantName);
    const vs=compile(gl,gl.VERTEX_SHADER,`#version 300 es\n${desc.vertexShaderPrelude}\n${desc.define}
      in vec2 a_position; in vec3 a_normal; out float v_dark; uniform vec3 u_view;
      void main() { float facing=max(0.0,dot(a_normal,u_view));
        v_dark=pow(1.0-facing,.8); gl_Position=projectTile(a_position); }`);
    const fs=compile(gl,gl.FRAGMENT_SHADER,`#version 300 es\nprecision highp float;
      in float v_dark; out vec4 fragColor; uniform float u_opacity;
      void main() { fragColor=vec4(.08,.23,.22,v_dark*u_opacity); }`);
    const p=gl.createProgram(); gl.attachShader(p,vs); gl.attachShader(p,fs); gl.linkProgram(p);
    gl.deleteShader(vs); gl.deleteShader(fs);
    if (!gl.getProgramParameter(p,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    programs.set(desc.variantName,p); return p;
  }
  map.addLayer({id:'globe-shading',type:'custom',
    onAdd(_map,gl) { buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STATIC_DRAW); },
    render(gl,args) {
      const opacity=Math.max(0,Math.min(.52,(4-map.getZoom())*.24));
      if (!opacity) return;
      const p=getProgram(gl,args.shaderData), projection=args.defaultProjectionData;
      gl.useProgram(p); const u=(name) => gl.getUniformLocation(p,name);
      gl.uniformMatrix4fv(u('u_projection_fallback_matrix'),false,projection.fallbackMatrix);
      gl.uniformMatrix4fv(u('u_projection_matrix'),false,projection.mainMatrix);
      gl.uniform4f(u('u_projection_tile_mercator_coords'),...projection.tileMercatorCoords);
      gl.uniform4f(u('u_projection_clipping_plane'),...projection.clippingPlane);
      gl.uniform1f(u('u_projection_transition'),projection.projectionTransition);
      const center=map.getCenter(), phi=center.lat*Math.PI/180, lambda=center.lng*Math.PI/180;
      gl.uniform3f(u('u_view'),Math.cos(phi)*Math.cos(lambda),Math.cos(phi)*Math.sin(lambda),Math.sin(phi));
      gl.uniform1f(u('u_opacity'),opacity);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
      gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      const pos=gl.getAttribLocation(p,'a_position'), normal=gl.getAttribLocation(p,'a_normal');
      gl.enableVertexAttribArray(pos); gl.enableVertexAttribArray(normal);
      gl.vertexAttribPointer(pos,2,gl.FLOAT,false,20,0); gl.vertexAttribPointer(normal,3,gl.FLOAT,false,20,8);
      gl.drawArrays(gl.TRIANGLES,0,vertices.length/5);
      gl.disableVertexAttribArray(pos); gl.disableVertexAttribArray(normal);
    },
    onRemove(_map,gl) { gl.deleteBuffer(buffer); programs.forEach((p) => gl.deleteProgram(p)); programs.clear(); },
  },'trip-route');
}
