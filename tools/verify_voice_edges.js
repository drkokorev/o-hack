/* Explicit voice doubles: no microphone recording or transcription service. */
async (page) => {
  const checks=[];
  const check=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  await page.addInitScript(()=>{
    Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>({getTracks:()=>[{stop(){}}]})});
    class VoiceDouble {
      start(){this.timer=setTimeout(()=>this.onstart?.(),10);}
      stop(){clearTimeout(this.timer);setTimeout(()=>{this.onresult?.({resultIndex:0,results:[{isFinal:true,0:{transcript:'Хочу в Казань'},length:1}]});this.onend?.();},10);}
      abort(){clearTimeout(this.timer);this.onend?.();}
    }
    window.SpeechRecognition=VoiceDouble;
  });
  await page.setViewportSize({width:1440,height:940});
  await page.goto('http://127.0.0.1:8091/');await page.locator('#suggest button').first().waitFor();
  const b=await page.locator('#send').boundingBox();
  const press=async()=>{await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();};
  await press();await page.waitForTimeout(450);await page.mouse.up();
  await page.locator('#voice-allow').click();await page.waitForTimeout(700);
  await press();await page.waitForFunction(()=>document.querySelector('#send').dataset.listening==='true');
  await page.waitForFunction(()=>document.querySelector('#text').value==='Хочу в Казань',{},{timeout:25000});
  check(await page.locator('.msg.user').count()===0,'20 second limit transcribes without sending');
  await page.mouse.up();await page.waitForTimeout(650);
  check(await page.locator('.msg.user').count()===0,'release after automatic stop does not submit');
  await page.locator('#send').click();await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  check(await page.locator('.msg.user').count()===1,'short pointer click sends exactly once');
  check(await page.locator('#text').inputValue()==='','successful short click clears composer');
  await page.locator('#text').fill('Сохранённый черновик');
  await press();await page.waitForFunction(()=>document.querySelector('#send').dataset.listening==='true');
  await page.locator('#send').dispatchEvent('pointercancel',{pointerId:1});await page.mouse.up();
  await page.waitForTimeout(100);
  check(await page.locator('#text').inputValue()==='Сохранённый черновик','pointer cancellation preserves draft');
  check(await page.locator('.msg.user').count()===1,'pointer cancellation never sends');
  return {passed:checks.length,checks};
}
