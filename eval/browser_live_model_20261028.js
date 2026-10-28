// Run against a locally configured combined preview; sends only synthetic test text.
async (page) => {
  const base = new URL(page.url()).origin;
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const info = await (await page.request.get(base + '/api/info')).json();
  const voice = await (await page.request.get(base + '/api/voice')).json();
  assert(info.llm === 'GigaChat-2-Max', 'Expected language model is not configured');
  assert(voice.backend === 'gigaam' && voice.status === 'ready', 'Local speech model is not ready');
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base + '/');
  await page.locator('#text').waitFor();
  const turns = [];
  async function chat(text) {
    await page.locator('#text').fill(text);
    const response = page.waitForResponse(r => r.url().endsWith('/api/chat') && r.request().method() === 'POST', {timeout:60000});
    await page.locator('#text').press('Enter');
    const body = await (await response).json();
    turns.push({nlu:body.nlu, destination:body.trip_summary?.destination, understood:body.understood,
                question:body.payload?.field || null, reply:body.reply});
    await page.waitForTimeout(1500);
    return body;
  }
  const first = await chat('Хочу в Казань');
  const answer = await chat('Можно ли будет отменить бронь?');
  const duration = await chat('На 7 дней');
  const changed = await chat('Передумал, хочу в Дубай');
  assert(first.trip_summary?.destination === 'Казань', 'Kazan was not understood');
  assert(answer.reply.toLowerCase().includes('отмен') && answer.payload?.field === 'when', 'Interruption answer or date question was lost');
  assert(duration.understood.includes('поездка: 7 дней'), 'Duration was lost');
  assert(changed.trip_summary?.destination === 'Дубай' && changed.understood.includes('поездка: 7 дней'), 'Change or duration was lost');
  assert((await page.locator('#condition-change').innerText()) === 'Казань → Дубай', 'UI does not show destination change');
  assert(turns.every(t => ['llm','llm+rules'].includes(t.nlu)), 'At least one turn did not use the language model: ' + turns.map(t => t.nlu).join(','));
  return {model:info.llm, voice:voice.backend, turns:turns.length, nlu:turns.map(t => t.nlu), summary:'pass', interruption:'pass'};
}
