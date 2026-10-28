// Fixture checks access to an event at exactly the same coordinate as a landmark.
async (page) => {
  const base=new URL(page.url()).origin,errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.unrouteAll({behavior:'wait'});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1440,height:900});
  await page.route('**/events.json*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
    checked_at:'2026-10-28',events:[{id:'same-location',name:'Тестовое событие',city:'Париж',country:'Франция',
      lat:48.858297,lon:2.294478,start:'2027-01-01',end:'2035-01-01',dates:'2027',category:'Кино',
      source:'Проверка',url:'https://example.org',icon:'film'}]})}));
  await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.earth===true,null,{timeout:30000});
  await page.evaluate(()=>tripMap.setCountry('FR',true));
  await page.getByRole('button',{name:'Париж: Эйфелева башня'}).click();
  const popup=page.locator('.map-pop'),events=popup.locator('summary').filter({hasText:'События на этом участке: 1'});
  if(!await events.isVisible()) throw Error('The overlapping event has no access in the landmark card');
  await events.click();
  await popup.getByRole('button',{name:/Тестовое событие/}).click();
  if(!await popup.getByText('Тестовое событие',{exact:true}).isVisible()) throw Error('Wrong overlapping event card');
  await page.unrouteAll({behavior:'wait'});
  if(errors.length) throw Error(errors.join('; '));
  return {overlap:'pass',correctCard:'pass',errors};
}
