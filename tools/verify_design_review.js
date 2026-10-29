// playwright-cli run-code --filename=tools/verify_design_review.js
// Run against an isolated rules-mode server. Synthetic trip; no booking/payment.
async (page) => {
  const base = new URL(page.url()).origin, checks = [], widths = [];
  const assert = (ok, name) => { if (!ok) throw new Error(name); checks.push(name); console.log('PASS '+name); };
  const idle = () => page.waitForFunction(() => !document.querySelector('#send').disabled, null, {timeout:120000});
  const screenshot = async name => {
    await page.locator('img:visible').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode().catch(()=>{}))));
    await page.screenshot({path:'output/playwright/'+name+'.png', fullPage:false});
  };
  const send = async text => { await page.locator('#text').fill(text); await page.locator('#ask').evaluate(form=>form.requestSubmit()); await idle(); };
  const fit = async name => {
    const size=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
    widths.push({name,...size});assert(size.document<=size.viewport,name+' fits viewport '+JSON.stringify(size));
  };
  await page.route('https://ipinfo.io/**',route=>route.fulfill({json:{}}));
  await page.setViewportSize({width:1440,height:940});
  await page.goto(base+'/static/favicon.svg');
  await page.evaluate(()=>{sessionStorage.clear();localStorage.removeItem('odin.tour.v1');});
  await page.goto(base+'/');await idle();
  assert(await page.locator('#tour-dialog').isVisible(),'first visit opens introduction');
  await page.locator('#tour-next').click();assert((await page.locator('#tour-title').innerText()).includes('глобусе'),'tour explains globe');
  await page.locator('#tour-next').click();assert((await page.locator('#tour-title').innerText()).includes('под себя'),'tour explains trip parts');
  await page.locator('#tour-back').click();await page.locator('#tour-back').click();
  await page.locator('#tour-example').click();
  assert((await page.locator('#text').inputValue()).includes('Казань'),'example prefills composer');
  assert(await page.locator('.msg.user').count()===0,'example is not sent automatically');
  await page.locator('#text').fill('');
  await page.locator('#how-it-works').click();await page.locator('#tour-skip').click();
  await page.reload();await idle();assert(await page.locator('#tour-dialog').isHidden(),'tour stays dismissed after reload');
  assert(await page.locator('#head h1').innerText()==='Соберём вашу поездку','compact useful title');
  assert(await page.locator('#suggest button').allTextContents().then(x=>x.join('|')==='К морю|В горы|Помоги выбрать'),'three short starter wishes');
  await screenshot('review-desktop-start');
  for(const width of [320,390,768]) {
    await page.setViewportSize({width,height:844});await fit('fresh chat');
    await page.locator('button[data-panel="map"]').click();await fit('globe');
    assert(await page.locator('#map').isVisible(),'globe accessible '+width);
    if(width===390)await screenshot('review-mobile-globe');
    await page.locator('button[data-panel="chat"]').click();
  }
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Помоги выбрать',exact:true}).click();
  assert(await page.locator('.inspiration').isVisible(),'inspiration opens on request');await fit('inspiration');
  await screenshot('review-mobile-inspiration');
  await page.locator('button[data-panel="chat"]').click();
  await send('Хочу на море из Москвы на 7 ночей с 15 июня 2027, двое взрослых, бюджет 180 тысяч рублей на всю поездку, без визы.');
  await page.locator('.reply-results').last().click();await fit('destinations');
  await page.getByRole('button',{name:'Выбрать Анталья',exact:true}).click();await idle();
  assert(await page.locator('.package-card').count()===3,'Antalya button opens three packages');
  assert(!(await page.locator('.msg.bot').last().innerText()).includes('личные данные'),'catalog action avoids false personal-data warning');
  await page.locator('.reply-results').last().click();await fit('packages');
  await screenshot('review-mobile-packages');
  for(const width of [320,768,1440]) {
    await page.setViewportSize({width,height:940});await fit('packages');
    await page.getByRole('button',{name:'Сравнить',exact:true}).click();await fit('comparison');
    assert(await page.locator('.compare-scroll').isVisible(),'comparison available '+width);
    await page.getByRole('button',{name:'Карточки',exact:true}).click();
  }
  await page.locator('#view').scrollIntoViewIfNeeded();await screenshot('review-desktop-packages');
  const heights=await page.locator('.package-card').evaluateAll(nodes=>nodes.map(n=>Math.round(n.getBoundingClientRect().height)));
  console.log('CARD_HEIGHTS '+JSON.stringify(heights));
  await page.locator('.package-card').first().getByText('Состав и маршрут',{exact:true}).click();
  await page.locator('.package-card').first().getByText('Трансферы · обе стороны',{exact:true}).click();
  assert((await page.locator('.package-card').first().innerText()).includes('Обратно к отправлению'),'both transfer directions available inside package');
  await page.locator('.package-card').first().getByRole('button',{name:'Выбрать',exact:true}).click();await idle();
  await page.locator('.reply-results').last().click();
  assert(await page.locator('.trip-component').count()===4,'basket has four trip components');
  await page.getByRole('button',{name:'Изменить дорогу',exact:true}).click();
  assert(await page.locator('#condition-field').inputValue()==='transport','change road opens transport condition');
  await page.locator('#conditions-dialog .dialog-close').click();
  const hotelBefore=await page.locator('.trip-component').nth(1).innerText();
  const outBefore=await page.locator('.trip-component').nth(0).innerText();
  const backBefore=await page.locator('.trip-component').nth(3).innerText();
  const totalBefore=await page.locator('.receipt .total').innerText();
  await page.locator('#transfer-kind').selectOption('shuttle');await idle();
  assert(await page.locator('#transfer-kind').inputValue()==='shuttle','group transfer applied');
  assert(await page.locator('.trip-component').nth(1).innerText()===hotelBefore,'transfer keeps selected hotel');
  assert(await page.locator('.trip-component').nth(0).innerText()===outBefore,'transfer keeps outward tickets');
  assert(await page.locator('.trip-component').nth(3).innerText()===backBefore,'transfer keeps return tickets');
  const totalAfter=await page.locator('.receipt .total').innerText();assert(totalAfter!==totalBefore,'transfer changes total');
  for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:940});await fit('basket');}
  await page.locator('#view').scrollIntoViewIfNeeded();await screenshot('review-desktop-basket');
  await page.setViewportSize({width:390,height:844});await page.locator('.trip-component').nth(2).scrollIntoViewIfNeeded();await screenshot('review-mobile-transfers');
  await page.locator('button[data-panel="chat"]').click();await page.locator('#text').fill('Хочу уточнить время выезда');
  const messages=await page.locator('.msg.user').count();
  let replay=0;const listener=request=>{if(request.url().endsWith('/api/chat'))replay++;};page.on('request',listener);
  await page.reload();await idle();page.off('request',listener);
  assert(replay===0,'refresh never replays chat request');
  assert(await page.locator('.msg.user').count()===messages,'refresh restores conversation');
  assert(await page.locator('#text').inputValue()==='Хочу уточнить время выезда','refresh restores draft');
  await page.locator('#panel-results').click();
  assert(await page.locator('.receipt .total').innerText()===totalAfter,'refresh restores total');
  assert(await page.locator('#transfer-kind').inputValue()==='shuttle','refresh restores transfer selection');
  await page.locator('button[data-panel="chat"]').click();
  await page.locator('#chat-menu summary').click();await page.locator('#reset').click();await page.locator('#reset-confirm').click();await idle();
  assert(await page.locator('.msg.user').count()===0,'new trip resets conversation');
  assert(await page.evaluate(()=>sessionStorage.getItem('odin.trip.v1'))===null,'new trip clears saved session');
  await send('В Казань из Санкт-Петербурга на 3 ночи с 15 июня 2027, двое взрослых, бюджет 100 тысяч рублей на всю поездку');
  await page.locator('button[data-panel="map"]').click();
  const title=await page.locator('#head').innerText();
  assert(title.includes('Санкт-Петербург')&&title.includes('Казань')&&!title.includes('LED'),'Russian city route replaces IATA heading');
  await fit('long Russian route');await screenshot('review-mobile-route');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert(await page.locator('body').evaluate(el=>getComputedStyle(el).transitionDuration)==='0s','reduced motion respected');
  console.log('RESULT '+JSON.stringify({checks,widths,heights,totalBefore,totalAfter}));
  return {checks,widths,heights,totalBefore,totalAfter};
}
