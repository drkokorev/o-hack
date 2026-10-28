/* Geographic Blue Marble imagery rendered on the same MapLibre globe.
   Source: NASA Earth Observatory, Blue Marble Next Generation, October 2004.
   The image is local and is never used to infer points or country borders. */
export async function addEarthSurface(map, imageUrl) {
  const sourceImage = new Image();
  sourceImage.decoding = 'async';
  sourceImage.src = imageUrl;
  await sourceImage.decode();
  if (!map.getLayer('land')) return null;

  const values = [];
  const rad = Math.PI / 180;
  const mercatorY = (latitude) => (1-Math.log(Math.tan(Math.PI/4+latitude*rad/2))/Math.PI)/2;
  function vertex(lon, lat, pole=0) {
    const lambda=lon*rad, phi=lat*rad;
    values.push((lon+180)/360, mercatorY(lat), (lon+180)/360, pole ? (pole<0 ? 0 : 1) : (90-lat)/180,
      pole ? 0 : Math.cos(phi)*Math.cos(lambda), pole ? 0 : Math.cos(phi)*Math.sin(lambda), pole ? (pole<0 ? 1 : -1) : Math.sin(phi), pole);
  }
  for (let lat=-85; lat<85; lat+=2.5) for (let lon=-180; lon<180; lon+=2.5) {
    const north=Math.min(85,lat+2.5), east=lon+2.5;
    vertex(lon,lat); vertex(east,lat); vertex(east,north);
    vertex(lon,lat); vertex(east,north); vertex(lon,north);
  }
  for (let lon=-180;lon<180;lon+=2.5) {
    vertex(lon,85); vertex(lon+2.5,85); vertex(lon+1.25,85,-32768);
    vertex(lon,-85); vertex(lon+1.25,-85,32768); vertex(lon+2.5,-85);
  }
  const programs=new Map(); let buffer, texture;
  function compile(gl,type,src) {
    const shader=gl.createShader(type); gl.shaderSource(shader,src); gl.compileShader(shader);
    if (!gl.getShaderParameter(shader,gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader));
    return shader;
  }
  function getProgram(gl,description) {
    if (programs.has(description.variantName)) return programs.get(description.variantName);
    const vs=compile(gl,gl.VERTEX_SHADER,`#version 300 es\n${description.vertexShaderPrelude}\n${description.define}
      in vec2 a_position; in vec2 a_uv; in vec3 a_normal; in float a_pole;
      out vec2 v_uv; out vec3 v_normal;
      void main(){ v_uv=a_uv; v_normal=a_normal; gl_Position=projectTile(a_position,vec2(0.0,a_pole)); }`);
    const fs=compile(gl,gl.FRAGMENT_SHADER,`#version 300 es
      precision highp float; in vec2 v_uv; in vec3 v_normal; out vec4 fragColor;
      uniform sampler2D u_earth; uniform vec3 u_view; uniform vec3 u_light; uniform float u_alpha;
      void main(){
        vec3 source=texture(u_earth,v_uv).rgb;
        float continent=smoothstep(.065,.16,max(source.r,source.g));
        vec3 water=vec3(.035,.205,.275)+source*.12;
        vec3 land=source*vec3(.88,.99,.88)+vec3(.045,.055,.035);
        vec3 normal=normalize(v_normal);
        float facing=clamp(dot(normal,u_view),0.0,1.0);
        float illumination=.54+.46*max(0.0,dot(normal,u_light));
        float rim=pow(1.0-facing,2.1);
        vec3 color=mix(water,land,continent)*illumination;
        color=mix(color,vec3(.18,.48,.51),rim*.33);
        fragColor=vec4(color,u_alpha);
      }`);
    const program=gl.createProgram(); gl.attachShader(program,vs); gl.attachShader(program,fs); gl.linkProgram(program);
    gl.deleteShader(vs); gl.deleteShader(fs);
    if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    programs.set(description.variantName,program); return program;
  }
  map.addLayer({id:'earth-imagery',type:'custom',
    onAdd(_map,gl) {
      buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(values),gl.STATIC_DRAW);
      const limit=Math.min(4096,gl.getParameter(gl.MAX_TEXTURE_SIZE));
      const factor=Math.min(1,limit/sourceImage.width,limit/sourceImage.height);
      const canvas=document.createElement('canvas');
      canvas.width=Math.round(sourceImage.width*factor); canvas.height=Math.round(sourceImage.height*factor);
      canvas.getContext('2d').drawImage(sourceImage,0,0,canvas.width,canvas.height);
      texture=gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,texture);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,canvas);
    },
    render(gl,args) {
      const alpha=Math.max(0,Math.min(1,(6-map.getZoom())/2));
      if (!alpha) return;
      const p=getProgram(gl,args.shaderData), projection=args.defaultProjectionData;
      gl.useProgram(p); const u=(name)=>gl.getUniformLocation(p,name);
      gl.uniformMatrix4fv(u('u_projection_fallback_matrix'),false,projection.fallbackMatrix);
      gl.uniformMatrix4fv(u('u_projection_matrix'),false,projection.mainMatrix);
      gl.uniform4f(u('u_projection_tile_mercator_coords'),...projection.tileMercatorCoords);
      gl.uniform4f(u('u_projection_clipping_plane'),...projection.clippingPlane);
      gl.uniform1f(u('u_projection_transition'),projection.projectionTransition);
      const center=map.getCenter(), phi=center.lat*rad, lambda=center.lng*rad;
      const view=[Math.cos(phi)*Math.cos(lambda),Math.cos(phi)*Math.sin(lambda),Math.sin(phi)];
      const east=[-Math.sin(lambda),Math.cos(lambda),0];
      const north=[-Math.sin(phi)*Math.cos(lambda),-Math.sin(phi)*Math.sin(lambda),Math.cos(phi)];
      const light=view.map((v,i)=>v-.42*east[i]+.62*north[i]);
      const length=Math.hypot(...light); gl.uniform3f(u('u_view'),...view);
      gl.uniform3f(u('u_light'),...light.map((v)=>v/length)); gl.uniform1f(u('u_alpha'),alpha);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D,texture); gl.uniform1i(u('u_earth'),0);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
      gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      const pos=gl.getAttribLocation(p,'a_position'), uv=gl.getAttribLocation(p,'a_uv'), normal=gl.getAttribLocation(p,'a_normal'), pole=gl.getAttribLocation(p,'a_pole');
      gl.enableVertexAttribArray(pos); gl.enableVertexAttribArray(uv); gl.enableVertexAttribArray(normal); gl.enableVertexAttribArray(pole);
      gl.vertexAttribPointer(pos,2,gl.FLOAT,false,32,0); gl.vertexAttribPointer(uv,2,gl.FLOAT,false,32,8);
      gl.vertexAttribPointer(normal,3,gl.FLOAT,false,32,16); gl.vertexAttribPointer(pole,1,gl.FLOAT,false,32,28);
      gl.drawArrays(gl.TRIANGLES,0,values.length/8);
      gl.disableVertexAttribArray(pos); gl.disableVertexAttribArray(uv); gl.disableVertexAttribArray(normal); gl.disableVertexAttribArray(pole);
    },
    onRemove(_map,gl) { gl.deleteBuffer(buffer); gl.deleteTexture(texture); programs.forEach((p)=>gl.deleteProgram(p)); programs.clear(); },
  },'land');
  map.setPaintProperty('land','fill-opacity',['interpolate',['linear'],['zoom'],0,.055,4,.055,6,1]);
  map.addLayer({id:'country-outlines',type:'line',source:'countries',
    paint:{'line-color':'#d6ead7','line-opacity':['interpolate',['linear'],['zoom'],0,.28,5,.4,8,.18],
      'line-width':['interpolate',['linear'],['zoom'],0,.5,5,1,10,.6]}},'trip-route');
  return true;
}
