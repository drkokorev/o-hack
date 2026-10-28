async (page) => {
  const texts = [
    'Хочу горы, летний вайб, шашлык, с другом, мало денег, живём в палатках',
    'только Россия',
    'какое время в пути?',
    'я не говорил про семь ночей',
  ];
  const replies = [];
  for (const text of texts) {
    await page.getByRole('textbox', { name: 'Сообщение агенту' }).fill(text);
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith('/api/chat') && r.request().method() === 'POST'),
      page.getByRole('button', { name: 'Отправить' }).click(),
    ]);
    if (!response.ok()) throw new Error('chat HTTP status ' + response.status());
    const body = await response.json();
    await page.waitForFunction((head) => document.querySelector('#log')?.innerText.includes(head), body.reply.split('\n')[0]);
    replies.push(body);
  }
  if (replies[1].payload?.kind !== 'ideas' || !replies[1].payload.items.every((i) => i.country === 'Россия'))
    throw new Error('Country filter was not applied');
  if (!replies[2].reply.toLowerCase().includes('откуда')) throw new Error('Missing origin question');
  if (!replies[3].reply.toLowerCase().includes('вы правы') || replies[3].payload?.kind !== 'ideas')
    throw new Error('Duration correction was not preserved');
  return { status: 'PASS', turns: replies.length, mode: replies.map((r) => r.nlu), ui_replies_visible: true };
}
