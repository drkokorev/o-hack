// Run after the sentence interaction and edge checks, with their synthetic trip.
async page=>{
  const checks=[],samples=[],errors=[],ok=(value,label)=>{if(!value)throw Error(label);checks.push(label);};
  page.on('pageerror',e=>errors.push(e.message));
  await page.emulateMedia({reducedMotion:'reduce'});
  const idle=()=>page.waitForFunction(()=>!document.getElementById('send').disabled);
  await idle();
  if(await page.locator('html').getAttribute('data-theme')!=='light')await page.locator('#theme-toggle').click();
  for(const width of [1440,1024,768,390,320]){
    await page.setViewportSize({width,height:width>=1024?960:740});
    if(width<=900)await page.locator('button[data-panel="chat"]').click();
    const panel=page.locator('#trip-context'),toggle=page.locator('#trip-context-toggle');
    if(width<=900&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
    const measurement=await page.evaluate(()=>{
      const p=document.getElementById('trip-context'),c=document.getElementById('conversation-scroll');
      return {width:innerWidth,height:p.getBoundingClientRect().height,chatHeight:c.getBoundingClientRect().height,
        parent:p.parentElement.id||p.parentElement.tagName,overflow:document.documentElement.scrollWidth>innerWidth,
        one:document.querySelectorAll('#trip-context').length===1};
    });samples.push(measurement);
    ok(measurement.one&&!measurement.overflow,`one summary without horizontal overflow: ${width}`);
    if(width>900){
      ok(await page.locator('#board > #trip-context').count()===1,`wide summary is outside chat: ${width}`);
      ok(await page.locator('#head .route-title').isHidden(),`route is not duplicated: ${width}`);
    }else{
      ok(measurement.height<=100&&measurement.chatHeight>=160,`compact summary leaves readable chat: ${width}`);
      await toggle.focus();await page.keyboard.press('Enter');
      ok(await page.locator('#trip-context-body').isVisible(),`keyboard expands summary: ${width}`);
      await toggle.click();
      await page.locator('button[data-panel="results"]').click();
      ok(await page.locator('#board > #trip-context').isVisible(),`conditions accompany results: ${width}`);
      await page.locator('button[data-panel="chat"]').click();
    }
    if(width===390)await page.screenshot({path:'output/playwright/sentence-placed-mobile.png'});
    if(width===1440)await page.screenshot({path:'output/playwright/sentence-placed-desktop.png'});
  }
  await page.setViewportSize({width:1440,height:960});await page.locator('#theme-toggle').click();
  const ratio=await page.evaluate(()=>{
    const rgb=s=>s.match(/[\d.]+/g).slice(0,3).map(Number);
    const lum=s=>rgb(s).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
    const a=lum(getComputedStyle(document.querySelector('.trip-word')).color),b=lum(getComputedStyle(document.getElementById('trip-context')).backgroundColor);
    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
  });ok(ratio>=4.5,'dark sentence contrast is at least 4.5:1');
  await page.screenshot({path:'output/playwright/sentence-placed-dark.png'});
  await page.setViewportSize({width:390,height:844});await page.goto('http://127.0.0.1:18191/static/widget.html');
  const frame=page.frameLocator('iframe');await frame.locator('#trip-context-toggle').waitFor();
  ok(await frame.locator('#trip-context-body').isHidden(),'embedded chat starts with compact conditions');
  await frame.locator('#trip-context-toggle').click();await frame.locator('[data-trip-field="budget"]').click();
  ok(await frame.locator('#condition-value').isVisible(),'embedded chat shares field editing');
  await frame.locator('#condition-cancel').click();await frame.locator('#trip-context-toggle').click();
  await frame.locator('button[data-panel="results"]').click();
  ok(await frame.locator('#board > #trip-context').isVisible(),'embedded results retain access to parameters');
  await page.screenshot({path:'output/playwright/sentence-placed-widget.png'});
  await page.setViewportSize({width:1440,height:960});await page.goto('http://127.0.0.1:18191/');await idle();
  await page.locator('#reset').click();await page.locator('#reset-confirm').click();await idle();
  ok(await page.locator('#trip-context').isHidden()&&await page.locator('#head h1').isVisible(),'new trip restores clean globe introduction');
  ok(errors.length===0,'no browser exceptions');
  return {status:'PASS',checks,samples,darkContrast:ratio,errors};
}
