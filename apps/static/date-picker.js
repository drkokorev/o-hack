/* Shared range picker. One complete range is one server update. */
window.openTripDates = ({start, end, today, onSelect, single=false}) => {
  document.getElementById('date-picker-dialog')?.remove();
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const parse=s=>new Date(`${s}T12:00:00`), min=today||iso(new Date()), max=iso(new Date(parse(min).getFullYear()+2,parse(min).getMonth(),parse(min).getDate()));
  let from=start>=min?start:null,to=end>from?end:null, selectingEnd=false;
  let month=parse(from||min);month.setDate(1);
  const dialog=document.createElement('dialog');dialog.id='date-picker-dialog';dialog.className='sheet date-picker';dialog.setAttribute('aria-label','Даты поездки');
  dialog.innerHTML='<button type="button" class="dialog-close icon-button" aria-label="Закрыть календарь">×</button><h2>Когда поедем?</h2><p class="range-hint" aria-live="polite"></p><div class="month-nav"><button type="button" class="icon-button previous" aria-label="Предыдущий месяц">‹</button><span></span><button type="button" class="icon-button next" aria-label="Следующий месяц">›</button></div><div class="months"></div><p class="date-picker-note">Выберите день начала и день возвращения.</p>';
  const fmt=new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long'});
  if(single)dialog.querySelector('.date-picker-note').textContent='Выберите день поездки.';
  function paint(){
    dialog.querySelector('.range-hint').textContent=single?'Дата поездки':selectingEnd?`${fmt.format(parse(from))} → выберите возвращение`:from&&to?`${fmt.format(parse(from))} — ${fmt.format(parse(to))}`:'Сначала — день начала поездки';
    dialog.querySelector('.previous').disabled=month.getFullYear()===parse(min).getFullYear()&&month.getMonth()<=parse(min).getMonth();
    dialog.querySelector('.next').disabled=iso(new Date(month.getFullYear(),month.getMonth()+1,1))>max;
    const area=dialog.querySelector('.months');area.replaceChildren();
    for(let n=0;n<2;n++){
      const m=new Date(month.getFullYear(),month.getMonth()+n,1),section=document.createElement('section');section.className='month';
      const heading=document.createElement('h3');heading.textContent=new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric'}).format(m);section.append(heading);
      const grid=document.createElement('div');grid.className='days';
      for(const day of ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']){const span=document.createElement('span');span.className='weekday';span.textContent=day;grid.append(span);}
      for(let i=0;i<(m.getDay()+6)%7;i++)grid.append(document.createElement('span'));
      for(let day=1;day<=new Date(m.getFullYear(),m.getMonth()+1,0).getDate();day++){
        const date=new Date(m.getFullYear(),m.getMonth(),day),value=iso(date),b=document.createElement('button');b.type='button';b.textContent=day;b.dataset.date=value;
        b.setAttribute('aria-label',new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric'}).format(date));
        b.disabled=value<min||value>max||(selectingEnd&&date-parse(from)>365*86400000);
        b.classList.toggle('range-edge',value===from||value===to);b.classList.toggle('in-range',!!from&&!!to&&value>from&&value<to);
        b.onclick=()=>{if(single){dialog.close();onSelect({start:value});}else if(!selectingEnd||value<=from){from=value;to=null;selectingEnd=true;paint();dialog.querySelector(`[data-date="${value}"]`)?.focus();}else{to=value;dialog.close();onSelect({start:from,end:to});}};
        grid.append(b);
      }section.append(grid);area.append(section);
    }
  }
  dialog.querySelector('.previous').onclick=()=>{month.setMonth(month.getMonth()-1);paint();};
  dialog.querySelector('.next').onclick=()=>{month.setMonth(month.getMonth()+1);paint();};
  dialog.querySelector('.dialog-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);paint();dialog.showModal();
};
