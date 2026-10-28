/* Geographic Blue Marble imagery rendered on the same MapLibre globe.
   Source: NASA Earth Observatory, Blue Marble Next Generation, October 2004.
   The image is local and is never used to infer points or country borders. */
// Begin decoding while the map itself is starting; no external network needed.
export async function prepareEarthImage(imageUrl) {
  const sourceImage=new Image(); sourceImage.decoding='async'; sourceImage.src=imageUrl;
  await sourceImage.decode(); return sourceImage;
}

export async function addEarthSurface(map, imageOrUrl) {
  const sourceImage=typeof imageOrUrl==='string' ? await prepareEarthImage(imageOrUrl) : imageOrUrl;
  if (!map.getLayer('land')) return null;

  // An indexed mesh reuses each geographic vertex instead of calculating and
  // transferring six copies. Separate pole vertices retain correct image UVs.
  const step=2.5, columns=145, rows=69, cells=(columns-1)*(rows-1), polar=(columns-1);
  const values=new Float32Array((columns*rows+polar*2)*8);
  const indices=new Uint16Array(cells*6+polar*6);
  const rad=Math.PI/180; let v=0, ix=0;
  const mercatorY=(latitude)=>(1-Math.log(Math.tan(Math.PI/4+latitude*rad/2))/Math.PI)/2;
  function vertex(lon,lat,pole=0) {
    const lambda=lon*rad,phi=lat*rad;
    values[v++]=(lon+180)/360; values[v++]=mercatorY(lat);
    values[v++]=(lon+180)/360; values[v++]=pole ? (pole<0 ? 0 : 1) : (90-lat)/180;
    values[v++]=pole ? 0 : Math.cos(phi)*Math.cos(lambda);
    values[v++]=pole ? 0 : Math.cos(phi)*Math.sin(lambda);
    values[v++]=pole ? (pole<0 ? 1 : -1) : Math.sin(phi); values[v++]=pole;
  }
  for(let y=0;y<rows;y++) for(let x=0;x<columns;x++) vertex(-180+x*step,-85+y*step);
  for(let y=0;y<rows-1;y++) for(let x=0;x<columns-1;x++) {
    const a=y*columns+x,b=a+1,c=a+1+columns,d=a+columns;
    indices[ix++]=a;indices[ix++]=b;indices[ix++]=c;
    indices[ix++]=a;indices[ix++]=c;indices[ix++]=d;
  }
  const northPoleStart=columns*rows,southPoleStart=northPoleStart+polar;
  for(let x=0;x<polar;x++) vertex(-180+(x+.5)*step,85,-32768);
  for(let x=0;x<polar;x++) vertex(-180+(x+.5)*step,-85,32768);
  for(let x=0;x<polar;x++) {
    const top=(rows-1)*columns+x;
    indices[ix++]=top;indices[ix++]=top+1;indices[ix++]=northPoleStart+x;
    indices[ix++]=x;indices[ix++]=southPoleStart+x;indices[ix++]=x+1;
  }
  const programs=new Map(), locations=new Map(); let buffer, indexBuffer, texture, style='satellite';
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
      uniform sampler2D u_earth; uniform vec3 u_view; uniform vec3 u_light; uniform float u_alpha; uniform float u_map;
      void main(){
        vec3 source=texture(u_earth,v_uv).rgb;
        float continent=smoothstep(.065,.16,max(source.r,source.g));
        vec3 normal=normalize(v_normal);
        float facing=clamp(dot(normal,u_view),0.0,1.0);
        float rim=pow(1.0-facing,2.1);
        vec3 color;
        if (u_map < .5) {
          // Снимок ярче и сочнее, чем исходный NASA: на чёрном космосе тёмная Земля теряется
          vec3 water=vec3(.05,.27,.42)+source*.35;
          vec3 land=pow(source,vec3(.78))*vec3(1.12,1.2,1.05)+vec3(.04,.05,.03);
          float illumination=.72+.38*max(0.0,dot(normal,u_light));
          color=mix(water,land,continent)*illumination;
          vec3 halfway=normalize(u_light+u_view);
          color+=vec3(1.0)*pow(max(0.0,dot(normal,halfway)),40.0)*.12;
          color=mix(color,vec3(.55,.80,1.0),rim*.38);
        } else {
          // Схематичная карта в духе Apple Maps: природные зоны снимка перекрашены в чистые цвета
          float lum=dot(source,vec3(.3,.59,.11));
          float ice=smoothstep(.5,.75,lum)*(1.0-smoothstep(.06,.18,source.r-source.b));
          float desert=smoothstep(.27,.45,lum)*smoothstep(.08,.22,source.r-source.b)*(1.0-ice);
          float forest=1.0-smoothstep(.07,.2,lum);
          vec3 land=mix(vec3(.67,.84,.48),vec3(.39,.64,.34),forest);
          land=mix(land,vec3(.91,.86,.71),desert);
          land=mix(land,vec3(.97,.98,1.0),ice);
          float shallow=smoothstep(.04,.13,source.g+source.b*.5);
          vec3 water=mix(vec3(.16,.47,.72),vec3(.37,.68,.85),shallow);
          float diffuse=max(0.0,dot(normal,u_light));
          color=mix(water,land,continent)*(.80+.24*diffuse);
          vec3 halfway=normalize(u_light+u_view);
          color+=vec3(1.0)*pow(max(0.0,dot(normal,halfway)),36.0)*.07;   // глянцевый блик
          color=mix(color,vec3(.80,.92,1.0),rim*.25);                     // светлый край атмосферы
        }
        fragColor=vec4(color,u_alpha);
      }`);
    const program=gl.createProgram(); gl.attachShader(program,vs); gl.attachShader(program,fs); gl.linkProgram(program);
    gl.deleteShader(vs); gl.deleteShader(fs);
    if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    locations.set(program,{uniforms:new Map(),attributes:Object.fromEntries(['a_position','a_uv','a_normal','a_pole'].map(name=>[name,gl.getAttribLocation(program,name)]))});
    programs.set(description.variantName,program); return program;
  }
  map.addLayer({id:'earth-imagery',type:'custom',
    onAdd(_map,gl) {
      buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,values,gl.STATIC_DRAW);
      indexBuffer=gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);
      const limit=gl.getParameter(gl.MAX_TEXTURE_SIZE);
      let image=sourceImage;
      if (sourceImage.width>limit || sourceImage.height>limit) {
        const factor=Math.min(limit/sourceImage.width,limit/sourceImage.height);
        const canvas=document.createElement('canvas');
        canvas.width=Math.round(sourceImage.width*factor);canvas.height=Math.round(sourceImage.height*factor);
        canvas.getContext('2d').drawImage(sourceImage,0,0,canvas.width,canvas.height);image=canvas;
      }
      texture=gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,texture);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
    },
    render(gl,args) {
      const alpha=Math.max(0,Math.min(1,(5-map.getZoom())/1.5));
      if (!alpha) return;
      const p=getProgram(gl,args.shaderData), projection=args.defaultProjectionData;
      gl.useProgram(p); const cached=locations.get(p); const u=(name)=>{if(!cached.uniforms.has(name))cached.uniforms.set(name,gl.getUniformLocation(p,name));return cached.uniforms.get(name);};
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
      gl.uniform1f(u('u_map'),style==='map' ? 1 : 0);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D,texture); gl.uniform1i(u('u_earth'),0);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
      gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      const pos=cached.attributes['a_position'], uv=cached.attributes['a_uv'], normal=cached.attributes['a_normal'], pole=cached.attributes['a_pole'];
      gl.enableVertexAttribArray(pos); gl.enableVertexAttribArray(uv); gl.enableVertexAttribArray(normal); gl.enableVertexAttribArray(pole);
      gl.vertexAttribPointer(pos,2,gl.FLOAT,false,32,0); gl.vertexAttribPointer(uv,2,gl.FLOAT,false,32,8);
      gl.vertexAttribPointer(normal,3,gl.FLOAT,false,32,16); gl.vertexAttribPointer(pole,1,gl.FLOAT,false,32,28);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);
      gl.drawElements(gl.TRIANGLES,indices.length,gl.UNSIGNED_SHORT,0);
      gl.disableVertexAttribArray(pos); gl.disableVertexAttribArray(uv); gl.disableVertexAttribArray(normal); gl.disableVertexAttribArray(pole);
    },
    onRemove(_map,gl) { gl.deleteBuffer(buffer); gl.deleteBuffer(indexBuffer); gl.deleteTexture(texture); programs.forEach((p)=>gl.deleteProgram(p)); programs.clear(); locations.clear(); },
  },'land');
  map.setPaintProperty('land','fill-opacity',['interpolate',['linear'],['zoom'],0,.055,3.5,.055,5,1]);
  map.addLayer({id:'country-outlines',type:'line',source:'countries',
    paint:{'line-color':'#d6ead7','line-opacity':['interpolate',['linear'],['zoom'],0,.28,5,.4,8,.18],
      'line-width':['interpolate',['linear'],['zoom'],0,.5,5,1,10,.6]}},'trip-route');
  // Вид поверхности: «satellite» — снимок как есть, «map» — схематичная карта по тем же природным зонам
  return {
    setStyle(next) {
      style=next;
      map.triggerRepaint();
    },
  };
}
