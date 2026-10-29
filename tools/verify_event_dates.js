// Run with playwright-cli run-code --filename after opening the local app.
// Uses real catalog/UI/API; no fabricated event or server responses.
async (page) => {
  const checks=[], errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const assert=(value,label)=>{if(!value)throw Error(label);checks.push(label);};
  const base=new URL(page.url()).origin;
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1440,height:960});
  async function choose(name){
    await page.goto(base+'/static/favicon.svg');
    await page.evaluate(()=>{sessionStorage.clear();localStorage.setItem('odin.tour.v2','seen');});
    await page.goto(base+'/');
    await page.waitForFunction(()=>tripMap.getView()?.earth===true&&!busy);
    await page.getByRole('combobox',{name:'Тип мест'}).selectOption('event');
    await page.evaluate(()=>tripMap.setCountry('AE',true));
    await page.getByRole('button',{name:'Приблизить карту',exact:true}).dblclick();
    await page.getByRole('button',{name:/^Дубай: .*событий/}).click();
    await page.getByRole('button',{name:new RegExp('^'+name+' Дубай')}).click();
    await page.getByRole('button',{name:'Хочу на событие',exact:true}).click();
    await page.waitForFunction(()=>lastData?.trip_summary?.selected_event&&!busy);
    return page.evaluate(()=>lastData.trip_summary);
  }
  const short=await choose('Dubai Design Week');
  assert(short.destination==='Дубай'&&short.date_from==='2026-11-03'&&short.date_to==='2026-11-09','short event fills city and full travel range');
  assert((await page.locator('[data-trip-field="dates"]').innerText()).includes('3 ноя — 9 ноя 2026'),'sentence displays selected dates');
  await page.locator('[data-trip-field="dates"]').click();
  assert(JSON.stringify(await page.locator('.range-edge').evaluateAll(nodes=>nodes.map(n=>n.dataset.date)))==='["2026-11-03","2026-11-09"]','calendar prefills the same dates');
  assert((await page.locator('.date-picker-event').innerText()).includes('Dubai Design Week'),'calendar explains the event context');
  await page.screenshot({path:'output/playwright/event-calendar.png'});
  await page.getByRole('button',{name:'Закрыть календарь',exact:true}).click();
  await page.reload();
  await page.waitForFunction(()=>lastData?.trip_summary?.selected_event&&!busy);
  assert(JSON.stringify(await page.evaluate(()=>lastData.trip_summary))===JSON.stringify(short),'reload restores event and dates without resending');
  await page.setViewportSize({width:390,height:844});
  assert((await page.locator('#trip-context-toggle').innerText()).includes('Дубай'),'mobile compact summary shows city');
  await page.locator('#trip-context-toggle').click();
  assert(await page.locator('[data-trip-field="dates"]').isVisible(),'mobile expands editable dates');
  await page.screenshot({path:'output/playwright/event-mobile.png'});
  await page.setViewportSize({width:1440,height:960});
  const long=await choose('Global Village');
  assert(long.destination==='Дубай'&&!long.date_from&&!long.date_to,'long season asks visiting days without a months-long stay');
  assert((await page.locator('[data-trip-field="dates"]').innerText()).includes('1 мая 2027'),'long event fills the date field with its known period');
  await page.locator('[data-trip-field="dates"]').click();
  assert((await page.locator('.date-picker-event').innerText()).includes('Global Village'),'long event period remains visible in calendar');
  assert((await page.locator('.range-edge').count())<=1,'long event does not prefill a complete long stay');
  await page.screenshot({path:'output/playwright/event-season.png'});
  assert(!errors.length,'no browser script errors');
  return {kind:'real_browser_event_flow',model:'rules',checks,errors,short_event:short.selected_event.id,
    short_dates:[short.date_from,short.date_to],long_event:long.selected_event.id};
}
