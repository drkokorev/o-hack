// Final client-side checks: no real visitor addresses or microphone input.
async(page)=>{
  const checks=[],ok=(value,label)=>{if(!value)throw Error(label);checks.push(label);};
  await page.unrouteAll({behavior:'wait'});
  await page.route('**/api/visitor-city',r=>r.fulfill({json:{city_name:'Moscow',origin:null}}));
  await page.goto('http://127.0.0.1:18191/?embed=1');
  await page.waitForFunction(()=>typeof info!=='undefined'&&info);
  ok(await page.evaluate(()=>approximateCity)===null,'foreign namesake is not auto-filled');
  await page.unroute('**/api/visitor-city');
  await page.route('**/api/visitor-city',r=>r.fulfill({json:{city_name:'Москва',origin:'Москва'}}));
  await page.reload();await page.waitForFunction(()=>typeof info!=='undefined'&&info);
  ok(await page.evaluate(()=>approximateCity)==='Москва','supported origin reaches chat without an IP suffix');
  await page.evaluate(()=>{document.querySelectorAll('dialog[open]').forEach(d=>d.close());window.__selectedDate=null;openTripDates({single:true,today:info.today,onSelect:r=>window.__selectedDate=r});});
  const selected=page.locator('#date-picker-dialog .days button:not([disabled])').first();
  const date=await selected.getAttribute('data-date');await selected.click();
  ok((await page.evaluate(()=>window.__selectedDate)).start===date,'single service date applies in one click');
  await page.locator('#date-picker-dialog').waitFor({state:'detached'});
  ok(true,'single service calendar closes after selection');
  await page.setViewportSize({width:320,height:740});
  ok(await page.locator('.chat-legal a[href="https://db-ip.com/"]').isVisible(),'local city data attribution remains visible in embedded chat');
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'legal links fit a 320 px chat');
  await page.unrouteAll({behavior:'wait'});
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('http://127.0.0.1:18191/');
  return {checks,visitor_city_response_stubbed:true};
}
