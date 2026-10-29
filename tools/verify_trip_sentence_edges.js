// Additional interaction boundaries, run after verify_trip_sentence.js.
async page => {
  const checks=[];
  const ok=(value,name)=>{if(!value)throw Error(name);checks.push(name);};
  const idle=()=>page.waitForFunction(()=>!document.querySelector('#send').disabled);
  const apply=async(key,text)=>{
    await page.locator(`[data-trip-field="${key}"]`).click();await page.locator('#condition-value').fill(text);
    const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/chat'&&r.request().method()==='POST');
    await page.locator('#condition-form [type=submit]').click();const data=await(await response).json();await idle();return data;
  };
  try {
    const original=await page.evaluate(()=>lastData.trip_summary);
    const shorter=await apply('duration','7 ночей');
    ok(shorter.trip_summary.nights===7 && shorter.trip_summary.origin===original.origin && shorter.trip_summary.budget_total===original.budget_total,'duration edit retains origin and budget');
    await page.locator('.latest-user .message-edit').click();
    const count=await page.locator('#log .user').count();
    await apply('budget','до 200000 рублей на всех');
    ok(await page.locator('#log .user').count()===count+1 && await page.locator('#edit-banner').isHidden(),'summary refinement does not overwrite a message being edited');
    const noOp=await page.locator('#log .user').count();
    await page.locator('[data-trip-field="budget"]').click();await page.locator('#condition-form [type=submit]').click();
    ok(await page.locator('#log .user').count()===noOp && await page.locator('#conditions-dialog').isHidden(),'unchanged field closes without a redundant request');
    const rendered=await page.evaluate(()=>{
      const area=document.createElement('div');let clicked;
      const renderer=createTripSentence({container:area,onEdit:key=>{clicked=key;}});
      const remaining=renderer.render({trip_summary:{origin:'<img src=x onerror=alert(1)>',destination:'Неизвестный город',date_from:'2026-12-28',date_to:'2027-01-05',nights:8,adults:2,children:1},
        understood:['8 ночей','2 взрослых','1 ребёнок','возраст детей: 8 лет (на дату заезда)','без пересадок'],assumptions:[]},{places:[],origins:[]});
      area.querySelector('[data-trip-field="origin"]').click();
      return {text:area.textContent,remaining,hasImage:!!area.querySelector('img'),clicked};
    });
    ok(rendered.text.includes('2026')&&rendered.text.includes('2027'),'date range crossing years shows both years');
    ok(!rendered.hasImage && rendered.clicked==='origin','unknown place names remain inert text inside a working control');
    ok(rendered.remaining.length===2&&rendered.remaining[0].includes('возраст детей'),'duplicate filtering preserves child ages and separate constraints');
    await page.locator('#theme-toggle').click();
    await page.waitForFunction(()=>getComputedStyle(document.querySelector('.trip-word')).color===getComputedStyle(document.documentElement).getPropertyValue('--accent').trim().replace('#aac3ff','rgb(170, 195, 255)').replace('#0e41d2','rgb(14, 65, 210)'));
    ok(true,'sentence controls settle to the active theme color');
    return {status:'PASS',checks,duration:{from:shorter.trip_summary.date_from,to:shorter.trip_summary.date_to,nights:shorter.trip_summary.nights}};
  } catch(error) {return {status:'FAIL',failure:error.message,checks};}
}
