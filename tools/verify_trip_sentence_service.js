// The sentence must retain the existing single-date service flow.
async page=>{
  const checks=[],ok=(v,n)=>{if(!v)throw Error(n);checks.push(n);};
  await page.setViewportSize({width:1440,height:960});
  await page.locator('#text').fill('Нужен только авиабилет из Москвы в Казань на 15 ноября 2026, один взрослый');
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/chat'&&r.request().method()==='POST');
  await page.locator('#send').click();const data=await(await response).json();
  await page.waitForFunction(()=>!document.getElementById('send').disabled);
  ok(data.trip_summary.search_scope==='flight_only','request is a standalone flight');
  if(await page.locator('#trip-context-toggle').getAttribute('aria-expanded')!=='true')await page.locator('#trip-context-toggle').click();
  await page.locator('[data-trip-field="dates"]').click();
  ok((await page.locator('.date-picker-note').innerText())==='Выберите день поездки.','summary date opens the single-day calendar');
  const next=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/chat'&&r.request().method()==='POST');
  await page.locator('[data-date="2026-11-16"]').click();const changed=await(await next).json();
  await page.waitForFunction(()=>!document.getElementById('send').disabled);
  ok(changed.trip_summary.date_from==='2026-11-16'&&changed.trip_summary.origin===data.trip_summary.origin&&changed.trip_summary.destination===data.trip_summary.destination&&changed.trip_summary.search_scope==='flight_only','one click changes only the service date');
  await page.locator('#reset').click();await page.locator('#reset-confirm').click();
  await page.waitForFunction(()=>!document.getElementById('send').disabled);
  return {status:'PASS',checks};
}
