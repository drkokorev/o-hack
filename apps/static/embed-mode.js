window.ODIN_EMBED=new URLSearchParams(location.search).get('embed')==='1';
if(window.ODIN_EMBED)document.documentElement.classList.add('embedded');
window.createEmbeddedMap=()=>({setData(){},draw(){},setCountry(){},showPoint(){},getView(){return null;},retry(){},unavailable(){},reset(){}});
