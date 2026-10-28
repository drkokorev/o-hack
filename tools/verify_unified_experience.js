// Run with playwright-cli on the isolated rules-mode preview.
async (page) => {
  const base = new URL(page.url()).origin, checks = [], errors = [];
  const check = (ok, name) => { if (!ok) throw Error(name); checks.push(name); };
  await page.unrouteAll({behavior:'wait'});
  await page.route('https://ipinfo.io/**', route => route.fulfill({json:{}}));
  page.on('pageerror', error => errors.push(error.message));
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1440,height:940});
  await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.earth && document.querySelector('#suggest button'));
  const chat = async text => {
    await page.locator('#text').fill(text);
    const response = page.waitForResponse(r=>r.url().endsWith('/api/chat') && r.request().method()==='POST');
    await page.locator('#text').press('Enter');
    const data = await (await response).json();
    await page.waitForFunction(()=>!document.querySelector('#send').disabled);
    return data;
  };
  await chat('В Ярославль');
  await page.locator('.latest-user .message-edit').click();
  const points = await (await page.request.get(base+'/api/map/points?kind=hotel&destination_id=yaroslavl&limit=2')).json();
  const hotel = points.items[1];
  await page.evaluate(point=>tripMap.showPoint(point), hotel);
  const response = page.waitForResponse(r=>r.url().endsWith('/api/chat') && r.request().method()==='POST');
  await page.locator('.map-pop .map-choose').click();
  const selected = await (await response).json();
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  check(selected.map_selection?.accepted && selected.map_selection.id===hotel.id,'exact map hotel reaches server');
  check(await page.locator('.msg.user').count()===2,'map choice creates a new turn while editing');
  check(await page.locator('#edit-banner').isHidden(),'map choice exits editing mode');
  check((await page.locator('#conditions').innerText()).includes(hotel.name),'summary shows selected map hotel');
  await page.locator('#undo').click();
  await page.waitForFunction(()=>document.querySelectorAll('.msg.user').length===1);
  check(!(await page.locator('#conditions').innerText()).includes(hotel.name),'undo removes selected map hotel');
  check((await page.locator('#conditions').innerText()).includes('Ярославль'),'undo retains previous destination');
  const credits = page.locator('.map-credits summary');
  await credits.click();
  check(await page.locator('.map-credits a').first().isVisible(),'model and image sources are accessible');
  for (const [width,height] of [[1440,940],[390,844],[320,700],[844,390]]) {
    await page.setViewportSize({width,height});
    await page.goto(base+'/');
    await page.locator('#suggest button').first().waitFor();
    if (await page.locator('#mobile-map').isVisible()) await page.locator('#mobile-map').click();
    await page.waitForFunction(()=>tripMap.getView()?.earth);
    check(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),`layout ${width}x${height}`);
  }
  await page.goto(base+'/static/widget.html');
  await page.locator('#text').fill('Из Москвы в Казань на семь дней');
  const widgetReply = page.waitForResponse(r=>r.url().endsWith('/api/chat') && r.request().method()==='POST');
  await page.locator('#text').press('Enter');
  const data = await (await widgetReply).json();
  check(data.trip_summary.destination==='Казань' && data.trip_summary.origin==='Москва','widget uses unified dialogue');
  check(errors.length===0,'no JavaScript errors');
  return {passed:checks.length,checks};
}
