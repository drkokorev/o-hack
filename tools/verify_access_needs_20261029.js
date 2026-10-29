// Real DOM and HTTP against the local rules server; synthetic data only.
async (page) => {
  const checks = [];
  const check = (ok, name) => { if (!ok) throw new Error(name); checks.push(name); };
  const idle = () => page.waitForFunction(() => !document.querySelector('#send').disabled, null, {timeout:120000});
  const send = async text => {
    await page.locator('#text').fill(text);
    await page.locator('#ask').evaluate(form => form.requestSubmit());
    await idle();
  };
  const base = new URL(page.url()).origin;
  await page.route('https://ipinfo.io/**', route => route.fulfill({json:{}}));
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base + '/static/favicon.svg');
  await page.evaluate(() => {sessionStorage.clear();localStorage.setItem('odin.tour.v2','seen');});
  await page.goto(base + '/'); await idle();
  await send('Из Москвы в Казань с 10 по 15 декабря 2027, 2 взрослых, на инвалидной коляске');
  const reply = page.locator('.msg.bot').last();
  const first = await reply.innerText();
  check(first.includes('не отобраны') && first.includes('не отправлен'), 'access is explicitly unverified');
  check(first.includes('2 взрослых') && !first.includes('детей не указаны'), 'only stated travellers are shown');
  await page.locator('.reply-results').last().click();
  check((await page.locator('#view').innerText()).includes('Условия доступности не проверены'), 'warning is visible next to cards');
  check(!(await page.locator('#view').innerText()).includes('Рекомендую'), 'cards do not recommend an unchecked accessible option');
  const stored = await page.evaluate(() => sessionStorage.getItem('odin.trip.v1') || '');
  check(!stored.includes('инвалидной коляске') && !stored.includes('поездка с инвалидной коляской'), 'sensitive request and reply are not saved in browser recovery');
  await page.locator('#text').fill('Мой диагноз и данные о здоровье');
  const draft = await page.evaluate(() => JSON.parse(sessionStorage.getItem('odin.trip.v1')).draft);
  check(!draft, 'recognised sensitive draft is not persisted');
  await page.locator('#text').fill('');
  await page.reload(); await idle();
  check((await page.locator('.msg.bot').last().innerText()).includes('не отобраны'), 'warning is restored from current session');
  check((await page.locator('.msg.user').last().innerText()).includes('не сохранены'), 'sensitive user message stays redacted after restore');
  await page.setViewportSize({width:390,height:844});
  const size = await page.evaluate(() => ({viewport:innerWidth, content:document.documentElement.scrollWidth}));
  check(size.content <= size.viewport, 'accessibility notice fits mobile viewport');
  return {checks};
}
