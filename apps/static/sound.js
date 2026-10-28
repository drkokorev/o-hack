/* Optional, short ambient cues synthesized locally after explicit opt-in. */
(() => {
  const button=document.getElementById("sound-toggle");
  if(!button)return;
  const Audio=window.AudioContext || window.webkitAudioContext;
  let enabled=false,recording=false,context=null,master=null,lastPlayed=-Infinity,mood="neutral";
  try{enabled=localStorage.getItem("odin.sound")==="on";}catch(_){}
  if(!Audio)enabled=false;
  function update(){
    button.disabled=!Audio;button.setAttribute("aria-pressed",String(enabled));
    button.setAttribute("aria-label",enabled?"Выключить звуки":"Включить звуки");
    button.title=enabled?"Звуки атмосферы включены":"Звуки атмосферы выключены";
    if(master&&context)master.gain.setTargetAtTime(enabled&&!recording&&!document.hidden?1:0,context.currentTime,.06);
  }
  function play(kind){
    if(!enabled||recording||document.hidden||!Audio||performance.now()-lastPlayed<2500)return;
    lastPlayed=performance.now();
    try{
      if(!context){context=new Audio();master=context.createGain();master.connect(context.destination);}
      update();if(context.state==="suspended")context.resume().catch(()=>{});
      const now=context.currentTime,duration=2;
      if(["sea","alpine","forest"].includes(kind)){
        const buffer=context.createBuffer(1,context.sampleRate*duration,context.sampleRate),data=buffer.getChannelData(0);
        for(let i=0;i<data.length;i++)data[i]=Math.random()*2-1;
        const source=context.createBufferSource(),filter=context.createBiquadFilter(),gain=context.createGain();
        source.buffer=buffer;filter.type=kind==="alpine"?"bandpass":"lowpass";
        filter.frequency.value={sea:450,alpine:850,forest:1200}[kind];filter.Q.value=.4;
        gain.gain.setValueAtTime(.0001,now);gain.gain.exponentialRampToValueAtTime(.016,now+.6);gain.gain.exponentialRampToValueAtTime(.0001,now+duration);
        source.connect(filter);filter.connect(gain);gain.connect(master);source.start(now);source.stop(now+duration);
        source.onended=()=>{source.disconnect();filter.disconnect();gain.disconnect();};
      }else{
        const notes=kind==="sunset"?[220,329.63]:kind==="city"?[293.66,440]:[392];
        notes.forEach((note,index)=>{const oscillator=context.createOscillator(),gain=context.createGain();
          oscillator.type="sine";oscillator.frequency.value=note;const start=now+index*.16;
          gain.gain.setValueAtTime(.0001,start);gain.gain.exponentialRampToValueAtTime(.012,start+.08);gain.gain.exponentialRampToValueAtTime(.0001,start+1.2);
          oscillator.connect(gain);gain.connect(master);oscillator.start(start);oscillator.stop(start+1.2);
          oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
        });
      }
    }catch(_){}
  }
  button.onclick=()=>{enabled=!enabled;try{localStorage.setItem("odin.sound",enabled?"on":"off");}catch(_){}update();if(enabled)play(mood);};
  document.addEventListener("odin:mood",(event)=>{const next=event.detail.mood;if(next!==mood){mood=next;if(mood!=="neutral")play(mood);}});
  document.addEventListener("odin:recording",(event)=>{recording=event.detail.recording;update();});
  document.addEventListener("visibilitychange",update);
  update();
})();
