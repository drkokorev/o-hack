// Run with playwright-cli against a local rules-mode server.
async (page) => {
  const base=new URL(page.url()).origin, failures=[], external=[];
  await page.unrouteAll({behavior:'wait'});
  page.on('pageerror',e=>failures.push(e.message));
  await page.route('**/*',route=>{
    const url=route.request().url();
    if (/^https?:/.test(url) && !url.startsWith(base+'/')) {external.push(url);return route.abort();}
    return route.continue();
  });
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base+'/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  await page.waitForFunction(()=>{
    const models=tripMap.getView()?.models || [];
    return ['tower','spire','race'].every(name=>models.includes(name));
  },null,{timeout:30000});
  await page.waitForFunction(()=>performance.getEntriesByType('resource').some(x=>x.name.includes('earth-blue-marble') && x.responseEnd));
  await page.waitForTimeout(800);
  const desktop=await page.evaluate(()=>tripMap.getView());
  if (desktop.projection!=='globe') throw Error('Globe projection is missing');
  const canvas=await page.locator('.map-canvas').boundingBox();
  await page.mouse.move(canvas.x+canvas.width*.36,canvas.y+canvas.height*.68);
  await page.mouse.down(); await page.mouse.move(canvas.x+canvas.width*.42,canvas.y+canvas.height*.68,{steps:8}); await page.mouse.up();
  await page.waitForTimeout(700);
  const moved=await page.evaluate(()=>tripMap.getView());
  if (Math.abs(desktop.center[0]-moved.center[0])<.2) throw Error('Globe did not rotate by dragging');
  await page.getByRole('button',{name:'Париж: Эйфелева башня'}).click();
  if (!await page.getByText('Хотите посетить это место?').isVisible()) throw Error('Paris marker lost its location after rotating');
  await page.evaluate(()=>tripMap.setCountry('MX',true));
  await page.waitForFunction(()=>Math.abs(tripMap.getView().center[0]+102.289448)<.01);
  await page.waitForTimeout(600);
  if (!await page.getByText('Формула-1',{exact:true}).count()) throw Error('Race label is not visible in Mexico');
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.models?.length===3,null,{timeout:30000});
  await page.waitForTimeout(800);
  if (await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('Mobile layout overflows');
  await page.setViewportSize({width:320,height:700});
  if (await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('Small mobile layout overflows');
  if (external.length) throw Error('External requests: '+external.join(', '));
  if (failures.length) throw Error('JavaScript errors: '+failures.join('; '));
  await page.unroute('**/*');
  await page.setViewportSize({width:1440,height:900});
  let blockedEarth=0, blockedModels=0;
  await page.route('**/earth-blue-marble-200410.jpg*',route=>{blockedEarth++; return route.fulfill({status:503,body:'unavailable'});});
  await page.route('**/*.glb',route=>{blockedModels++; return route.fulfill({status:503,body:'unavailable'});});
  await page.goto(base+'/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  await page.getByRole('button',{name:'Париж: Эйфелева башня'}).waitFor({timeout:30000});
  await page.getByRole('button',{name:'Париж: Эйфелева башня'}).click();
  if (!await page.getByText('Хотите посетить это место?').isVisible()) throw Error('Artwork failure broke selection');
  await page.waitForTimeout(1200);
  if (blockedEarth!==1 || blockedModels!==3) throw Error(`Fallback was not exercised: earth=${blockedEarth}, models=${blockedModels}`);
  if (failures.length) throw Error('JavaScript errors in fallback: '+failures.join('; '));
  await page.unrouteAll({behavior:'wait'});
  return {localAssets:'pass',loadedModels:desktop.models,desktop:'pass',rotateAndSelect:'pass',mexico:'pass',mobile:'pass',offlineArtworkFallback:'pass',externalRequests:external,errors:failures};
}
