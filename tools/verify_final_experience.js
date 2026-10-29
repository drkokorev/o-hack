// Real browser + local API. No commercial booking; all offers are the demo catalog.
async page=>{
  const base='http://127.0.0.1:18191',checks=[],samples=[],errors=[];
  const ok=(value,name)=>{if(!value)throw Error(name);checks.push(name);};
  const idle=()=>page.waitForFunction(()=>!document.querySelector('#send').disabled,null,{timeout:60000});
  const request=async action=>{const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/chat'&&r.request().method()==='POST');await action();const data=await(await reply).json();await idle();return data;};
  const say=text=>request(async()=>{await page.locator('#text').fill(text);await page.locator('#send').click();});
  page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.unrouteAll({behavior:'wait'});await page.emulateMedia({reducedMotion:'reduce'});
    await page.setViewportSize({width:1440,height:960});await page.goto(base+'/static/favicon.svg');
    await page.evaluate(()=>{sessionStorage.clear();localStorage.setItem('odin.tour.v2','seen');localStorage.setItem('odin.theme','light');localStorage.setItem('odin.currency','RUB');localStorage.setItem('odin.globe','earth');});
    await page.goto(base+'/');await idle();await page.waitForFunction(()=>tripMap.getView()?.models.length>0);
    await page.locator('.event-teaser').first().waitFor();
    ok(await page.locator('body>.quiet-footer').count()===1&&await page.locator('.chat-legal').count()===0,'one shared footer outside the two panels');
    ok(await page.locator('#board>#journey').count()===1&&await page.locator('#head h1').isVisible(),'stage heading and timeline live above the globe');
    ok(await page.locator('.event-teaser').count()===3,'three travel occasions are visible immediately');
    ok(await page.locator('.event-teaser img').evaluateAll(imgs=>imgs.every(i=>i.complete&&i.naturalWidth>0)),'all featured photographs load locally');
    ok(await page.locator('#trip-context').isHidden(),'no empty questionnaire competes with starter wishes');
    await page.screenshot({path:'output/playwright/final-desktop-start.png'});
    await page.locator('[data-event-id="f1-qatar-2026"]').click();
    await page.locator('.event-story').waitFor();
    ok(await page.locator('.event-story .event-photo img').evaluate(i=>i.complete&&i.naturalWidth>0),'Formula 1 opens a loaded thematic photo');
    ok((await page.locator('.event-story').innerText()).includes('Тематическое фото')&&(await page.locator('.event-story .event-location').innerText()).includes('Доха'),'event card names the location and labels the image honestly');
    await page.screenshot({path:'output/playwright/final-event-card.png'});
    const first=await request(()=>page.getByRole('button',{name:'Хочу на событие',exact:true}).click());
    ok(first.trip_summary.destination==='Доха'&&first.trip_summary.selected_event.id==='f1-qatar-2026'&&!first.trip_summary.date_from,'event action selects a supported city without inventing stay dates');
    const trip=await say('Из Москвы с 27 по 30 ноября 2026, двое взрослых, бюджет 500000 рублей');
    ok(trip.payload.kind==='packages'&&trip.payload.items.length>0,'selected event continues into full trip options');
    ok(await page.locator('.chat>#trip-context').count()===1&&await page.locator('#trip-context-body').isHidden(),'chosen parameters remain compact in the chat');
    const preview=await page.locator('.trip-context-preview').innerText();
    ok(['Москва','Доха','ноя','2 взрослых','500'].every(t=>preview.includes(t)),'compact summary exposes route dates party and budget');
    ok(await page.locator('#results-jump').isHidden(),'no duplicate primary result action above the globe');
    await page.locator('#trip-context-toggle').focus();await page.keyboard.press('Enter');
    await page.locator('[data-trip-field="budget"]').click();await page.locator('#condition-value').fill('400000');
    const refined=await request(()=>page.locator('#condition-form [type=submit]').click());
    ok(refined.trip_summary.budget_total===400000&&['destination','origin','adults','date_from','date_to'].every(k=>refined.trip_summary[k]===trip.trip_summary[k]),'editing the summary changes only the requested parameter');
    await page.locator('#trip-context-toggle').click();await page.locator('#currency').selectOption('EUR');
    ok((await page.locator('.trip-context-preview').innerText()).includes('€'),'collapsed summary follows the chosen display currency');
    await page.locator('#currency').selectOption('RUB');
    await page.locator('.map-event-period').selectOption('all');await page.locator('[data-event-id="global-village"]').click();await page.locator('.event-story').waitFor();
    const changed=await request(()=>page.getByRole('button',{name:'Хочу на событие',exact:true}).click());
    ok(changed.trip_summary.destination==='Дубай'&&['origin','adults','budget_total','date_from','date_to'].every(k=>changed.trip_summary[k]===refined.trip_summary[k]),'another event changes destination while preserving travel conditions');
    await page.getByRole('button',{name:'К глобусу',exact:true}).click();
    await page.waitForFunction(()=>tripMap.getView()?.zoom<3);
    await page.screenshot({path:'output/playwright/final-desktop-trip.png'});
    for(const width of [1366,1024,390,320]){
      await page.setViewportSize({width,height:width>900?768:844});
      if(width<=900)await page.locator('button[data-panel="map"]').click();
      await page.waitForTimeout(350); // ResizeObserver, map render and marker debounce settle.
      const measure=await page.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,
        surface:document.querySelector('.map-surface').getBoundingClientRect().toJSON(),footer:document.querySelector('.quiet-footer').getBoundingClientRect().toJSON(),
        summaryInChat:document.getElementById('trip-context').parentElement.matches('.chat')}));samples.push(measure);
      ok(!measure.overflow&&measure.summaryInChat,`responsive roles and no horizontal overflow at ${width}`);
      await page.screenshot({path:`output/playwright/final-map-${width}.png`});
      if(width<=900){
        await page.locator('button[data-panel="chat"]').click();
        const room=await page.locator('.conversation-scroll').boundingBox();
        ok(room.height>=160,`conversation keeps at least 160px of reading space at ${width}`);
        const composer=await page.locator('.composer').boundingBox(),footer=await page.locator('.quiet-footer').boundingBox();
        ok(composer.y+composer.height<=footer.y+1,`footer does not cover composer at ${width}`);
        if(width===390)await page.screenshot({path:'output/playwright/final-mobile-chat.png'});
      }
    }
    await page.setViewportSize({width:1440,height:960});await page.locator('#theme-toggle').click();
    await page.screenshot({path:'output/playwright/final-dark.png'});
    await page.setViewportSize({width:430,height:844});await page.goto(base+'/static/widget.html');
    const frame=page.frameLocator('iframe');await frame.locator('#trip-context-toggle').waitFor();
    ok(await frame.locator('.chat>#trip-context').count()===1&&await frame.locator('#trip-context-body').isHidden(),'second chat has the same compact summary');
    ok(await frame.locator('.maplibregl-canvas').count()===0,'second chat does not create an invisible WebGL map');
    ok(await frame.locator('body>.quiet-footer').count()===1&&await frame.locator('#currency').isVisible()&&await frame.locator('.language-pill').isVisible(),'second chat shares footer currency and language controls');
    await frame.locator('#trip-context-toggle').click();await frame.locator('[data-trip-field="budget"]').click();
    ok((await frame.locator('#condition-value').inputValue()).includes('400000'),'second chat opens the same current parameter editor');
    await frame.locator('#condition-cancel').click();await frame.locator('#trip-context-toggle').click();
    await page.screenshot({path:'output/playwright/final-widget-chat.png'});
    await frame.locator('button[data-panel="results"]').click();
    ok(await frame.locator('.package-card').first().isVisible(),'second chat exposes the same trip cards');
    await page.screenshot({path:'output/playwright/final-widget-results.png'});
    ok(errors.length===0,'no uncaught browser errors');
    return {status:'PASS',checks,samples,errors};
  }catch(error){await page.screenshot({path:'output/playwright/final-acceptance-failure.png'});return {status:'FAIL',failure:error.message,checks,samples,errors};}
}
