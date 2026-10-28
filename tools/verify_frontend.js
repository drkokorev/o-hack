// Open the running application with playwright-cli before running this file.
// The service must run without real model/API keys. No booking or payment occurs.
async (page) => {
  const base = new URL(page.url()).origin;
  await page.unrouteAll({behavior:'ignoreErrors'});
  await page.addInitScript(() => {
    window.SpeechRecognition = class {
      start() { setTimeout(() => { this.onresult?.({resultIndex:0,results:[Object.assign([{transcript:'Хочу в Париж'}],{isFinal:true})]}); this.onend?.(); }, 20); }
      stop() { this.onend?.(); }
    };
  });
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const chat = async text => {
    await page.locator('#text').fill(text);
    const response = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
    await page.locator('#text').press('Enter');
    const result = await (await response).json();
    await page.waitForTimeout(250);
    return result;
  };
  const trigger = async (label, index = 0) => {
    const response = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
    await page.getByRole('button', {name:label, exact:true}).nth(index).click();
    const result = await (await response).json();
    await page.waitForTimeout(250);
    return result;
  };

  await page.setViewportSize({width:1440, height:900});
  await page.goto(base + '/health');
  await page.evaluate(() => localStorage.clear());
  await page.route('**/api/visitor-country', route => route.fulfill({json:{country_code:'DE', country_name:'Германия', source:{name:'DB-IP Lite'}}}));
  await page.goto(base + '/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  await page.getByText(/записей в области/).waitFor({timeout:30000});
  await page.waitForFunction(() => { const view=tripMap.getView(); return view && Math.abs(view.center[1]-50.96)<2; });
  assert(await page.locator('#currency').inputValue() === 'EUR', 'Country currency not selected');
  assert(await page.locator('#country').count() === 0, 'Country should not appear beside currency');
  assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), 'Desktop overflows');
  assert(await page.locator('#trip-context').isHidden(), 'IP was treated as a confirmed origin');
  assert(await page.locator('#ask button').count() === 1, 'Voice requires a separate control');
  assert(await page.locator('#send').getAttribute('aria-label') === 'Голосовой ввод', 'Empty composer does not offer voice');
  await page.locator('#send').click();
  await page.waitForFunction(() => document.querySelector('#text').value === 'Хочу в Париж');
  assert(await page.locator('#send').getAttribute('aria-label') === 'Отправить', 'Transcription cannot be reviewed and sent');
  await page.locator('#text').fill('');
  assert(await page.locator('.inspiration-grid img').count() >= 3, 'Curated photos are missing');

  // The summary must reflect each server response, never preserve a value the
  // agent stopped confirming. These fixtures exercise the UI independently of NLU.
  const understoodSteps = [['Казань'], ['Казань', 'поездка: 7 дней'], ['Дубай', 'поездка: 7 дней'], ['Дубай']];
  await page.route('**/api/chat', route => route.fulfill({json:{session_id:'summary-fixture', stage:'start',
    reply:'Расскажите о поездке.', payload:{kind:'question'}, understood:understoodSteps.shift(), assumptions:[]}}));
  await chat('Хочу в Казань');
  assert(await page.locator('#conditions').isVisible(), 'The current trip summary is not visible');
  await chat('На 7 дней');
  assert((await page.locator('#conditions').innerText()).includes('7 дней'), 'Confirmed duration is missing');
  await chat('Передумал, хочу в Дубай');
  assert((await page.locator('#condition-change').innerText()) === 'Казань → Дубай', 'Destination change is missing');
  assert((await page.locator('#conditions').innerText()).includes('7 дней'), 'Confirmed duration disappeared after changing destination');
  await chat('Уточню позже');
  assert(!(await page.locator('#conditions').innerText()).includes('7 дней'), 'Unconfirmed duration remained visible');
  await page.locator('.condition-edit summary').click();
  await page.getByRole('button', {name:'Гости',exact:true}).click();
  assert((await page.locator('#text').inputValue()).includes('Путешественники'), 'Editing trip conditions did not open the composer');
  await page.unroute('**/api/chat');
  await page.goto(base + '/');
  await page.getByText(/записей в области/).waitFor({timeout:30000});

  await page.evaluate(() => tripMap.draw({targets:[{name:'Париж',lat:48.8566,lon:2.3522}]}));
  await page.getByRole('button',{name:'Выбрать Париж',exact:true}).waitFor();
  const cityReply = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByRole('button',{name:'Выбрать Париж',exact:true}).click();
  const city = await (await cityReply).json();
  assert(city.understood.includes('Париж'), 'Map selection was not sent to the assistant');
  await page.getByText('Выбрать даты',{exact:true}).waitFor();
  assert(await page.getByRole('button',{name:'Пока не знаю'}).isVisible(), 'No answer for unknown dates');
  const unknownReply = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByRole('button',{name:'Пока не знаю'}).click(); await unknownReply;
  await page.waitForTimeout(300);
  assert(await page.getByRole('button',{name:'Пока не знаю'}).count() === 0, 'Unknown dates were repeatedly requested by the UI');
  await page.getByRole('button', {name:'Начать заново'}).click();
  await page.locator('.inspiration-grid').waitFor();
  await chat('хочу в Париж');
  await page.getByText('Выбрать даты',{exact:true}).click();
  await page.getByLabel('Дата начала поездки').fill('2027-01-15');
  await page.getByLabel('Дата окончания поездки').fill('2027-01-18');
  const datesReply = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByRole('button',{name:'Готово',exact:true}).click();
  const dated = await (await datesReply).json();
  assert(dated.understood.some((x) => x.includes('января')), 'Selected dates did not reach the assistant');
  await page.getByRole('button', {name:'Начать заново'}).click();
  await page.locator('.inspiration-grid').waitFor();

  await page.evaluate(() => tripMap.draw({targets:[
    {name:'Калининград',country:'Россия',lat:54.71,lon:20.452},
    {name:'Дагестан',country:'Россия',lat:42.983,lon:47.504},
    {name:'Владивосток',country:'Россия',lat:43.115,lon:131.885}]}));
  await page.waitForFunction(() => {const v=tripMap.getView();return v && Math.abs(v.center[0]-77)<1 && Math.abs(v.center[1]-61)<1 && v.zoom<1.2;});
  assert(await page.locator('.target-marker').count() === 3, 'Suggested Russian places are not marked');

  // A marker opens a sourced event rather than a fixed overlay.
  const event = page.locator('.event-marker:not(.maplibregl-marker-covered)').first();
  await event.click();
  if (await page.locator('.map-event-row').count()) await page.locator('.map-event-row').first().click();
  await page.locator('.maplibregl-popup-content .map-source').waitFor();
  assert(await page.locator('.maplibregl-popup-content').getByText(/Билеты не проверены/).count(), 'Event ticket status missing');

  // Center on Moscow through the public map component interface, zoom to
  // individual accommodation records, and open a sourced detail card.
  await page.evaluate(() => tripMap.draw({targets:[{name:'Москва',lat:55.7558,lon:37.6173}]}));
  await page.locator('.map-kind').selectOption('hotel');
  await page.waitForTimeout(1200);
  await page.getByRole('button', {name:'Москва: Московский Кремль'}).click();
  await page.locator('.maplibregl-popup-content').getByText('Московский Кремль').waitFor();
  assert(await page.locator('.maplibregl-popup-content').getByText(/условия посещения/i).count(), 'Landmark context missing');
  await page.locator('.landmark-model').first().waitFor({timeout:30000});
  assert(await page.locator('.landmark-model').first().evaluate(c => [...c.getContext('2d').getImageData(0,0,c.width,c.height).data].some((v,i) => i%4===3 && v>0)), '3D model is blank');
  for (let n=0;n<10;n++) { await page.getByLabel('Приблизить карту').click(); await page.waitForTimeout(720); }
  await page.getByText(/мест$/, {exact:false}).first().waitFor({timeout:30000});
  await page.locator('.map-list summary').click();
  await page.locator('.map-list-row').first().waitFor({timeout:30000});
  await page.locator('.map-list-row').first().click();
  await page.locator('.maplibregl-popup-content').getByText(/Цена, условия и наличие не подтверждены/).waitFor({timeout:15000});
  await page.waitForTimeout(1400);
  assert(await page.locator('.maplibregl-popup-content').getByText(/Overture Maps/).count(), 'Point or source disappeared after map movement');
  assert(await page.locator('.maplibregl-popup-content').getByText(/Снимок|Дата снимка/).count(), 'Point snapshot missing');
  await page.locator('.map-favorite').click();
  assert(await page.locator('#saved-places').isVisible(), 'Map hotel was not saved');
  await page.locator('.map-favorite').click();

  await page.getByRole('button', {name:'Начать заново'}).click();
  const plan = await chat('Из Москвы в Казань с 15 по 18 января 2027 года, 2 взрослых, бюджет 100000 рублей');
  assert(plan.payload?.kind === 'packages', 'Travel plan did not load');
  assert(plan.understood.some((x) => x.includes('Москва')), 'IP country overwrote the explicitly stated origin');
  assert(await page.locator('#view .card').count() >= 2, 'Comparison cards missing');
  assert((await page.locator('#view').innerText()).includes('€'), 'Currency conversion is not shown');
  assert((await page.locator('#view').innerText()).includes('Демо'), 'Demo prices are not labelled');
  const firstPackage = page.locator('#view .cards > .card').first();
  await firstPackage.locator('.feedback-button[aria-pressed]').click();
  assert(await page.locator('#saved-places').isVisible(), 'Accommodation was not saved');
  await firstPackage.locator('.feedback-button[aria-pressed]').click();
  await firstPackage.locator('.feedback-button:not([aria-pressed])').click();
  await page.getByRole('button',{name:'Сравнить',exact:true}).click();
  assert(await page.locator('.compare-table').isVisible(), 'Comparison table did not open');
  assert(await page.locator('.compare-table [data-option-key][hidden]').count() > 0, 'Hidden option appeared in comparison');
  await page.getByRole('button',{name:'Показать скрытые'}).click();
  assert(await page.locator('.compare-table [data-option-key][hidden]').count() === 0, 'Hidden comparison option did not restore');
  await page.getByRole('button',{name:'Карточки',exact:true}).click();
  assert((await page.locator('#conditions').innerText()).includes('Казань'), 'Conditions missing from chat');
  const cart = await trigger('Выбрать вариант');
  assert(cart.payload?.kind === 'cart', 'Cart not reached');
  const payment = await trigger('Выбрать способ оплаты');
  assert(payment.payload?.kind === 'payment', 'Payment choices not reached');
  await trigger('Демо-карта');
  const order = await trigger('Подтвердить демонстрацию');
  assert(order.payload?.kind === 'order', 'Demo order not reached');
  assert((await page.locator('#view').innerText()).includes('Денег не списано'), 'Demo order disclaimer missing');
  await page.getByRole('button', {name:'Начать заново'}).click();
  await page.locator('.maplibregl-canvas').waitFor({state:'visible', timeout:10000});
  assert(await page.locator('.maplibregl-canvas').isVisible(), 'Reset did not restore the map');

  await chat('Хочу к морю');
  const ideas = await chat('не знаю');
  assert(ideas.payload?.kind === 'ideas', 'Ideas did not load');
  assert(await page.locator('#view .cards img').count() > 0, 'Ideas did not use destination photos');
  assert(!(await page.locator('#suggest').innerText()).includes('Горы'), 'Welcome examples did not disappear');
  const firstIdea = page.locator('#view .cards > .card').first();
  await firstIdea.locator('.feedback-button[aria-pressed]').click();
  assert(await page.locator('#saved-places').isVisible(), 'Favourite was not saved');
  await firstIdea.locator('.feedback-button:not([aria-pressed])').click();
  assert(await firstIdea.isHidden(), 'Excluded direction remains visible');
  await page.getByRole('button', {name:'Показать скрытые'}).click();
  assert(await firstIdea.isVisible(), 'Hidden direction could not be restored');
  await page.reload();
  await page.locator('#saved-places').waitFor({state:'visible', timeout:30000});
  assert((await page.locator('#saved-count').textContent()) === '1', 'Favourite did not persist locally');

  // Run the widget from a different origin and check the iframe's own chat.
  const other = base.includes('127.0.0.1') ? base.replace('127.0.0.1', 'localhost') : base.replace('localhost', '127.0.0.1');
  await page.goto(other + '/health');
  await page.setContent('<!doctype html><html lang="ru"><body><h1>Сайт партнёра</h1></body></html>');
  await page.addScriptTag({url:base + '/static/embed.js'});
  await page.getByRole('button', {name:'Открыть помощника по поездкам'}).click();
  const frame = page.frameLocator('iframe[title="Помощник в планировании поездки"]');
  await frame.getByText(/Расскажите/).waitFor();
  await frame.getByLabel('Сообщение помощнику').fill('Хочу в Казань');
  await frame.getByLabel('Сообщение помощнику').press('Enter');
  await frame.locator('.message.user').filter({hasText:'Хочу в Казань'}).waitFor();
  await frame.locator('.message:not(.user)').nth(1).waitFor({timeout:30000});
  await page.getByRole('button', {name:'Закрыть помощника по поездкам'}).click();
  assert(await page.locator('iframe').isHidden(), 'Widget did not close');

  await page.setViewportSize({width:375,height:812});
  await page.goto(base + '/');
  await page.locator('.maplibregl-canvas').waitFor({timeout:30000});
  await page.getByText(/записей в области/).waitFor({timeout:30000});
  assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), 'Mobile overflows horizontally');
  await page.route('**/api/chat', route => route.fulfill({status:503, body:'unavailable'}));
  await page.locator('#text').fill('Поездка в Париж');
  await page.locator('#text').press('Enter');
  await page.getByText('Не удалось отправить. Текст сохранён — попробуйте ещё раз.').first().waitFor();
  assert(await page.locator('#text').inputValue() === 'Поездка в Париж', 'Failed mobile message was lost');
  assert(await page.locator('#say').isVisible(), 'Mobile error is not visible');
  assert(!errors.length, 'JavaScript errors: ' + errors.join('; '));
  return {globe:'pass', tripSummary:'pass', mapCityAndUnknownDates:'pass', dateSelection:'pass', russianOverview:'pass', threeDimensionalLandmark:'pass', sourcedPoint:'pass', event:'pass',
    approximateCountry:'pass', currency:'pass', oneButtonVoiceMock:'pass', comparison:'pass', demoCheckout:'pass',
    favouritesAndHidden:'pass', widgetCrossOrigin:'pass', mobile:'pass', failedMessage:'pass'};
}
