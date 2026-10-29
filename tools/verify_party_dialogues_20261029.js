// playwright-cli run-code; synthetic conversations against the local rules server.
async (page) => {
  const checks = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const check = (ok, name) => { if (!ok) throw new Error(name); checks.push(name); };
  const idle = () => page.waitForFunction(() => !document.querySelector('#send').disabled, null, {timeout:120000});
  const send = async text => { await page.locator('#text').fill(text); await page.locator('#ask').evaluate(form => form.requestSubmit()); await idle(); };
  const reset = async () => { await page.locator('#reset').click(); await page.locator('#reset-confirm').click(); await idle(); };
  const last = () => page.locator('.msg.bot').last().innerText();
  const stored = () => page.evaluate(() => sessionStorage.getItem('odin.trip.v1') || '');
  const base = new URL(page.url()).origin;
  await page.route('https://ipinfo.io/**', route => route.fulfill({json:{}}));
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base + '/static/favicon.svg');
  await page.evaluate(() => {sessionStorage.clear(); localStorage.setItem('odin.tour.v2','seen');});
  await page.goto(base + '/'); await idle();

  await send('Из Москвы в Казань с 10 по 15 декабря 2027, 2 взрослых');
  check(!(await last()).toLowerCase().includes('детей не указаны'), 'adult-only request does not invent children');
  check(!(await last()).toLowerCase().includes('животн'), 'trip without pets does not introduce an animal');
  await page.locator('#text').fill('без орехов');
  check(!JSON.parse(await stored()).draft, 'recognised dietary draft is not saved');
  await page.locator('#text').fill('');
  await reset();
  await send('Только отель в Казани с 10 по 15 декабря 2027, 2 взрослых, ребёнок');
  await send('на дату заезда 8 месяцев');
  check((await last()).toLowerCase().includes('льготы не проверены'), 'infant age is accepted and child fares are unverified');
  check(!(await stored()).includes('8 месяцев'), 'child age answer is not saved in browser recovery');
  await reset();
  await send('В Сочи из Москвы 10–15 декабря 2027, 2 взрослых и дети');
  await page.locator('#text').fill('2 и 7 лет.');
  check(!JSON.parse(await stored()).draft, 'pending child ages are not saved as a draft');
  await send('2 и 7 лет.');
  check((await last()).toLowerCase().includes('детск'), 'bare two-child age answer continues the dialogue');
  check(!(await stored()).includes('2 и 7 лет'), 'bare child ages are not saved in browser recovery');
  await reset();
  await send('Только отель в Казани с 10 по 15 декабря 2027, 2 взрослых, 2 ребёнка');
  await send('8 месяцев и 7 лет');
  check((await last()).toLowerCase().includes('льготы не проверены'), 'mixed ages at check-in lead to hotel results');
  check(!(await stored()).includes('8 месяцев и 7 лет'), 'mixed child ages are not saved in browser recovery');
  await reset();

  await send('Я беременна, 24 недели, из Москвы в Казань с 10 по 15 декабря 2027, 2 взрослых');
  check((await last()).includes('врач') && (await last()).includes('не проверены'), 'pregnancy gets a qualified warning');
  check(!(await stored()).includes('24 недели') && !(await stored()).includes('Я беременна'), 'sensitive pregnancy message is not saved');
  await page.locator('.reply-results').last().click();
  const pregnancyCards = await page.locator('#view').innerText();
  check(pregnancyCards.includes('страховки') && !pregnancyCards.includes('Рекомендую'), 'cards show unverified pregnancy conditions');
  await page.reload(); await idle();
  check((await page.locator('.msg.user').last().innerText()).includes('не сохранены'), 'sensitive message stays redacted after reload');
  await reset();

  await send('Из Москвы в Казань с 10 по 15 декабря 2027, 2 взрослых, с собакой 9 кг в салоне');
  check((await last()).includes('9 кг') && (await last()).includes('в салоне') && (await last()).includes('не проверены'), 'pet weight and preference are acknowledged without a transport guarantee');
  check(!(await last()).includes('до 8 кг'), 'no universal pet weight threshold is asserted');
  await send('собака 4 кг');
  check((await last()).includes('4 кг'), 'pet weight can be corrected');
  await reset();

  await send('Из Москвы в Казань с 10 по 15 декабря 2027, 2 взрослых, аллергия на арахис и молоко');
  check((await last()).includes('перекрёстного') && (await last()).includes('не отобраны'), 'multiple allergies are unverified, including cross-contact');
  check(!(await stored()).includes('аллергия на арахис'), 'allergy message is not saved in browser recovery');
  await send('арахис больше можно');
  const pageText = await page.locator('body').innerText();
  check(pageText.includes('молок'), 'remaining dietary requirement is visible after correction');
  await page.setViewportSize({width:390,height:844});
  const size = await page.evaluate(() => ({viewport:innerWidth, content:document.documentElement.scrollWidth}));
  check(size.content <= size.viewport, 'long notices fit the mobile viewport');
  check(errors.length === 0, 'no uncaught browser errors');
  return {checks, viewport:size, pageErrors:errors.length};
}
