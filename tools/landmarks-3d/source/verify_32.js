async (page) => {
 const root='outputs/odin-landmarks';const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>r.continue());
 await page.setViewportSize({width:1440,height:1100});
 await page.goto('http://127.0.0.1:18135/');
 await page.waitForFunction(()=>window.previewReady?.loaded.length===32,null,{timeout:60000});
 const load=await page.evaluate(()=>window.previewReady);
 const shots=[];
 for(let i=0;i<32;i++){const id=await page.evaluate(i=>window.landmarkPreview.targets[i].kind,i);await page.locator('.card canvas').nth(i).screenshot({path:root+'/previews/'+id+'.png'});shots.push(id);}
 const rotations=[];
 for(const angle of [-180,-90,0,90,180]){
  await page.locator('#rotation').evaluate((el,v)=>{el.value=String(v);el.dispatchEvent(new Event('input',{bubbles:true}));},angle);await page.waitForTimeout(180);
  const sample=await page.evaluate(angle=>({angle,models:window.landmarkPreview.targets.map(t=>{const c=t.canvas,d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let pixels=0;for(let i=3;i<d.length;i+=4)if(d[i]>16)pixels++;return {id:t.kind,pixels,state:c.dataset.modelState}})}),angle);
  if(sample.models.some(m=>m.pixels<500||m.state!=='ready'))throw Error('Blank or failed rotation '+angle);rotations.push(sample);
 }
 await page.locator('#rotation').evaluate(el=>{el.value='0';el.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.getByRole('button',{name:'До',exact:true}).click();
 const beforeCount=await page.locator('.card:visible').count();if(beforeCount!==8)throw Error('Expected 8 baseline cards, got '+beforeCount);
 await page.getByRole('button',{name:'После',exact:true}).click();
 await page.getByRole('button',{name:'Светлый фон',exact:true}).click();await page.screenshot({path:root+'/light-32.png',fullPage:true});
 await page.getByRole('button',{name:'Тёмный фон',exact:true}).click();
 await page.setViewportSize({width:390,height:844});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error('Mobile overflow');
 await page.screenshot({path:root+'/mobile-32.png',fullPage:true});
 await page.setViewportSize({width:1920,height:1550});await page.goto('http://127.0.0.1:18135/?board=1');
 await page.waitForFunction(()=>window.previewReady?.loaded.length===32);await page.screenshot({path:root+'/collection-32-dark.png',fullPage:true});
 await page.setViewportSize({width:1440,height:1000});await page.goto('http://127.0.0.1:18135/globe.html');
 await page.waitForFunction(()=>window.globeReady==='world',null,{timeout:60000});
 const world=[];
 for(const center of [[20,25],[110,30],[-90,25],[140,-25],[60,58]]){
  await page.evaluate(async center=>{window.globePreview.map.jumpTo({center,zoom:1.65});await window.globePreview.render();},center);
  world.push(await page.evaluate(()=>({view:window.globePreview.map.getCenter().toArray(),visible:window.globeVisible,ready:[...document.querySelectorAll('.marker canvas')].every(c=>c.dataset.modelState==='ready')})));
 }
 const individual=[];const ids=await page.evaluate(()=>window.globePreview.places.map(p=>p.icon));
 for(const id of ids){await page.selectOption('#city',id);await page.waitForFunction(id=>window.globeReady===id,id);const visible=await page.evaluate(()=>window.globeVisible);if(!visible.includes(id))throw Error('Selected landmark not visible '+id);individual.push(id);}
 await page.selectOption('#city','');await page.waitForFunction(()=>window.globeReady==='world');await page.screenshot({path:root+'/globe-32.png',fullPage:true});
 if(errors.length)throw Error(errors.join('\n'));
 return {date:'2026-10-29',load,rotationChecks:rotations,baselineCards:beforeCount,mobile:{width:390,overflow},globeViews:world,individualModels:individual,pageErrors:errors};
}
