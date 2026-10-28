// Open the application with playwright-cli; no real model key is needed.
async (page) => {
  const base = new URL(page.url()).origin;
  await page.unrouteAll({behavior:'ignoreErrors'});
  await page.addInitScript(() => {
    window.__soundStarts = 0;
    const param = () => ({value:0, setValueAtTime(){}, exponentialRampToValueAtTime(){}, setTargetAtTime(){}});
    const node = () => ({gain:param(),frequency:param(),connect(){},start(){window.__soundStarts++},stop(){}});
    window.AudioContext = class {
      constructor(){this.currentTime=0;this.sampleRate=8000;this.destination={};this.state='running';}
      createGain(){return node()} createOscillator(){return node()} createBufferSource(){return node()}
      createBiquadFilter(){return node()} createBuffer(_n, length){return {getChannelData:()=>new Float32Array(length)}}
      resume(){return Promise.resolve()}
    };
  });
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base + '/health');
  await page.evaluate(()=>localStorage.clear());
  await page.goto(base + '/');
  await page.getByText(/записей в области/).waitFor({timeout:30000});
  if (await page.evaluate(()=>window.__soundStarts) !== 0) throw Error('Autoplay on page open');
  await page.getByRole('button',{name:'Море',exact:true}).click();
  await page.waitForTimeout(300);
  const sea=await page.evaluate(()=>window.__soundStarts);
  if (!sea) throw Error('Sea sound was not generated on interaction');
  await page.getByRole('button',{name:'Выключить звуки'}).click();
  await page.waitForTimeout(2700);
  await page.locator('.event-marker:not(.maplibregl-marker-covered)').first().click();
  if (await page.evaluate(()=>window.__soundStarts) !== sea) throw Error('Sound played while disabled');
  await page.reload();
  if (await page.getByRole('button',{name:'Включить звуки'}).getAttribute('aria-pressed') !== 'false') throw Error('Mute preference did not persist');
  await page.getByRole('button',{name:'Включить звуки'}).click();
  if (await page.getByRole('button',{name:'Выключить звуки'}).getAttribute('aria-pressed') !== 'true') throw Error('Sound did not turn back on');
  return {noAutoplay:'pass',seaOnClick:'pass',mute:'pass',persist:'pass',unmute:'pass',audioOutput:'mocked'};
}
