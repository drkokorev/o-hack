// Open the application with playwright-cli; no real model key is needed.
async (page) => {
 const base=new URL(page.url()).origin;let requests=0;
 await page.unrouteAll({behavior:'ignoreErrors'});
 await page.addInitScript(()=>{window.SpeechRecognition=class {
   start(){window.__speech=this;} stop(){this.onend?.();}
 };});
 page.on('request',r=>{if(r.url().endsWith('/api/chat'))requests++;});
 await page.setViewportSize({width:1440,height:900});await page.goto(base+'/');
 await page.getByText(/записей в области/).waitFor({timeout:30000});
 await page.getByLabel('Голосовой ввод').click();
 await page.locator('#text').fill('Ищу поездку');
 await page.evaluate(()=>{window.__speech.onresult({resultIndex:0,results:[Object.assign([{transcript:'в Париж'}],{isFinal:true})]});window.__speech.onend();});
 const recognized=await page.locator('#text').inputValue();
 if(recognized !== 'Ищу поездку в Париж')throw Error('Unexpected speech result: '+recognized);
 if(requests)throw Error('Speech was sent without user action');
 await page.locator('#text').fill('Из Москвы в Сочи с 5 по 12 декабря 2026 года, двое взрослых, перелёт, живём в палатках');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/chat'));
 await page.locator('#text').press('Enter');const data=await(await response).json();
 if(data.payload?.kind!=='tent_transport')throw Error('Tent trip did not reach transport alternatives: '+data.payload?.kind);
 await page.getByText('Дорога и своя палатка',{exact:true}).waitFor();
 if(!(await page.locator('#view').innerText()).includes('Отель не включён'))throw Error('Tent trip wrongly includes hotel');
 return {speechEditable:'pass',notSentAutomatically:'pass',tentTransport:'pass'};
}
