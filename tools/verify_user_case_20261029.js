// Synthetic user-reported dialogue through the actual browser, without a real booking.
async (page) => {
  const checks = [];
  const check = (value, name) => { if (!value) throw new Error(name); checks.push(name); };
  const idle = () => page.waitForFunction(() => !document.querySelector('#send').disabled, null, {timeout:120000});
  const send = async value => {
    await page.locator('#text').fill(value);
    await page.locator('#ask').evaluate(form => form.requestSubmit());
    await idle();
  };
  await page.route('https://ipinfo.io/**', route => route.fulfill({json:{}}));
  await page.setViewportSize({width: 1440, height: 940});
  const base = new URL(page.url()).origin;
  await page.goto(base + '/static/favicon.svg');
  await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('odin.tour.v2'); });
  await page.goto(base + '/');
  await idle();
  if (await page.locator('#tour-dialog').isVisible()) await page.locator('#tour-skip').click();
  await page.locator('#suggest button').filter({hasText:/^предложи сам$/i}).click();
  await idle();
  let reply = await page.locator('.msg.bot').last().innerText();
  check(!reply.toLowerCase().includes('когда примерно') && reply.toLowerCase().includes('не рассчитаны'), 'start suggestion offers ideas without invented dates or prices');
  await page.goto(base + '/static/favicon.svg');
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(base + '/');
  await idle();
  await send('Хочу в горы, красивый вид и спокойные прогулки из Москвы. Предложи направления.');
  const delegate = page.locator('#suggest button').filter({hasText:/предложи сам/i});
  check(await delegate.count() === 1, 'time prompt offers an actionable suggestion');
  await delegate.click(); await idle();
  reply = await page.locator('.msg.bot').last().innerText();
  check(!reply.toLowerCase().includes('не понял') && reply.toLowerCase().includes('не рассчитаны'), 'delegation returns unpriced ideas');
  await send('с 11.11.2027 по 11.12.2027');
  reply = await page.locator('.msg.bot').last().innerText();
  check(reply.includes('11.11.2027') && reply.includes('11.12.2027'), 'known dates remain visible');
  check(reply.toLowerCase().includes('состав путешественников'), 'missing information is explained');
  await send('Хочу в Байкал (Иркутск)');
  await send('2 взрослых');
  reply = await page.locator('.msg.bot').last().innerText();
  check(reply.toLowerCase().includes('самый недорогой') && reply.includes('₽'), 'minimum price is visible in chat');
  check(reply.toLowerCase().includes('демо') && reply.toLowerCase().includes('бюджет не указан'), 'demo and optional budget are visible');
  await page.locator('.reply-results').last().click();
  check(await page.locator('.package-card').count() > 0, 'trip cards remain accessible');
  return {checks};
}
