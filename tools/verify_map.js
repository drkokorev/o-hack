// Run with playwright-cli against a running local application.
async (page) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('http://127.0.0.1:8080/');
  await page.locator('#map svg').waitFor({ timeout: 30000 });
  await page.getByRole('button', { name: 'Весь мир', exact: true }).click();
  await page.getByRole('button', { name: 'Выбрать Нью-Йорк', exact: true }).waitFor();
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw new Error('The main page overflows on a mobile viewport');

  // A host page loads only the map assets and receives a structured selection.
  await page.goto('http://127.0.0.1:8080/health');
  await page.setContent('<!doctype html><html lang="ru"><head><link rel="stylesheet" href="/static/trip-map.css"></head><body><div id="external-map"></div></body></html>');
  await page.addScriptTag({ url: '/static/trip-map.js' });
  await page.evaluate(async () => {
    const [catalog, geography] = await Promise.all([
      fetch('/api/info').then(r => r.json()), fetch('/static/land.geojson').then(r => r.json()),
    ]);
    const map = window.createTripMap({ container: document.getElementById('external-map'),
      onChoose: place => { window.chosenPlace = place; } });
    window.testMap = map;
    map.setData(catalog, geography);
    map.draw();
  });
  await page.getByLabel('Выбрать направление из списка').selectOption({ label: 'Токио' });
  await page.getByRole('button', { name: 'Хочу сюда', exact: true }).click();
  const selected = await page.evaluate(() => window.chosenPlace);
  if (!selected || selected.id !== 'tokyo') throw new Error('Standalone map did not return the catalog place');
  await page.evaluate(() => {
    const { name, lat, lon } = window.chosenPlace;
    window.chosenPlace = null;
    window.testMap.draw({ targets: [{ name, lat, lon }] });
  });
  await page.getByRole('button', { name: 'Выбрать Токио', exact: true }).click();
  await page.getByRole('button', { name: 'Хочу сюда', exact: true }).click();
  if (await page.evaluate(() => window.chosenPlace?.id) !== 'tokyo')
    throw new Error('The route marker lost the catalog identity');
  if (errors.length) throw new Error('Browser exceptions: ' + errors.join('; '));
  return { world: 'passed', mobile: 'passed', standalone: 'passed', selection: 'passed' };
}
