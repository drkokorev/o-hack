async (page)=>{
 const base=new URL(page.url()).origin;
 const ratio=(bg,fg)=>{const lum=s=>{const c=s.match(/\d+/g).slice(0,3).map(x=>Number(x)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]};const a=lum(bg),b=lum(fg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
 const results={};
 for (const scheme of ['light','dark']) {
  await page.emulateMedia({colorScheme:scheme,reducedMotion:'reduce'});await page.goto(base+'/');
  await page.locator('.composer button').first().waitFor();
  const colors=await page.locator('.composer button').first().evaluate(e=>{const s=getComputedStyle(e);return [s.backgroundColor,s.color]});
  results[scheme]=ratio(...colors);if(results[scheme]<4.5)throw Error('Composer contrast is too low in '+scheme);
 }
 await page.emulateMedia({colorScheme:'light'});await page.goto(base+'/static/widget.html');
 await page.locator('.send').waitFor();const colors=await page.locator('.send').evaluate(e=>{const s=getComputedStyle(e);return [s.backgroundColor,s.color]});
 results.widget=ratio(...colors);if(results.widget<4.5)throw Error('Widget contrast is too low');
 return results;
}
