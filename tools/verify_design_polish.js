// Focused regression for final currency, icons, events and reset (rules or models).
async(page)=>{
  const checks=[],errors=[]; const assert=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);};
  const idle=()=>page.waitForFunction(()=>!document.querySelector('#send').disabled,null,{timeout:90000});
  page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1440,height:960});
  await page.goto('http://127.0.0.1:18191/static/favicon.svg');
  await page.evaluate(()=>{sessionStorage.clear();localStorage.removeItem('odin.places');localStorage.setItem('odin.currency','RUB');localStorage.setItem('odin.tour.v2','seen');});
  await page.goto('http://127.0.0.1:18191/');await idle();
  await page.locator('#text').fill('Хочу на море из Москвы на 7 ночей с 15 июня 2027, двое взрослых, бюджет 180 тысяч рублей, без визы.');
  await page.locator('#ask').evaluate(f=>f.requestSubmit());await idle();
  await page.locator('#view').getByRole('button',{name:'Выбрать Анталья',exact:true}).click();await idle();
  const labels=await page.locator('[data-rub-price]').allTextContents();
  assert(labels.length>3,'date alternatives have sourced ruble values');
  for(const value of ['EUR','USD','EUR']){
    await page.locator('#currency').selectOption(value);
    assert((await page.locator('[data-rub-price]').first().textContent()).includes(value==='EUR'?'€':'$'),'calendar converts '+value);
    await page.evaluate(()=>preferences.apply());
  }
  await page.locator('#currency').selectOption('RUB');
  assert(JSON.stringify(labels)===JSON.stringify(await page.locator('[data-rub-price]').allTextContents()),'calendar currency roundtrip is lossless');
  const favorite=page.locator('[data-save-key]').first();
  assert(await favorite.locator('svg').count()===1,'favorites use outline SVG');
  await favorite.click();assert(await favorite.getAttribute('aria-pressed')==='true','favorite icon updates state');
  await page.locator('#reset').click();await page.locator('#reset-confirm').click();await idle();
  assert(await page.locator('#saved-places').isVisible(),'new trip preserves saved places');
  await page.waitForFunction(()=>tripMap.getView()?.earth,null,{timeout:45000});
  await page.waitForFunction(()=>tripMap.getView()?.zoom<=2,null,{timeout:10000});
  assert(await page.locator('.map-surface').evaluate(e=>e.clientHeight>500),'new trip restores full globe height');
  assert(!(await page.locator('.board').getAttribute('class')).includes('compact'),'new trip leaves compact route layout');
  await page.locator('.map-kind').selectOption('event');
  await page.waitForSelector('.event-medallion:visible',{timeout:25000});
  await page.locator('.event-medallion:visible').first().click();
  if(await page.locator('.map-event-row:visible').count())await page.locator('.map-event-row:visible').first().click();
  assert(await page.locator('.event-story').isVisible(),'event opens an editorial card');
  const eventName=await page.locator('.event-story > strong').textContent();
  const bounds=await page.locator('.maplibregl-popup').boundingBox();
  const mapBounds=await page.locator('.map-canvas').boundingBox();
  assert(bounds.x>=mapBounds.x-1&&bounds.x+bounds.width<=mapBounds.x+mapBounds.width+1,'event card fits globe width');
  await page.screenshot({path:'output/playwright/globe-event-card.png'});
  await page.getByRole('button',{name:'Хочу на событие',exact:true}).click();await idle();
  assert((await page.locator('.msg.bot').last().textContent()).includes(eventName),'event selection preserves exact event context');
  assert((await page.locator('.msg.bot').last().textContent()).includes('Билеты на событие не включены'),'event admission is not sold as travel package');
  await page.setViewportSize({width:390,height:844});
  await page.locator('#reset').click();await page.locator('#reset-confirm').click();await idle();
  await page.locator('[data-panel="map"]').click();
  await page.waitForFunction(()=>tripMap.getView()?.zoom<=2,null,{timeout:10000});
  assert(await page.locator('.map-surface').evaluate(e=>e.clientHeight>=310),'mobile reset restores globe surface');
  assert((await page.locator('.map-kind').inputValue())==='all','new trip resets discovery filter');
  assert(errors.length===0,'no JavaScript exceptions');
  return {checks,eventName,errors};
}
