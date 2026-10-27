// Run with playwright-cli after opening the app; no LLM key is required.
async (page) => {
  const base = new URL(page.url()).origin;
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  async function standalone() {
    await page.goto(base + '/health');
    await page.setContent('<!doctype html><html lang="ru"><head><link rel="stylesheet" href="/static/trip-map.css"></head><body><div id="external-map"></div></body></html>');
    await page.addScriptTag({url:base + '/static/trip-map.js'});
    await page.evaluate(async () => {
      const [info, land] = await Promise.all([fetch('/api/info').then(r => r.json()), fetch('/static/land.geojson').then(r => r.json())]);
      window.testMap = createTripMap({container:document.getElementById('external-map'), onChoose:place => {window.chosenPlace=place;}});
      window.testMap.setData(info, land); window.testMap.draw();
    });
  }
  await page.setViewportSize({width:375,height:812});
  await standalone();
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  await page.getByLabel('Выбрать направление из списка').selectOption({label:'Токио'});
  await page.getByRole('button', {name:'Хочу сюда',exact:true}).click();
  if (await page.evaluate(() => window.chosenPlace?.id) !== 'tokyo') throw new Error('Selection lost its catalog identity');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Standalone map overflows');

  await page.route('**/api/map/catalog', route => route.fulfill({status:503,body:'unavailable'}));
  await standalone();
  await page.getByText('Подробный каталог карты недоступен. Показаны направления приложения.').waitFor({timeout:30000});
  await page.evaluate(() => window.testMap.draw({targets:[]}));
  if (!await page.getByText('Подробный каталог карты недоступен. Показаны направления приложения.').isVisible())
    throw new Error('Fallback status disappeared when redrawn');
  if (errors.length) throw new Error('JavaScript errors: ' + errors.join('; '));
  return {standalone:'pass', selection:'pass', fallback:'pass', mobile:'pass'};
}
