// Screen-space placement shared by the application and the review globe.
export function selectLandmarks(map, places, width, height) {
  const zoom=map.getZoom(),center=map.getCenter(),mobile=width<650;
  if(zoom>=11)return [];
  const overview=zoom<2.8,size=overview?(mobile?58:72):(mobile?80:96);
  const max=overview?(mobile?8:18):(mobile?14:26);
  const rad=Math.PI/180,lat=center.lat*rad;
  const candidates=[];
  for(const place of places){
    if(map.getProjection?.().type==='globe'){
      const dot=Math.sin(lat)*Math.sin(place.lat*rad)+Math.cos(lat)*Math.cos(place.lat*rad)*Math.cos((place.lon-center.lng)*rad);
      if(dot<.08)continue;
    }
    const point=map.project([place.lon,place.lat]);
    if(point.x<size*.55||point.x>width-size*.55||point.y<size+8||point.y>height-12)continue;
    const distance=Math.hypot((point.x-width/2)/width,(point.y-height/2)/height);
    candidates.push({...place,point,markerSize:size,overview,score:(place.priority||60)-distance*12+(!overview&&distance<.015?150:0)});
  }
  candidates.sort((a,b)=>b.score-a.score||a.icon.localeCompare(b.icon));
  const selected=[];
  for(const place of candidates){
    const box={left:place.point.x-size*.52,right:place.point.x+size*.52,top:place.point.y-size-10,bottom:place.point.y+12};
    if(selected.some(s=>box.left<s.box.right&&box.right>s.box.left&&box.top<s.box.bottom&&box.bottom>s.box.top))continue;
    selected.push({...place,box});if(selected.length>=max)break;
  }
  return selected;
}
