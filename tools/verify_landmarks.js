// Run with playwright-cli against the local application, with no model key.
async (page) => {
  const base = new URL(page.url()).origin, errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base + '/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  const tower = page.getByRole('button',{name:'Париж: Эйфелева башня'});
  await tower.locator('.landmark-hit-area').waitFor({timeout:30000});
  if (await page.locator('canvas.landmark-model').count()) throw Error('Landmarks must be in the globe scene');
  await page.getByLabel('Тип мест').selectOption('attraction');
  if (await page.locator('.event-marker').count()) throw Error('Attractions filter retained events');
  await page.getByLabel('Тип мест').selectOption('all');
  await tower.click();
  if (!await page.getByText('Хотите посетить это место?').isVisible()) throw Error('Landmark action missing');
  const parisResponse = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByRole('button',{name:'Выбрать город'}).click();
  const paris = await (await parisResponse).json();
  if (paris.trip_summary.destination !== 'Париж') throw Error('Paris selection was not understood');

  await page.goto(base + '/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  await page.waitForFunction(() => tripMap.getView()?.projection === 'globe');
  await page.evaluate(() => tripMap.setCountry('MX',true));
  await page.waitForFunction(() => Math.abs(tripMap.getView().center[0] + 102.289448) < .01);
  const nearest = page.locator('.event-marker.has-3d:not([hidden])').first();
  await nearest.waitFor({timeout:30000});
  await nearest.click();
  const mexicoChoice = page.locator('.map-pop').getByRole('button',{name:/Мехико · Формула-1.*30 октября/});
  if (!await mexicoChoice.isVisible()) throw Error('Mexico model opened a different city');
  await mexicoChoice.click();
  if (!await page.getByText(/Координата автодрома имени братьев Родригес/).isVisible()) throw Error('Circuit location not disclosed');
  if (!await page.getByText('30 октября — 1 ноября 2026',{exact:true}).isVisible()) throw Error('Next Mexico date is missing');
  const eventResponse = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByRole('button',{name:'Хочу на событие'}).click();
  const event = await (await eventResponse).json();
  if (!event.session_id) throw Error('Event selection did not reach chat');

  await page.goto(base + '/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  const point = await page.evaluate(() => fetch('/api/map/points?kind=hotel&destination_id=yaroslavl&limit=1')
    .then(r=>r.json()).then(d=>d.items[0]));
  await page.evaluate(point => tripMap.showPoint(point), point);
  await page.getByRole('button',{name:'Выбрать этот отель'}).waitFor({timeout:30000});
  const hotelResponse = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByRole('button',{name:'Выбрать этот отель'}).click();
  const hotel = await (await hotelResponse).json();
  if (!hotel.map_selection?.accepted || hotel.map_selection.id !== point.id) throw Error('Hotel identity was not preserved');

  await page.setViewportSize({width:375,height:812});
  await page.goto(base + '/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Mobile layout overflows');
  if (errors.length) throw Error('JavaScript errors: ' + errors.join('; '));
  return {paris:'pass', mexico:'pass', exactHotel:'pass', filters:'pass', mobile:'pass', errors};
}
