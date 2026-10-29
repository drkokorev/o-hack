// Real WebGL context loss/recovery; one explicit cluster fixture for a click boundary.
async(page)=>{
  const base='http://127.0.0.1:18191',errors=[],checks=[];
  const ok=(condition,name)=>{if(!condition)throw Error(name);checks.push(name);};
  await page.unrouteAll({behavior:'wait'});await page.emulateMedia({reducedMotion:'no-preference'});
  await page.setViewportSize({width:1440,height:960});await page.goto(base+'/static/favicon.svg');
  await page.evaluate(()=>{sessionStorage.clear();localStorage.setItem('odin.tour.v2','seen');localStorage.setItem('odin.globe','earth');localStorage.setItem('odin.theme','light');});
  page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.models.includes('tower'),null,{timeout:45000});
  for(const mode of ['Географическая','Дизайнерская']){
    await page.getByRole('button',{name:mode,exact:true}).click();await page.waitForTimeout(500);
    const available=await page.evaluate(()=>{const gl=document.querySelector('.maplibregl-canvas').getContext('webgl2');window.contextLoss=gl.getExtension('WEBGL_lose_context');contextLoss?.loseContext();return !!contextLoss;});
    ok(available,'context-loss extension available: '+mode);await page.waitForTimeout(800);
    await page.evaluate(()=>contextLoss.restoreContext());
    await page.waitForFunction(()=>{const v=tripMap.getView();return v.earth&&v.surfaceLayer&&v.modelLayer;},null,{timeout:20000});await page.waitForTimeout(1200);
    ok(await page.evaluate(()=>tripMap.getView().projection==='globe'),'surface and 3D layers restored: '+mode);
    await page.screenshot({path:'output/playwright/recovered-'+(mode==='Географическая'?'earth':'designer')+'.png',animations:'disabled'});
  }
  const point=await(await page.request.get(base+'/api/map/point/geonames%3A2988507')).json();
  await page.route('**/api/map/clusters?**',async route=>{
    const response=await route.fetch(),data=await response.json();
    const size=data.cell_degrees;data.items=[{id:`${Math.floor((point.lon+180)/size)}:${Math.floor((point.lat+90)/size)}`,lon:point.lon,lat:point.lat,count:1,representative_id:point.id}];
    await route.fulfill({json:data});
  });
  await page.locator('.map-kind').selectOption('city');
  const singleton=page.locator('.cluster-marker.singleton:visible').first();await singleton.waitFor({timeout:20000});
  const zoom=await page.evaluate(()=>tripMap.getView().zoom);await singleton.click({position:{x:6,y:22}});
  await page.locator('.map-pop strong').filter({hasText:point.name}).waitFor({timeout:15000});
  ok(Math.abs(await page.evaluate(()=>tripMap.getView().zoom)-zoom)<.01,'singleton opens actual city without another zoom');
  ok(await singleton.evaluate(e=>e.getBoundingClientRect().width>=44),'singleton has a 44 px target, including edge click');
  ok(errors.length===0,'no JavaScript exceptions');await page.unrouteAll({behavior:'wait'});
  return {checks,errors,fixture:'one real Paris record as a singleton group; normal renderer and point endpoint'};
}
