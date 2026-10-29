/* Our quiet cartography, using the documented OpenMapTiles schema.
   Tiles and glyphs: OpenFreeMap. Data attribution remains visible on the map.
   Vector data is requested only when approaching a country, not on first paint. */
export const palettes = {
  light: {ocean:'#b9d9eb',land:'#e7eddc',park:'#c7dcad',water:'#a9cfe5',building:'#d8daca',road:'#ffffff',edge:'#c6cdbf',major:'#f5e4ad',text:'#253a49',halo:'#f7faf2',border:'#91a99a',route:'#0e41d2'},
  dark: {ocean:'#142c40',land:'#283b43',park:'#314d44',water:'#18384d',building:'#3a4d54',road:'#56676c',edge:'#26383f',major:'#88947a',text:'#e7eff4',halo:'#22333e',border:'#5e7880',route:'#aac3ff'},
};
export function installBasemap(map, onState) {
  let installed=false, theme='light', mode='earth', failed=false,earthReady=false;
  const min=4;
  const fade=['interpolate',['linear'],['zoom'],4,0,5,1];
  const font=['Noto Sans Regular'];
  const name=['coalesce',['get','name:ru'],['get','name'],['get','name:latin']];
  const definitions = [
    {id:'ground',type:'fill',sourceLayer:'landcover',color:'land'},
    {id:'green',type:'fill',sourceLayer:'landcover',filter:['in',['get','class'],['literal',['wood','grass','scrub']]],color:'park'},
    {id:'park',type:'fill',sourceLayer:'park',color:'park'},
    {id:'water',type:'fill',sourceLayer:'water',color:'water'},
    {id:'waterway',type:'line',sourceLayer:'waterway',minzoom:8,color:'water',width:['interpolate',['linear'],['zoom'],8,.5,14,2,16,5]},
    {id:'building',type:'fill',sourceLayer:'building',minzoom:13,color:'building'},
    {id:'road-edge',type:'line',sourceLayer:'transportation',minzoom:8,color:'edge',filter:['in',['get','class'],['literal',['motorway','trunk','primary','secondary','tertiary','minor','service']]],width:['interpolate',['exponential',1.5],['zoom'],8,.6,12,3,16,12]},
    {id:'road',type:'line',sourceLayer:'transportation',minzoom:8,color:'road',filter:['in',['get','class'],['literal',['motorway','trunk','primary','secondary','tertiary','minor','service']]],width:['interpolate',['exponential',1.5],['zoom'],8,.3,12,1.5,16,9]},
    {id:'major-road',type:'line',sourceLayer:'transportation',minzoom:5,color:'major',filter:['in',['get','class'],['literal',['motorway','trunk','primary']]],width:['interpolate',['exponential',1.4],['zoom'],5,.4,10,1.5,16,8]},
    {id:'path',type:'line',sourceLayer:'transportation',minzoom:14,color:'edge',filter:['in',['get','class'],['literal',['path','track']]],width:1,dash:[2,2]},
    {id:'boundary',type:'line',sourceLayer:'boundary',color:'border',filter:['<=',['get','admin_level'],4],width:.8,dash:[3,2]},
    {id:'city',type:'symbol',sourceLayer:'place',minzoom:4,filter:['in',['get','class'],['literal',['city','town']]],layout:{'text-field':name,'text-font':font,'text-size':['interpolate',['linear'],['zoom'],4,11,10,14],'text-max-width':8,'text-padding':12}},
    {id:'locality',type:'symbol',sourceLayer:'place',minzoom:11,filter:['in',['get','class'],['literal',['village','suburb','neighbourhood']]],layout:{'text-field':name,'text-font':font,'text-size':11,'text-padding':16}},
    {id:'street-name',type:'symbol',sourceLayer:'transportation_name',minzoom:13,layout:{'symbol-placement':'line','text-field':name,'text-font':font,'text-size':11,'text-padding':4,'symbol-spacing':400}},
  ];
  function paint() {
    const p=palettes[theme];
    map.setPaintProperty('ocean','background-color',p.ocean);
    map.setPaintProperty('land','fill-color',p.land);
    map.setPaintProperty('land','fill-outline-color',p.border);
    map.setPaintProperty('land','fill-opacity',earthReady?['interpolate',['linear'],['zoom'],0,.025,3.5,.025,5,1]:1);
    map.setPaintProperty('trip-route','line-color',p.route);
    if (map.getLayer('country-outlines')) map.setPaintProperty('country-outlines','line-color',p.border);
    const backdrop=theme==='dark'?'#17191d':'#f5f6f8';
    map.setSky({'sky-color':backdrop,'horizon-color':backdrop,'fog-color':backdrop,'atmosphere-blend':0});
    if (!installed) return;
    for(const d of definitions) {
      const id='atlas-'+d.id;
      if(d.type==='symbol') {map.setPaintProperty(id,'text-color',p.text);map.setPaintProperty(id,'text-halo-color',p.halo);}
      else map.setPaintProperty(id,d.type+'-color',p[d.color]);
    }
  }
  function ensure() {
    if(installed || map.getZoom()<min) return;
    installed=true;
    onState('loading');
    map.addSource('atlas-tiles',{type:'vector',url:'https://tiles.openfreemap.org/planet',attribution:'<a href="https://openfreemap.org/" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'});
    for(const d of definitions) {
      const layer={id:'atlas-'+d.id,type:d.type,source:'atlas-tiles','source-layer':d.sourceLayer,minzoom:d.minzoom||min,paint:{}};
      if(d.filter) layer.filter=d.filter;
      if(d.type==='symbol') {layer.layout=d.layout;layer.paint={'text-color':palettes[theme].text,'text-halo-color':palettes[theme].halo,'text-halo-width':1.5,'text-opacity':fade};}
      else {layer.paint[d.type+'-color']=palettes[theme][d.color];layer.paint[d.type+'-opacity']=fade;}
      if(d.type==='line') {layer.paint['line-width']=d.width||1;layer.layout={'line-cap':'round','line-join':'round'};if(d.dash)layer.paint['line-dasharray']=d.dash;}
      map.addLayer(layer,'trip-route');
    }
    paint();
  }
  map.on('zoomend',ensure);
  map.on('sourcedata',e=>{if(e.sourceId==='atlas-tiles'&&e.isSourceLoaded){failed=false;onState('ready');}});
  map.on('error',e=>{if(e.sourceId==='atlas-tiles'||/openfreemap/.test(String(e.error?.message))){failed=true;onState('error');}});
  return {setEarthReady(ready){earthReady=ready;paint();},set(nextTheme,nextMode){theme=nextTheme;mode=nextMode;paint();ensure();},getState(){return !installed?'idle':failed?'error':map.isSourceLoaded('atlas-tiles')?'ready':'loading';}};
}
