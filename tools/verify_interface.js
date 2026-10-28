/* Run with playwright-cli run-code, on the local rules-mode preview.
   No microphone is used: voice recognition and permission are explicit doubles. */
async (page) => {
  const base = new URL(page.url()).origin;
  await page.route('https://ipinfo.io/**', route => route.fulfill({json:{}}));
  const checks=[];
  const assert=(ok,name)=>{if(!ok)throw new Error(name);checks.push(name);console.log('PASS '+name);};
  const ready=async()=>{await page.locator('#head h1').waitFor({state:'attached'});await page.locator('#suggest button').first().waitFor();};
  const send=async(text)=>{await page.locator('#text').fill(text);await page.locator('#ask').evaluate(form=>form.requestSubmit());await page.waitForFunction(()=>!document.querySelector('#send').disabled);await page.locator('.msg.user').last().waitFor();};
  await page.setViewportSize({width:1440,height:940});
  await page.goto(base+'/');await ready();
  assert(await page.locator('.journey .stages li:visible').count()===6,'desktop: six stages on the right');
  assert(await page.locator('.inspiration').count()===0,'inspiration hidden until requested');
  assert(await page.locator('#sound-toggle').getAttribute('aria-pressed')==='false','sound defaults off');
  assert((await page.locator('#send').getAttribute('aria-label')).includes('Отправить'),'send arrow remains the default');
  await page.locator('.example-link').click();
  await page.locator('#examples-dialog .example-card').first().click();
  assert((await page.locator('#text').inputValue()).includes('180 тысяч'),'full example is editable in composer');
  assert(await page.locator('.msg.user').count()===0,'choosing an example does not send it');
  await send('Хочу в Казань');
  assert((await page.locator('#conditions').innerText()).includes('Казань'),'summary reflects server destination');
  await send('из Москвы');
  await page.locator('.latest-user .message-edit').click();
  await send('из Санкт-Петербурга');
  assert((await page.locator('#conditions').innerText()).includes('Санкт-Петербург'),'editing replaces server origin');
  assert(await page.locator('.msg.user').count()===2,'editing replaces message instead of appending');
  await page.locator('#undo').click();
  await page.waitForFunction(()=>document.querySelectorAll('.msg.user').length===1);
  assert(!(await page.locator('#conditions').innerText()).includes('Санкт-Петербург'),'undo restores conditions');
  assert((await page.locator('#text').inputValue())==='из Санкт-Петербурга','undo returns text to composer');
  await page.locator('#conditions-edit').click();
  await page.locator('#condition-field').selectOption('budget');
  await page.locator('#condition-value').fill('до 150000 рублей на всех');
  await page.locator('#condition-form button[type=submit]').click();
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  assert((await page.locator('#conditions').innerText()).includes('150'),'condition dialog applies budget');
  await page.locator('#chat-menu summary').click();await page.locator('#reset').click();
  await page.locator('#reset-cancel').click();
  assert(await page.locator('.msg.user').count()===2,'reset cancellation preserves conversation');
  await page.locator('#chat-menu summary').click();await page.locator('#reset').click();await page.locator('#reset-confirm').click();
  await page.waitForFunction(()=>document.querySelectorAll('.msg.user').length===0);
  assert(await page.locator('#trip-context').isHidden(),'confirmed new trip clears conditions');
  for(const [label,mood] of [['Море','sea'],['Снежные горы','alpine'],['Город','city'],['Лес и тишина','forest'],['Закаты вдвоём','sunset']]){
    await page.goto(base+'/');await ready();
    await page.getByRole('button',{name:'Пока не знаю',exact:true}).click();
    assert(await page.locator('.inspiration').isVisible(),`${mood}: inspiration opens on request`);
    await page.locator('.mood-choices').getByRole('button',{name:label,exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('#send').disabled);
    assert(await page.locator('body').getAttribute('data-mood')===mood,`${mood}: atmosphere selected`);
  }
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+'/');await ready();
  assert(await page.locator('#board').isHidden(),'mobile opens chat');
  assert(await page.locator('#text').isVisible(),'mobile composer visible');
  await page.locator('#stage-toggle').click();
  assert(await page.locator('#journey li:visible').count()===6,'mobile timeline expands');
  await page.locator('#stage-toggle').click();
  await page.locator('#mobile-map').click();
  assert(await page.locator('#board').isVisible(),'mobile globe accessible');
  await page.locator('#mobile-map').click();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no mobile horizontal overflow');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert(await page.locator('body').evaluate(el=>getComputedStyle(el).transitionDuration)==='0s','reduced motion respected');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.setViewportSize({width:1440,height:940});
  await page.addInitScript(()=>{
    window.__voiceStarted=0;window.__tracksStopped=0;
    Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>({getTracks:()=>[{stop:()=>window.__tracksStopped++}]})});
    class FakeRecognition{
      start(){window.__voiceStarted++;this.timer=setTimeout(()=>this.onstart?.(),10);}
      stop(){clearTimeout(this.timer);setTimeout(()=>{this.onresult?.({resultIndex:0,results:[{isFinal:true,0:{transcript:'хочу к морю'},length:1}]});this.onend?.();},30);}
      abort(){clearTimeout(this.timer);this.onend?.();}
    }
    window.SpeechRecognition=FakeRecognition;window.webkitSpeechRecognition=FakeRecognition;
  });
  await page.goto(base+'/');await ready();
  const hold=async()=>{const b=await page.locator('#send').boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.waitForTimeout(550);await page.mouse.up();};
  await hold();
  assert(await page.locator('#voice-dialog').isVisible(),'first hold explains voice processing');
  await page.locator('#voice-allow').click();
  await page.waitForFunction(()=>window.__tracksStopped>0);
  assert(await page.evaluate(()=>window.__voiceStarted)===0,'permission does not start hidden recording');
  await page.waitForTimeout(650);await hold();
  await page.waitForFunction(()=>document.querySelector('#text').value.includes('хочу к морю'));
  assert(await page.locator('.msg.user').count()===0,'release transcribes without sending');
  assert((await page.locator('#send').getAttribute('aria-label')).includes('Отправить'),'arrow restored after transcription');
  await page.waitForTimeout(650);await page.locator('#text').fill('На неделю.');await hold();
  await page.waitForFunction(()=>document.querySelector('#text').value.includes('хочу к морю'));
  assert((await page.locator('#text').inputValue()).startsWith('На неделю.'),'dictation preserves typed draft');
  await page.waitForTimeout(650);
  const b=await page.locator('#send').boundingBox();await page.mouse.move(b.x+20,b.y+20);await page.mouse.down();await page.waitForTimeout(450);
  await page.keyboard.press('Escape');await page.mouse.up();await page.waitForTimeout(80);
  assert(await page.locator('#voice-cancel').isHidden(),'Escape cancels recording');
  assert(await page.locator('.msg.user').count()===0,'cancel does not submit');
  await page.locator('#text').fill('');await page.locator('#text').press('Enter');
  assert(await page.locator('.msg.user').count()===0,'empty Enter does not start or send');
  await page.locator('#chat-menu summary').click();await page.locator('#dictate-menu').click();
  await page.waitForFunction(()=>document.querySelector('#send').dataset.listening==='true');
  await page.locator('#ask').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>document.querySelector('#text').value.includes('хочу к морю'));
  assert(await page.locator('.msg.user').count()===0,'menu dictation works without holding');
  await page.reload();await ready();
  return {passed:checks.length,checks};
}
