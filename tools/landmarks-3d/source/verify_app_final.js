async (page) => {
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>r.continue());
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('http://127.0.0.1:18136/');
 await page.getByRole('button',{name:'Весь мир',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('.landmark-model').length>3 && [...document.querySelectorAll('.landmark-model')].every(c=>c.dataset.modelState==='ready'),null,{timeout:60000});
 const desktop=await page.evaluate(()=>({visible:[...document.querySelectorAll('.landmark-marker')].map(x=>x.title),overflow:document.documentElement.scrollWidth>innerWidth}));
 await page.screenshot({path:'outputs/odin-landmarks/application-desktop.png',fullPage:true});
 await page.locator('.landmark-marker').first().click();
 await page.locator('.maplibregl-popup').waitFor();
 const popup=await page.locator('.maplibregl-popup').innerText();
 if(!popup.includes('Выбрать место'))throw Error('Missing landmark action');
 await page.locator('.maplibregl-popup-close-button').click();
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'Весь мир',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('.landmark-model').length>0 && [...document.querySelectorAll('.landmark-model')].every(c=>c.dataset.modelState==='ready'),null,{timeout:60000});
 const mobile=await page.evaluate(()=>({width:innerWidth,visible:[...document.querySelectorAll('.landmark-marker')].map(x=>x.title),overflow:document.documentElement.scrollWidth>innerWidth}));
 await page.screenshot({path:'outputs/odin-landmarks/application-mobile.png',fullPage:true});
 if(mobile.overflow||desktop.overflow||errors.length)throw Error(JSON.stringify({mobile,desktop,errors}));
 return {desktop,mobile,popup,pageErrors:errors};
}
