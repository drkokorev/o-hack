async (page) => {
 const base=new URL(page.url()).origin;
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.setViewportSize({width:1440,height:900});
 await page.goto(base+'/');
 await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
 await page.waitForFunction(()=>tripMap.getView()?.projection==='globe');
 await page.evaluate(()=>tripMap.setCountry('RU',true));
 await page.waitForFunction(()=>Math.abs(tripMap.getView().center[0]-44.686469)<.01);
 await page.waitForTimeout(500);
 const canvas=await page.locator('.map-canvas').boundingBox();
 let text=null;
 for(const [x,y] of [[.5,.55],[.55,.6],[.6,.5],[.45,.55],[.65,.45]]) {
   await page.mouse.click(canvas.x+canvas.width*x,canvas.y+canvas.height*y);
   text=await page.locator('.map-pop').last().innerText().catch(()=>null);
   if(text?.includes('Россия')&&text?.includes('Хотите поехать сюда?')) break;
 }
 if (!text?.includes('Россия') || !text?.includes('Хотите поехать сюда?')) throw Error('Country selection unavailable: '+text);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST');
 await page.locator('.map-pop').getByRole('button',{name:'Хочу сюда'}).click();
 const result=await (await response).json();
 if(!result.understood.some(x=>x.includes('Россия'))) throw Error('Country was not understood');
 return {country:'Россия',status:'pass'};
}
