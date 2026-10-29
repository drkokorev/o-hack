window.addEventListener('message',e=>{if(e.source===parent&&e.data?.type==='odin-widget-hidden')document.querySelector('iframe').contentWindow.postMessage(e.data,location.origin);});
