// Synthetic browser speech and HTTP responses; no microphone or real booking.
async (page) => {
  const checks = [];
  const check = (ok, name) => { if (!ok) throw new Error(name); checks.push(name); };
  await page.addInitScript(() => {
    window.__voiceQA = {starts:0, stops:0, aborts:0, transcript:'диктовка'};
    Object.defineProperty(navigator, 'mediaDevices', {configurable:true, value:{
      getUserMedia:async()=>({getTracks:()=>[{stop(){}}]})
    }});
    class Recognition {
      start() { window.__voiceQA.starts++; this.onstart?.(); }
      stop() { window.__voiceQA.stops++; this.onresult?.({resultIndex:0, results:[{isFinal:true, 0:{transcript:window.__voiceQA.transcript}}]}); this.onend?.(); }
      abort() { window.__voiceQA.aborts++; this.onend?.(); }
    }
    Object.defineProperty(window, 'SpeechRecognition', {value:Recognition, configurable:true});
  });
  const chats = [];
  await page.route('**/api/voice', route => route.fulfill({json:{backend:'browser',status:'ready'}}));
  await page.route('**/api/chat', route => {
    chats.push(route.request().postDataJSON());
    return route.fulfill({json:{session_id:'synthetic', revision:1, reply:'Принято', payload:{kind:'greeting'},
      stage:'start', understood:[], assumptions:[], suggestions:[], nlu:'rules', checked:[], ms:0, can_undo:false}});
  });
  const base = new URL(page.url()).origin;
  await page.goto(base + '/static/favicon.svg');
  await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('odin.tour.v2'); });
  await page.goto(base + '/');
  await page.waitForFunction(() => !document.querySelector('#send').disabled, null, {timeout:120000});
  if (await page.locator('#tour-dialog').isVisible()) await page.locator('#tour-skip').click();
  await page.waitForTimeout(500);
  await page.locator('#mic-button').click();
  check(await page.locator('#voice-dialog').isVisible(), 'voice disclosure appears before first recording');
  await page.locator('#voice-allow').click();
  await page.waitForFunction(() => document.querySelector('#voice-status')?.innerText.includes('готов'));
  await page.locator('#mic-button').click();
  await page.locator('#mic-button').click();
  check((await page.locator('#text').inputValue()).includes('диктовка'), 'dedicated microphone transcribes');
  await page.locator('#text').fill('План');
  await page.locator('#mic-button').click();
  check(await page.locator('#send').getAttribute('data-listening') === 'true', 'microphone starts recording');
  await page.locator('#send').click();
  check((await page.locator('#text').inputValue()) === 'План диктовка', 'stopping adds text for review');
  check(chats.length === 0, 'stopping recording does not send');
  await page.locator('#send').click();
  await page.waitForFunction(() => document.querySelector('#log')?.innerText.includes('Принято'));
  check(chats.length === 1 && chats[0].text === 'План диктовка', 'manual send after review works');
  await page.locator('#mic-button').click();
  await page.keyboard.press('Escape');
  check((await page.evaluate(() => window.__voiceQA.aborts)) === 1, 'escape cancels recording');
  return {checks, mocked_speech:true};
}
