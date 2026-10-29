/* Interaction shell. No dependency on the globe's rendering implementation. */
window.createExperience = ({send, reset, undo, edit, isBusy, voice, ideas}) => {
  const byId = (id) => document.getElementById(id);
  let summary = {}, selectedMood = "neutral", boardLabel = "Карта";
  const moodNames = {neutral:"Мир открыт",sea:"Ближе к морю",alpine:"Выше облаков",city:"В ритме города",forest:"Наедине с природой",sunset:"Навстречу закату"};
  const closeMenu = () => {};
  const show = (id) => { closeMenu(); const dialog = byId(id); if (!dialog.open) dialog.showModal(); };
  const fill = (text) => { byId("text").value = text; byId("text").dispatchEvent(new Event("input", {bubbles:true})); byId("text").focus(); };
  const setMood = (mood) => {
    selectedMood = mood in moodNames ? mood : "neutral";
    document.body.dataset.mood = selectedMood;
    document.dispatchEvent(new CustomEvent("odin:mood", {detail:{mood:selectedMood}}));
  };
  const settings = {
    origin:{prefix:"Я выезжаю из ",hint:"Например, Москва"},
    destination:{prefix:"Хочу в ",hint:"Например, Сочи"},
    dates:{prefix:"Даты поездки: ",hint:"Например, с 5 по 12 декабря 2026"},
    duration:{prefix:"Длительность поездки: ",hint:"Например, 7 дней"},
    people:{prefix:"",hint:"Например, 2 взрослых и ребёнок 8 лет"},
    budget:{prefix:"Бюджет: ",hint:"Например, до 150000 рублей на всех"},
    transport:{prefix:"Хочу добраться: ",hint:"Например, поездом"},
    other:{prefix:"",hint:"Например, нужен отель с бассейном"}
  };
  const values = () => ({origin:summary.origin || "",destination:summary.destination || "",
    dates:summary.date_from && summary.date_to ? `с ${summary.date_from.split("-").reverse().join(".")} по ${summary.date_to.split("-").reverse().join(".")}` : "",
    duration:summary.nights ? `${summary.nights} ночей` : "",
    people:[summary.adults ? `${summary.adults} взрослых` : "",summary.children ? `${summary.children} детей` : ""].filter(Boolean).join(" и "),
    budget:summary.budget_total ? `до ${summary.budget_total} рублей на всех` : "",
    transport:{plane:"самолётом",train:"поездом"}[summary.transport] || "",other:""});
  function fillCondition() {
    const key = byId("condition-field").value;
    byId("condition-value").value = values()[key] || "";
    byId("condition-value").placeholder = settings[key].hint;
  }
  function openCondition(key = "other") {
    if (isBusy()) return;
    if(key==="dates"){openDates();return;}
    byId("condition-field").value = key;
    fillCondition(); show("conditions-dialog"); byId("condition-value").focus();
  }
  function fieldFor(text) {
    if (/^из:/.test(text)) return "origin";
    if (/бюджет|₽/.test(text)) return "budget";
    if (/взросл|путешествен|ребён|детей/.test(text)) return "people";
    if (/ноч|поездка:/.test(text)) return "duration";
    if (/самолёт|поезд$/.test(text)) return "transport";
    if (/январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр/.test(text)) return "dates";
    if (text === summary.destination) return "destination";
    return "other";
  }
  function update(data) {
    summary = data?.trip_summary || {};
    let eventLine=byId('selected-event');
    if(!eventLine){eventLine=document.createElement('p');eventLine.id='selected-event';eventLine.className='selected-event';byId('trip-context').append(eventLine);}
    eventLine.hidden=!summary.selected_event;
    eventLine.textContent=summary.selected_event ? `${summary.selected_event.name} · ${summary.selected_event.dates}` : '';
    const stage = data?.stage || "start";
    boardLabel = ["plan","cart","payment","booked"].includes(stage) ? "Поездка" : "Карта";
    const titles = {start:"Куда хочется?",destination:"Туда, где вам хорошо",plan:"Выбираем то самое",cart:"Всё складывается",payment:"Почти поехали",booked:"Можно предвкушать"};
    byId("chat-title").textContent = stage === "start" && data?.understood?.length ? "Уточняем вашу поездку" : titles[stage] || titles.start;
    const types = summary.trip_types || [];
    let mood = types.some(t=>["sea","beach"].includes(t)) ? "sea" : types.some(t=>["ski","mountains"].includes(t)) ? "alpine" : types.some(t=>["city","culture"].includes(t)) ? "city" : types.includes("nature") ? "forest" : null;
    if (selectedMood === "alpine" && mood === "forest") mood = "alpine";
    if (selectedMood === "sunset" && (!mood || mood === "sea")) mood = "sunset";
    if (mood && mood !== selectedMood) setMood(mood);
    byId("conditions").querySelectorAll(".chip").forEach((chip) => {
      const button = document.createElement("button"); button.type = "button";
      button.className = chip.className; button.textContent = chip.textContent;
      button.title = `Изменить: ${chip.textContent}`;
      button.setAttribute("aria-label", button.title);
      button.addEventListener("click", () => openCondition(fieldFor(chip.textContent)));
      chip.replaceWith(button);
    });
    const items = Array.from(byId("stages").children), idx = Math.max(0, items.findIndex((n) => n.classList.contains("now")));
    items.forEach((item, i) => { if (i === idx) item.setAttribute("aria-current","step"); });
    byId("journey").setAttribute("aria-label", `Этапы поездки: ${items[idx]?.textContent || "Запрос"}, шаг ${idx + 1} из ${items.length || 6}`);
    document.body.classList.toggle("has-conversation", Boolean(data));
  }
  function configureExamples(info) {
    const examples = [
      ["Море и спокойствие","Хочу к морю из Москвы с 5 по 12 декабря 2026, 2 взрослых, до 180 тысяч рублей на всех. Отель 4 звезды, завтрак, недалеко от пляжа, без пересадок."],
      ["Выходные в городе","В Казань из Санкт-Петербурга с 4 по 7 декабря 2026, 2 взрослых с собакой. До 70 тысяч рублей на всех, поездом, отель рядом с центром."],
      ["Воздух гор","Хочу в горы в январе 2027 на неделю, из Москвы, 2 взрослых, до 200 тысяч рублей. Нужен отель с завтраком и красивым видом."]
    ];
    byId("example-list").replaceChildren(...examples.map(([label,text]) => {
      const b = document.createElement("button"); b.type="button"; b.className="example-card";
      const strong=document.createElement("strong"); strong.textContent=label; b.append(strong,text);
      b.onclick=()=> { byId("examples-dialog").close(); fill(text); }; return b;
    }));
  }
  byId("text").addEventListener("input", () => { const input=byId("text"); input.style.height="auto"; input.style.height=Math.min(input.scrollHeight,138)+"px"; });
  byId("text").addEventListener("keydown", (event) => {
    if(event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); byId("ask").requestSubmit(); }
  });
  byId("about-open").onclick=()=>show("about-dialog");
  byId("conditions-edit").onclick=()=>openCondition("destination");
  byId("condition-field").onchange=fillCondition;
  byId("condition-form").onsubmit=(event)=> {
    event.preventDefault(); const text=byId("condition-value").value.trim(); if(!text || isBusy()) return;
    const prefix=settings[byId("condition-field").value].prefix;
    byId("conditions-dialog").close(); send(prefix+text);
  };
  byId("reset").onclick=()=>{ if (!isBusy()) show("reset-dialog"); };
  byId("reset-cancel").onclick=()=>byId("reset-dialog").close();
  byId("reset-confirm").onclick=async()=> { if(isBusy()) return; byId("reset-dialog").close(); await reset(); setMood("neutral"); };
  byId("edit-cancel").onclick=()=>edit(null);
  byId("voice-cancel").onclick=()=>voice.cancel();
  byId("mobile-map").onclick=()=> {
    const visible=document.body.classList.toggle("show-map"); byId("mobile-map").textContent=visible ? "В чат" : boardLabel;
    byId("mobile-map").setAttribute("aria-expanded",String(visible)); window.dispatchEvent(new Event("resize"));
  };
  document.querySelectorAll("dialog").forEach((dialog)=>dialog.addEventListener("click",(event)=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
  return {update, setMood, fill, configureExamples, openCondition, openExamples:()=>show("examples-dialog"),
    showChat:()=>{document.body.classList.remove("show-map");byId("mobile-map").textContent=boardLabel;byId("mobile-map").setAttribute("aria-expanded","false");},
    moodLabel:()=>moodNames[selectedMood], showIdeas:()=>{ideas();document.body.classList.add("show-map");byId("mobile-map").textContent="В чат";byId("mobile-map").setAttribute("aria-expanded","true");window.dispatchEvent(new Event("resize"));},
    reset:()=>{summary={};setMood("neutral");byId("text").value="";byId("text").dispatchEvent(new Event("input",{bubbles:true}));update(null);byId("edit-banner").hidden=true;}};
};
