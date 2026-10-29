async (page) => {
 await page.route('**/missing-model-test/*.glb',r=>r.fulfill({status:404,body:'test missing model'}));
 const result=await page.evaluate(async()=>{
  const {createLandmarkRenderer}=await import('./integration/landmarks-3d.mjs');
  const events=new Map();const map={getCenter:()=>({lng:0}),getBearing:()=>0,on:(name,fn)=>events.set(name,fn),off:name=>events.delete(name)};
  const canvas=document.createElement('canvas');canvas.width=canvas.height=192;document.body.append(canvas);
  const renderer=createLandmarkRenderer(map,{assetBase:new URL('./missing-model-test/',location.href)});
  renderer.setTargets([{kind:'tower',lon:0,canvas}]);const ready=await renderer.ready();
  const state=canvas.dataset.modelState;const visible=canvas.getContext('2d').getImageData(0,0,192,192).data.some(x=>x);
  renderer.dispose();canvas.remove();
  return {expectedFailure:'HTTP 404 twice',failedIds:Object.keys(ready.errors),state,visible,remainingMapListeners:events.size};
 });
 if(result.state!=='fallback'||!result.visible||result.remainingMapListeners)throw Error(JSON.stringify(result));
 return result;
}
