// Run with playwright-cli against the local application without model credentials.
// Speech audio and the transcription service are simulated; no real booking occurs.
async (page) => {
  const base = new URL(page.url()).origin;
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.unrouteAll({behavior:'ignoreErrors'});
  await page.setViewportSize({width:1440, height:900});
  await page.goto(base + '/');
  await page.locator('#text').waitFor();
  await page.locator('.fine summary').click();
  assert(await page.getByRole('link', {name:'GeoNames'}).isVisible(), 'Source attribution was lost');
  await page.locator('.fine summary').click();
  const chat = async (selector, text) => {
    await page.locator(selector).fill(text);
    const response = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
    await page.locator(selector).press('Enter');
    const result = await (await response).json();
    await page.waitForTimeout(150);
    return result;
  };
  await chat('#text', 'Хочу в Казань');
  const interruption = await chat('#text', 'Можно ли будет отменить бронь?');
  assert(interruption.reply.toLowerCase().includes('отмен'), 'Interruption was not answered');
  assert((await page.locator('#log .msg.bot').last().innerText()).toLowerCase().includes('отмен'), 'The answer was hidden by the page');
  assert(interruption.payload?.field === 'when', 'Date question was lost after interruption');
  await chat('#text', 'На 7 дней');
  const changed = await chat('#text', 'Передумал, хочу в Дубай');
  assert(changed.trip_summary.destination === 'Дубай', 'New destination not returned');
  assert((await page.locator('#condition-change').innerText()) === 'Казань → Дубай', 'Changed destination not shown');
  assert((await page.locator('#conditions').innerText()).includes('7 дней'), 'Confirmed duration not shown');

  await page.getByRole('button', {name:'Начать заново'}).click();
  const plan = await chat('#text', 'Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых');
  assert(plan.payload?.kind === 'packages', 'Plan was not returned');
  const planMessage = page.locator('#log .msg.bot').last();
  assert(await planMessage.locator('.full-reply summary').isVisible(), 'Complete plan answer is inaccessible');
  await planMessage.locator('.full-reply summary').click();
  assert((await planMessage.locator('.full-reply > div').textContent()) === plan.reply, 'Complete plan answer differs from the server');
  const question = await chat('#text', 'Завтрак и бассейн есть?');
  const shown = (await page.locator('#log .msg.bot').last().innerText()).toLowerCase();
  assert(question.reply.toLowerCase().includes('питан') && question.reply.toLowerCase().includes('бассейн'), 'Both questions were not answered');
  assert(shown.includes('питан') && shown.includes('бассейн'), 'One of the answers was hidden by the page');
  assert(!question.understood.some(x => /бассейн|завтрак/i.test(x)), 'Question was silently turned into a requirement');
  const mixed = await chat('#text', 'Нужен завтрак, а парковка есть?');
  assert((await page.locator('#log .msg.bot').last().innerText()).toLowerCase().includes('парковк'), 'Mixed answer was hidden');
  assert(mixed.understood.some(x => /завтрак/i.test(x)), 'Explicit breakfast requirement was lost');
  assert(!mixed.understood.some(x => /парковк/i.test(x)), 'Parking question became a requirement');
  assert((await page.locator('#suggest').innerText()).includes('другое направление'), 'A valid server suggestion was dropped');

  await page.getByRole('button', {name:'Начать заново'}).click();
  await chat('#text', 'Казань из Питера на выходные с собакой');
  const choice = await chat('#text', 'Хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов');
  assert(choice.payload?.field === 'trip_choice', 'New or existing trip choice was not returned');
  assert(await page.getByRole('button', {name:'новая поездка',exact:true}).isVisible(), 'New trip choice is missing');
  assert(await page.getByRole('button', {name:'изменить текущую',exact:true}).isVisible(), 'Edit current trip choice is missing');

  await page.goto(base + '/static/widget.html');
  const widgetPlan = await chat('#text', 'Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых');
  const widgetMessage = page.locator('#log .message:not(.user)').last();
  assert(await widgetMessage.locator('.full-reply summary').isVisible(), 'Widget complete answer is inaccessible');
  await widgetMessage.locator('.full-reply summary').click();
  assert((await widgetMessage.locator('.full-reply > div').textContent()) === widgetPlan.reply, 'Widget complete answer differs from the server');
  await chat('#text', 'Завтрак и бассейн есть?');
  const widgetAnswer = (await page.locator('#log .message:not(.user)').last().innerText()).toLowerCase();
  assert(widgetAnswer.includes('питан') && widgetAnswer.includes('бассейн'), 'Widget did not show both answers');

  // Simulated local microphone and recognizer exercise the selected local backend
  // without requesting actual microphone permission or running a speech model.
  let transcriptions = 0, chatsDuringVoice = 0, wavBytes = 0;
  page.on('request', r => { if (r.url().endsWith('/api/chat')) chatsDuringVoice++; });
  await page.route('**/api/voice', route => route.fulfill({json:{backend:'gigaam',status:'ready',max_seconds:20}}));
  await page.route('**/api/voice/transcribe', route => {
    transcriptions++;
    const bytes = route.request().postDataBuffer(); wavBytes = bytes.length;
    assert(bytes.subarray(0, 4).toString() === 'RIFF', 'Audio was not encoded as WAV');
    return route.fulfill({json:{text:'Хочу в Казань',backend:'gigaam'}});
  });
  await page.addInitScript(() => {
    window.__stoppedTracks = 0; window.__audioEmitted = false;
    Object.defineProperty(navigator, 'mediaDevices', {configurable:true, value:{
      getUserMedia:async () => ({getTracks:() => [{stop:() => window.__stoppedTracks++}]})
    }});
    window.AudioContext = class {
      constructor() { this.sampleRate = 16000; this.destination = {}; }
      async resume() {} async close() {}
      createMediaStreamSource() { return {connect(){}, disconnect(){}}; }
      createScriptProcessor() {
        const node = {disconnect(){}, connect(){setTimeout(() => {
          node.onaudioprocess?.({inputBuffer:{getChannelData:() => new Float32Array(4096).fill(0.2)},
            outputBuffer:{getChannelData:() => new Float32Array(4096)}});
          window.__audioEmitted = true;
        }, 20);}};
        return node;
      }
    };
  });
  await page.goto(base + '/');
  await page.getByText(/Голос распознаётся на сервере приложения/).waitFor();
  await page.getByRole('button', {name:'Голосовой ввод'}).click();
  await page.waitForFunction(() => window.__audioEmitted);
  await page.getByRole('button', {name:'Остановить запись'}).click();
  await page.waitForFunction(() => document.querySelector('#text').value === 'Хочу в Казань');
  assert(transcriptions === 1 && wavBytes > 44, 'Simulated local transcription did not receive audio');
  assert(chatsDuringVoice === 0, 'Recognized speech was sent without confirmation');
  assert(await page.evaluate(() => window.__stoppedTracks > 0), 'Microphone tracks were not stopped');

  await page.goto(base + '/static/widget-demo.html');
  await page.getByRole('button', {name:'Открыть помощника по поездкам'}).click();
  const frame = page.frameLocator('iframe[title="Помощник в планировании поездки"]');
  await frame.getByText(/Голос распознаётся на сервере приложения/).waitFor();
  await frame.getByRole('button', {name:'Голосовой ввод'}).click();
  await frame.getByText(/Слушаю/).waitFor();
  await page.getByRole('button', {name:'Закрыть помощника по поездкам'}).click();
  await page.waitForTimeout(100);
  assert((await frame.locator('body').evaluate(() => window.__stoppedTracks)) > 0, 'Closing widget did not stop the microphone');
  assert(transcriptions === 1, 'Closing widget unexpectedly sent its recording');
  assert(!errors.length, 'JavaScript errors: ' + errors.join('; '));
  return {interruptedQuestion:'pass', destinationAndDuration:'pass', questionVsRequirement:'pass',
    completeAnswers:'pass', serverSuggestions:'pass', tripChoice:'pass', widgetAnswers:'pass',
    localVoiceMock:'pass', widgetVoiceCancel:'pass'};
}
