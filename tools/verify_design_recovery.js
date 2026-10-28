// Browser regression checks for globe, restored edits, failed resume and visible mic.
// Recognition and permission are explicit doubles; no microphone is recorded.
async (page) => {
  const base=new URL(page.url()).origin, checks=[], errors=[];
  const assert=(ok,name)=>{if(!ok)throw new Error(name);checks.push(name);};
  const idle=()=>page.waitForFunction(()=>!document.querySelector('#send').disabled);
  const send=async text=>{await page.locator('#text').fill(text);await page.locator('#ask').evaluate(f=>f.requestSubmit());await idle();};
  page.on('pageerror',error=>errors.push(error.message));
  await page.setViewportSize({width:1440,height:940});
  await page.goto(base+'/static/favicon.svg');
  await page.evaluate(()=>{sessionStorage.clear();localStorage.setItem('odin.tour.v1','seen');});
  await page.route('**/api/voice',route=>route.fulfill({json:{backend:'browser',status:'ready'}}));
  await page.addInitScript(()=>{
    window.__voiceStarted=0;window.__tracksStopped=0;
    Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>({getTracks:()=>[{stop:()=>window.__tracksStopped++}]})});
    class FakeRecognition {
      start(){window.__voiceStarted++;this.timer=setTimeout(()=>this.onstart?.(),10);}
      stop(){clearTimeout(this.timer);setTimeout(()=>{this.onresult?.({resultIndex:0,results:[{isFinal:true,0:{transcript:'хочу к морю'},length:1}]});this.onend?.();},30);}
      abort(){clearTimeout(this.timer);this.onend?.();}
    }
    window.SpeechRecognition=FakeRecognition;window.webkitSpeechRecognition=FakeRecognition;
  });
  await page.goto(base+'/');await idle();
  await page.waitForFunction(()=>tripMap.getView()?.earth && tripMap.getView()?.models?.includes('tower'),null,{timeout:30000});
  await page.waitForTimeout(800);
  const initial=await page.evaluate(()=>tripMap.getView());
  assert(initial.projection==='globe','real globe surface and models loaded');
  await page.screenshot({path:'output/playwright/review-desktop-start.png'});
  const box=await page.locator('.map-canvas').boundingBox();
  await page.mouse.move(box.x+box.width*.36,box.y+box.height*.65);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.43,box.y+box.height*.65,{steps:8});await page.mouse.up();
  await page.waitForTimeout(700);
  assert(await page.evaluate(x=>Math.abs(tripMap.getView().center[0]-x)>.2,initial.center[0]),'globe still rotates by dragging');
  await page.getByRole('button',{name:'Париж: Эйфелева башня'}).click();
  assert(await page.getByText('Хотите посетить это место?').isVisible(),'landmark remains selectable');
  await page.locator('#mic-button').click();
  assert(await page.locator('#voice-dialog').isVisible(),'visible microphone explains permission first');
  await page.locator('#voice-allow').click();await page.waitForFunction(()=>window.__tracksStopped>0);
  assert(await page.evaluate(()=>window.__voiceStarted)===0,'permission does not start hidden recording');
  await page.locator('#text').fill('На неделю.');await page.locator('#mic-button').click();
  await page.waitForFunction(()=>document.querySelector('#send').dataset.listening==='true');
  await page.locator('#mic-button').click();await page.waitForFunction(()=>document.querySelector('#text').value.includes('хочу к морю'));
  assert((await page.locator('#text').inputValue()).startsWith('На неделю.'),'microphone preserves typed draft');
  assert(await page.locator('.msg.user').count()===0,'dictation does not send automatically');
  await send('Хочу в Казань');await send('из Москвы');
  await page.locator('.latest-user .message-edit').click();await page.locator('#text').fill('из Санкт-Петербурга');
  await page.reload();await idle();
  assert(await page.locator('#edit-banner').isVisible(),'reload restores edit mode');
  assert(await page.locator('#text').inputValue()==='из Санкт-Петербурга','reload restores unsent edit');
  await page.locator('#ask').evaluate(f=>f.requestSubmit());await idle();
  assert(await page.locator('.msg.user').count()===2,'restored edit replaces the original turn');
  assert((await page.locator('#conditions').textContent()).includes('Санкт-Петербург'),'restored edit updates origin');
  await page.reload();await idle();await page.locator('#undo').click();await idle();
  assert(await page.locator('.msg.user').count()===1,'undo works after another reload');
  const session=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('odin.trip.v1')).session_id);
  const failed=route=>route.fulfill({status:503,json:{detail:'Сервис временно недоступен'}});
  await page.route('**/api/session',failed);await page.reload();await page.locator('#startup-error').waitFor();
  assert(await page.locator('#send').isDisabled(),'failed restore blocks accidental replacement with new session');
  assert(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('odin.trip.v1')).session_id)===session,'failed restore keeps saved session');
  await page.unroute('**/api/session',failed);await page.getByRole('button',{name:'Повторить',exact:true}).click();await idle();
  assert(await page.locator('.msg.user').count()===1,'retry restores existing conversation');
  await page.route('**/api/session',route=>route.fulfill({status:404,json:{detail:'Сессия завершилась'}}));
  await page.reload();await idle();
  assert((await page.locator('#log').innerText()).includes('Прошлая сессия завершилась'),'expired session explains new start');
  assert(await page.evaluate(()=>sessionStorage.getItem('odin.trip.v1'))===null,'expired session removes stale saved state');
  await page.unroute('**/api/session');
  assert(errors.length===0,'no browser JavaScript errors');
  return {checks,globe:initial,errors,voice:'explicit recognition and permission doubles'};
}
