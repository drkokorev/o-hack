// Run with playwright-cli against a local rules-mode server.
async (page) => {
  const base=new URL(page.url()).origin,errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:1440,height:900});
  await page.goto(base+'/');
  await page.waitForFunction(()=>tripMap.getView()?.earth===true,null,{timeout:30000});
  await page.evaluate(()=>tripMap.setCountry('FR',true));
  const paris=page.getByRole('button',{name:'Париж: Эйфелева башня'});
  await paris.waitFor({timeout:30000});
  await page.waitForFunction(()=>tripMap.getView().models.includes('tower'),null,{timeout:30000});
  await paris.click();
  const popup=page.locator('.map-pop');
  if (!await popup.getByText('Хотите посетить это место?').isVisible()) throw Error('Paris card missing');
  const grouped=popup.locator('.map-nearby summary').filter({hasText:'Ещё мест на этом участке'});
  if (!await grouped.isVisible()) throw Error('Nearby landmarks were not grouped');
  await grouped.click();
  const choices=grouped.locator('..').locator('button');
  if (!await choices.count()) throw Error('Grouped places cannot be opened');
  await choices.first().click();
  if (!await popup.getByText('Биг-Бен',{exact:true}).isVisible()) throw Error('Grouped place opened the wrong card');
  await page.locator('.maplibregl-popup-close-button').click();
  await paris.click();
  if (!await popup.getByText('Эйфелева башня',{exact:true}).isVisible()) throw Error('Paris could not be reopened');
  await popup.getByRole('button',{name:'Посмотреть ближе'}).click();
  await page.waitForFunction(()=>Math.abs(tripMap.getView().center[0]-2.294478)<.001 && Math.abs(tripMap.getView().center[1]-48.858297)<.001,null,{timeout:10000});
  await page.evaluate(()=>window.__parisMarker=document.querySelector('[aria-label="Париж: Эйфелева башня"]'));
  async function measureTower() {
    // Exclude labels and badges from the pixel sample of the actual 3D mesh.
    const overlayStyle=await page.addStyleTag({content:'.landmark-label,.landmark-count,.event-label,.event-count{visibility:hidden !important}'});
    const encoded=(await page.locator('.map-surface').screenshot()).toString('base64');
    await overlayStyle.evaluate(element=>element.remove());
    return page.evaluate(async (encoded)=>{
      const image=new Image();image.src='data:image/png;base64,'+encoded;await image.decode();
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
      const scale=canvas.width/document.querySelector('.map-surface').clientWidth;
      const cx=canvas.width/2,cy=canvas.height/2;let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity,count=0;
      for(let y=Math.floor(cy-70*scale);y<=Math.floor(cy+3*scale);y++) for(let x=Math.floor(cx-28*scale);x<=Math.floor(cx+28*scale);x++){
        const i=(y*canvas.width+x)*4,r=pixels[i],g=pixels[i+1],b=pixels[i+2];
        if(r>105 && r>g*1.07 && g>b*1.08 && r-b>25){count++;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
      }
      return {count,height:count ? (maxY-minY+1)/scale : 0,width:count ? (maxX-minX+1)/scale : 0};
    },encoded);
  }
  const sizes=[];
  for(let step=0;step<=8;step++){
    if(step){await page.getByRole('button',{name:'Приблизить карту'}).click();await page.waitForTimeout(180);}
    if([0,4,8].includes(step)){
      await page.waitForTimeout(250);
      const view=await page.evaluate(()=>tripMap.getView());
      if(!await paris.isVisible()) throw Error('Paris disappeared while centered at zoom '+view.zoom);
      if(!await page.evaluate(()=>window.__parisMarker===document.querySelector('[aria-label="Париж: Эйфелева башня"]')))
        throw Error('Paris marker was recreated while zooming');
      const size=await measureTower();
      if(size.count<50 || size.height<20 || size.height>80 || size.width>60) throw Error('Invalid rendered model size: '+JSON.stringify(size));
      sizes.push({zoom:view.zoom,...size});
    }
  }
  if(Math.max(...sizes.map(x=>x.height))/Math.min(...sizes.map(x=>x.height))>1.35) throw Error('Model size changes too much: '+JSON.stringify(sizes));
  await paris.click();
  if (!await popup.getByRole('button',{name:'Выбрать город'}).isVisible()) throw Error('Paris is not clickable at close zoom');
  const within=await page.evaluate(()=>{
    const a=document.querySelector('.map-canvas').getBoundingClientRect(),b=document.querySelector('.maplibregl-popup').getBoundingClientRect();
    return b.left>=a.left-1 && b.right<=a.right+1 && b.top>=a.top-1 && b.bottom<=a.bottom+1;
  });
  if(!within) throw Error('Popup extends outside the map');
  if(errors.length) throw Error('JavaScript errors: '+errors.join('; '));
  return {stableMarker:'pass',groupedPlaces:'pass',focus:'pass',sizes,popupInsideMap:'pass',errors};
}
