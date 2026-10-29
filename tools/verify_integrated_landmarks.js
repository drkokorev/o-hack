// Check all 32 supplied files through the actual globe renderer and detail cards.
async(page)=>{
  const base='http://127.0.0.1:18191',errors=[],requests=[],checked=[];
  await page.unrouteAll({behavior:'wait'});await page.emulateMedia({reducedMotion:'reduce'});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(/models\/landmarks\/.*\.glb|vendor\/three\/draco/.test(r.url()))requests.push({path:new URL(r.url()).pathname,status:r.status(),local:new URL(r.url()).origin===base});});
  await page.setViewportSize({width:1440,height:960});await page.goto(base+'/static/favicon.svg');
  await page.evaluate(()=>{sessionStorage.clear();localStorage.setItem('odin.tour.v2','seen');});await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.earth,null,{timeout:45000});
  const {landmarks}=await(await page.request.get(base+'/static/landmarks.json')).json();
  if(landmarks.length!==32)throw Error('Expected exactly 32 supplied miniatures');
  await page.locator('.map-kind').selectOption('attraction');
  for(const place of landmarks){
    await page.evaluate(p=>tripMap.draw({targets:[{lat:p.lat,lon:p.lon}]}),place);
    await page.waitForFunction(id=>tripMap.getView().models.includes(id),place.icon,{timeout:20000});
    const marker=page.getByRole('button',{name:`${place.city}: ${place.name}`,exact:true});
    await marker.waitFor({state:'visible',timeout:10000});await marker.click();
    if(!(await page.locator('.map-pop strong').first().textContent()).includes(place.name))throw Error('Wrong detail '+place.icon);
    await page.locator('.maplibregl-popup-close-button').click();checked.push(place.icon);
    if(['opera','great_wall','golden_gate'].includes(place.icon))await page.screenshot({path:`output/playwright/integrated-${place.icon}.png`,animations:'disabled'});
  }
  const loaded=await page.evaluate(()=>tripMap.getView().models);
  if(errors.length||requests.some(r=>!r.local||r.status>=400))throw Error(JSON.stringify({errors,requests}));
  await page.getByRole('button',{name:'К глобусу',exact:true}).click();
  await page.screenshot({path:'output/playwright/integrated-world-32.png',animations:'disabled'});
  return {checked,loaded,requests,errors,rendering:'actual shared WebGL layer; every model decoded and every place card opened'};
}
