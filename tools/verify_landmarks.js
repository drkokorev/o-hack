// Open the application with playwright-cli; no real model key is needed.
async (page) => {
 const base = new URL(page.url()).origin;
 await page.unrouteAll({behavior:'ignoreErrors'});
 await page.route('**/vendor/three/*.js', route=>route.continue()); // bypass the HTTP cache
 await page.setViewportSize({width:1440,height:900});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base + '/');await page.getByText(/записей в области/).waitFor({timeout:30000});
 const illustrations=await page.locator('.event-marker svg').count();
 const landmarks=await page.evaluate(()=>fetch('/static/landmarks.json').then(r=>r.json()));
 const models=[];
 for (const place of landmarks.landmarks) {
   await page.evaluate(p=>tripMap.draw({targets:[{name:p.city,lat:p.lat,lon:p.lon}]}),place);
   const canvas=page.getByRole('button',{name:`${place.city}: ${place.name}`}).locator('canvas.landmark-model');
   await canvas.waitFor({timeout:30000});
   await page.waitForFunction(label=>{
     const c=[...document.querySelectorAll('.landmark-marker')].find(e=>e.getAttribute('aria-label')===label)?.querySelector('canvas');
     return c && [...c.getContext('2d').getImageData(0,0,c.width,c.height).data].some((v,i)=>i%4===3 && v>0);
   },`${place.city}: ${place.name}`,{timeout:30000});
   models.push({label:`${place.city}: ${place.name}`,visiblePixels:true});
 }
 if(models.some(m=>!m.visiblePixels))throw Error('Blank landmark: '+JSON.stringify(models));
 if(!illustrations)throw Error('Event illustrations missing');
 if(errors.length)throw Error(errors.join('; '));
 return {models,illustrations,errors};
}
