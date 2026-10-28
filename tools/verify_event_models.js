// Replaces only events.json in the test browser with four separated fixtures.
// Run with playwright-cli against the local rules-mode server.
async (page) => {
  const base=new URL(page.url()).origin, errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.unrouteAll({behavior:'wait'});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1440,height:900});
  const points=[['film','Кино',-15,53],['art','Искусство',30,34],
    ['music','Музыка',29,56],['sport','Спорт',-10,33]];
  const events=points.map(([icon,name,lon,lat])=>({id:'test-'+icon,name,city:name,country:'Тест',lon,lat,
    start:'2027-01-01',end:'2035-01-01',dates:'2027',category:name,source:'Проверка',
    url:'https://example.org',icon}));
  await page.route('**/events.json*',route=>route.fulfill({status:200,contentType:'application/json',
    body:JSON.stringify({checked_at:'2026-10-28',events})}));
  await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.earth===true,null,{timeout:30000});
  await page.getByLabel('Тип мест').selectOption('event');
  await page.evaluate(()=>tripMap.setCountry('FR',true));
  await page.waitForFunction(()=>['film','art','music','sport'].every(kind=>tripMap.getView().models.includes(kind)),
    null,{timeout:45000});
  for (const [,name] of points) {
    const marker=page.getByRole('button',{name:`Событие: ${name}, ${name}`});
    if (!await marker.isVisible() || await marker.evaluate(el=>el.classList.contains('model-pending')))
      throw Error(`Event model is not ready: ${name}`);
    await marker.click();
    if (!await page.locator('.map-pop').getByText(name,{exact:true}).first().isVisible())
      throw Error(`Event model opened the wrong card: ${name}`);
    await page.locator('.maplibregl-popup-close-button').click();
  }
  await page.unrouteAll({behavior:'wait'});
  if(errors.length) throw Error('JavaScript errors: '+errors.join('; '));
  return {models:points.map(([icon])=>icon),cards:'pass',errors};
}
