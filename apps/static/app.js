const $ = (id) => document.getElementById(id);
let sessionId = null, busy = false, info = null, conversationStarted = false, imageCredits = {};
let inspiration = {starters:[], places:[], quick:{}};
let lastDestination = null;
// Bundled local database on our server; never query an external IP service.
const approximateCity = fetch("/api/visitor-city", {cache:"no-store", credentials:"same-origin", referrerPolicy:"no-referrer"})
  .then((response) => response.ok ? response.json() : null)
  .then((data) => typeof data?.origin === "string" && data.origin.length <= 100 ? data.origin : null)
  .catch(() => null);
let preferenceData = { saved: {}, hidden: [] };
try {
  const stored = JSON.parse(localStorage.getItem("odin.places") || "null");
  if (stored && stored.saved && Array.isArray(stored.hidden)) preferenceData = stored;
} catch (_) {}
const persistPlaces = () => { try { localStorage.setItem("odin.places", JSON.stringify(preferenceData)); } catch (_) {} };
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
  return node;
}
const marks = (cls, items) => el("ul", { class: "marks " + cls }, items.map((t) => typeof t === "string" ? el("li", {}, t) : el("li", { class: t.level }, t.text)));
const sayBtn = (label, text, cls = "btn ghost") => el("button", { type: "button", class: cls, onclick: () => send(text || label) }, label);
const destinationBtn = (label, place, cls = "btn ghost") => el("button", {type:"button", class:cls,
  onclick:()=>send(`Хочу в ${place.name}`, {destination_id:place.id})}, label);

const tripMap = (window.ODIN_EMBED ? createEmbeddedMap : createTripMap)({ container: $("map"), onChoose: (place) => {
  if (place.kind === "hotel") return send(`Хочу остановиться в «${place.name}»`, {map_point_id:place.id});
  const known = (info?.places || []).find(item => item.id === place.id ||
    (item.name === place.name && Number.isFinite(place.lat) && Number.isFinite(place.lon) &&
      Math.hypot(item.lat-place.lat,item.lon-place.lon)<0.01));
  if (known && !place.event && !place.landmark) return send(`Хочу в ${known.name}`, {destination_id:known.id});
  if (place.kind === "country") return send(`Хочу поехать: ${place.name}`, {map_country_code:place.code});
  if (place.kind === "city") return send(`Хочу поехать: ${place.name}${place.country_name ? `, ${place.country_name}` : ""}`,
    {map_city_id:place.id});
  if (place.event) return send(`Хочу поехать на ${place.event} в ${place.name}`, {event_id:place.id});
  if (place.landmark) return send(`Хочу посетить ${place.landmark}, ${place.name}`);
  return send(`Хочу поехать в ${place.name}${place.country_name ? `, ${place.country_name}` : ""}`);
},
  isFavorite: (point) => Boolean(preferenceData.saved[`point:${point.id}`]), onFavorite: (point) => {
    const key = `point:${point.id}`;
    if (preferenceData.saved[key]) delete preferenceData.saved[key];
    else preferenceData.saved[key] = {kind:"point",name:point.name || "Место",id:point.id,lat:point.lat,lon:point.lon};
    persistPlaces(); renderSaved(); return Boolean(preferenceData.saved[key]);
  } });
const drawMap = (options = {}) => tripMap.draw(options);
const preferences = createPreferences(tripMap);
const voice = createVoiceInput({input:$("text"), button:$("send"), microphone:$("mic-button"), status:$("voice-status"), holdToTalk:false});
let lastData = null, latestTurn = null, editing = false;
const experience = createExperience({send:sendTripChange, reset:resetConversation, undo:undoTurn, edit:editTurn,
  isBusy:()=>busy, voice, ideas:renderWelcome});
const tripStorage = createTripStorage();
const journeyUI = createJourneyUI({fill:experience.fill, onTransfer:changeTransfer});
const tripSentence = createTripSentence({container:$("trip-sentence-text"), onEdit:key=>experience.openCondition(key)});
const tripContextLayout = createTripContextLayout();
experience.showChat = () => journeyUI.show("chat", false);
experience.showIdeas = () => {renderWelcome();journeyUI.show("results");};

function renderHead(data) {
  const p=data?.payload||{},stage=data?.stage||'start';
  const title={start:data?.understood?.length?'Уточним вашу поездку':'Соооберём вашу поездку',destination:'Туда, где вам хорошо',plan:'Выберем то самое',cart:'Всё складывается',payment:'Почти поехали',booked:'Можно предвкушать',hotel_search:'Найдём тот самый отель',transfer_search:'Встретим и довезём',flight_search:'Выберем дорогу'}[stage]||'Соооберём вашу поездку';
  const trip=p.trip||(p.order&&{origin:p.order.origin,dest:p.order.dest});
  const route=trip?.dest?[trip.origin,trip.dest].filter(Boolean).join(' → '):null;
  const subtitle=route||(!data?'Отель, дорога и трансферы — по вашим пожеланиям.':null);
  $("head").replaceChildren(el('div',{class:'hero'},el('h1',{},title),subtitle?el('p',{class:route?'stage-route':null},subtitle):null));
  if(trip?.dest)routeWeather(trip,data.trip_summary);
}

function renderConditions(data) {
  const understood = data?.understood || [], assumed = data?.assumptions || [];
  $("trip-context").hidden = !data || (!understood.length && !assumed.length && !data.trip_summary);
  // The optional structured field is authoritative. Older services only expose
  // a list, so recognise a destination there only when it matches their catalog.
  const knownPlaces = new Map((info?.places || []).map((p) => [p.name.toLocaleLowerCase("ru"), p.name]));
  const destination = data?.trip_summary?.destination || understood.map((value) =>
    knownPlaces.get(String(value).trim().toLocaleLowerCase("ru"))).find(Boolean) || null;
  const changed = destination && lastDestination && destination !== lastDestination;
  $("condition-change").hidden = !changed;
  $("condition-change").textContent = changed ? `${lastDestination} → ${destination}` : "";
  lastDestination = destination;
  const extra = tripSentence.render(data, info);
  renderTripWishes({values:extra, assumptions:assumed, onEdit:(key,text)=>experience.openCondition(key,text), busy});
  tripContextLayout.update(data);

}

function renderSaved() {
  const entries = Object.entries(preferenceData.saved);
  $("saved-places").hidden = false;
  $("saved-count").textContent = entries.length ? String(entries.length) : "";
  $("saved-list").replaceChildren(...entries.map(([id, saved]) => {
    const item = typeof saved === "string" ? {name:saved,kind:"city"} : saved;
    if (!item?.name) return null;
    let target = item.kind === "hotel" ? el("span", {}, item.name, el("small", {}, " · размещение")) : item.kind === "point" ?
      el("button", {type:"button", onclick:() => tripMap.showPoint(item)}, item.name, el("small", {}, " · на глобусе")) :
      el("button", { type: "button", onclick: () => send(`хочу в ${item.name}`) }, item.name);
    if (item.kind === "hotel" && item.url) {
      try { const u = new URL(item.url); if (["http:", "https:"].includes(u.protocol))
        target = el("a", {href:u.href, target:"_blank", rel:"noopener noreferrer"}, item.name, el("small", {}, " · на карте ↗"));
      } catch (_) {}
    }
    return el("div", { class: "saved-row" }, target,
    el("button", { type: "button", class: "saved-remove", "aria-label": `Убрать ${item.name} из избранного`, onclick: () => {
      delete preferenceData.saved[id]; persistPlaces(); renderSaved();
      const button = document.querySelector(`[data-save-key="${CSS.escape(id)}"]`);
      if (button) { button.setAttribute("aria-pressed", "false"); button.replaceChildren(odinIcon("heart")); }
    } }, odinIcon("close")));
  }).filter(Boolean));
}
function renderHidden() {
  const list=$("hidden-list");if(!list)return;
  list.replaceChildren(...preferenceData.hidden.map(key=>el("div",{class:"saved-row"},el("span",{},preferenceData.hiddenNames?.[key]||key.replace(/^hotel:/,"")),el("button",{type:"button",class:"text-button",onclick:()=>{
    preferenceData.hidden=preferenceData.hidden.filter(k=>k!==key);persistPlaces();
    $("view").querySelectorAll(`[data-option-key="${CSS.escape(key)}"]`).forEach(cell=>{cell.hidden=false;});
    renderHidden();
  }},"Вернуть"))));
  $("hidden-empty").hidden=preferenceData.hidden.length>0;
}
function selectionPreferences(){return {saved:Object.keys(preferenceData.saved).slice(0,100),hidden:preferenceData.hidden.slice(0,100)};}
function openDates(single=false){
  const s=lastData?.trip_summary||{},event=s.selected_event;
  const eventStart=event?.start && info?.today ? (event.start>info.today?event.start:info.today) : event?.start;
  openTripDates({single,start:s.date_from||eventStart,end:s.date_to,today:info?.today,event,
    onSelect:range=>single?sendTripChange(`на ${range.start.split('-').reverse().join('.')}`):sendTripChange(`Даты поездки: с ${range.start.split('-').reverse().join('.')} по ${range.end.split('-').reverse().join('.')}`,{date_range:range})});
}
function datesButton(){return el("button",{type:"button",class:"btn ghost date-range-open",onclick:()=>openDates()},"Изменить даты");}
function routeWeather(trip, summary){
  if(!trip.dest_id||!summary?.date_from||!summary?.date_to)return;
  const line=el('p',{class:'route-weather',role:'status'},'Загружаем погоду…');$("head").append(line);
  fetch('/api/weather?'+new URLSearchParams({destination_id:trip.dest_id,start:summary.date_from,end:summary.date_to})).then(r=>r.ok?r.json():null).then(w=>{
    if(!line.isConnected)return;
    const temp=t=>`${t>0?'+':''}${t}°`;
    line.textContent=w?.status==='forecast'?`Прогноз: днём ${temp(w.day)}, ночью ${temp(w.night)}${w.partial?` · ${w.start.slice(8)}.${w.start.slice(5,7)}–${w.end.slice(8)}.${w.end.slice(5,7)}`:''}`:w?.status==='later'?'Прогноз появится ближе к поездке':'Прогноз пока недоступен';
    if(w?.status==='forecast'){line.title='Open-Meteo · '+w.start+' — '+w.end;}
  }).catch(()=>{line.textContent='Прогноз пока недоступен';});
}
function decorateOptions(payload) {
  if (!["ideas", "destinations", "hotels", "packages"].includes(payload.kind)) return;
  const cards = [...$("view").querySelectorAll(".cards > .card")];
  const section = $("view").querySelector(".cards");
  if (!section) return;
  (payload.items || []).forEach((entry, index) => {
    const isHotel = ["hotels", "packages"].includes(payload.kind);
    const place = payload.kind === "packages" ? entry.hotel : entry;
    const card = cards[index]; if (!card || !place || !place.name) return;
    const key = (isHotel ? "hotel:" : "") + String(place.id || place.name);
    card.dataset.optionKey=key;
    card.hidden = preferenceData.hidden.includes(key);
    const actions = el("div",{class:"card-feedback"});card.prepend(actions);
    const saved = el("button", { type: "button", class: "feedback-button", "data-save-key": key,
      "aria-label": `В избранное: ${place.name}`, "aria-pressed": String(Boolean(preferenceData.saved[key])),
      title: "Сохранить и учитывать при следующем подборе", onclick: () => {
        if (preferenceData.saved[key]) delete preferenceData.saved[key];
        else preferenceData.saved[key] = {name:place.name, kind:isHotel ? "hotel" : "city", url:isHotel ? place.map_url || null : null};
        saved.setAttribute("aria-pressed", String(Boolean(preferenceData.saved[key])));
        saved.replaceChildren(odinIcon("heart",Boolean(preferenceData.saved[key]))); persistPlaces(); renderSaved();
      } }, odinIcon("heart",Boolean(preferenceData.saved[key])));
    const hide = el("button", { type: "button", class: "feedback-button", "aria-label": `Скрыть: ${place.name}`,
      title: "Больше не предлагать", onclick: () => {
        if (!preferenceData.hidden.includes(key)) preferenceData.hidden.push(key);
        preferenceData.hiddenNames ||= {};preferenceData.hiddenNames[key]=place.name;
        persistPlaces(); card.hidden = true;
        $("view").querySelectorAll(`[data-option-key="${CSS.escape(key)}"]`).forEach((cell) => {cell.hidden=true;});
        renderHidden();
      } });
    hide.innerHTML = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 10v9H4v-9h3Zm2 0 3-6c.4-.7 1-1 1.6-.7l.3.1c.7.3.9 1 .7 1.7L14 8h4.2c1.2 0 2 1.1 1.7 2.2l-1.4 5c-.2.8-.9 1.3-1.7 1.3H11a2 2 0 0 1-2-2V10Z" transform="rotate(180 12 12)" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';
    actions.append(saved, hide);
  });
  renderHidden();
}

function savedDestinationPhotos(id) {
  if (!id) return [];
  const keys = [`dest/${id}.jpg`, ...Object.keys(imageCredits).filter((key) => key.startsWith(`gallery/${id}-`)).sort()];
  return keys.filter((key) => imageCredits[key]).map((key) => ({src:`/static/img/${key}`,
    credit:`${imageCredits[key].author}, ${imageCredits[key].license}`, page:imageCredits[key].page}));
}
function renderWelcome() {
  const cards = (inspiration.places || []).map(({id, label}) => {
    const place = (info?.places || []).find((item) => item.id === id);
    const picture = savedDestinationPhotos(id)[0];
    if (!place || !picture) return null;
    return el("article", {class:"inspire-card"}, photo(picture, {alt:place.name}),
      el("button", {type:"button", class:"inspire-select", "aria-label":`Выбрать ${place.name}`,
        onclick:() => send(`Хочу в ${place.name}`, {destination_id:place.id})}, el("span", {}, label), el("strong", {}, place.name), el("i", {"aria-hidden":"true"}, "↗")));
  }).filter(Boolean);
  if (!cards.length) { $("view").replaceChildren(); return; }
  $("view").replaceChildren(el("section", {class:"inspiration"}, el("div", {class:"inspiration-head"},
    el("h2", {}, "Для вдохновения"), el("span", {}, "С чего начнём?")), el("div", {class:"inspiration-grid"}, cards)));
  journeyUI.update({payload:{kind:"ideas",items:cards}});
}

function photo(img, opts = {}) {
  if (!img) return null;
  return el("div", { class: "photo " + (opts.cls || "") },
    el("img", { src: img.src, alt: opts.alt || "", loading: "lazy", decoding: "async" }),
    opts.badge ? el("span", { class: "badge-ill" }, opts.badge) : null,
    opts.over || null,
    el("a", { class: "credit", href: img.page || "#", target: "_blank", rel: "noopener", title: "Фото: " + img.credit,
      "aria-label": "Фото: " + img.credit + ". Сведения об авторе и лицензии" }, "ⓘ"));
}
// Несколько фото направления — листаются свайпом, стрелками и точками; у каждого снимка своя подпись автора
function gallery(imgs, opts = {}) {
  imgs = (imgs || []).filter(Boolean);
  if (imgs.length < 2) return photo(imgs[0], opts);
  const dots = imgs.map((_, i) => el("i", { class: i ? "" : "on" }));
  const track = el("div", { class: "track" }, imgs.map((img, i) => el("div", { class: "slide" },
    el("img", { src: img.src, alt: opts.alt ? `${opts.alt}, фото ${i + 1}` : "", loading: "lazy", decoding: "async" }),
    el("a", { class: "credit", href: img.page || "#", target: "_blank", rel: "noopener", title: "Фото: " + img.credit,
      "aria-label": "Фото: " + img.credit + ". Сведения об авторе и лицензии" }, "ⓘ"))));
  const go = (dir) => track.scrollBy({ left: dir * track.clientWidth, behavior: "smooth" });
  track.addEventListener("scroll", () => {
    const i = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
    dots.forEach((d, j) => d.classList.toggle("on", j === i));
  }, { passive: true });
  return el("div", { class: "photo gal " + (opts.cls || "") }, track,
    el("button", { type: "button", class: "nav prev", "aria-label": "Предыдущее фото", onclick: () => go(-1) }, "‹"),
    el("button", { type: "button", class: "nav next", "aria-label": "Следующее фото", onclick: () => go(1) }, "›"),
    el("div", { class: "dots" }, dots), opts.over || null);
}
function hotelSource(h) {
  if (h.source !== "overture") return el("div", { class: "src" }, "Модельный отель прототипа");
  return el("div", { class: "src" }, "Настоящий объект · ",
    el("a", { href: h.map_url, target: "_blank", rel: "noopener" }, "на карте"),
    h.website ? [" · ", el("a", { href: h.website.startsWith("http") ? h.website : "https://" + h.website, target: "_blank", rel: "noopener" }, "сайт")] : null,
    el("span", {}, " · цены, отзывы и условия — демо"));
}
const legLine = (leg) => {
  const kind = leg.mode === "train" ? "Поезд" : "Рейс";
  const via = leg.stops ? ` · пересадка ${leg.via}, ${leg.layover}` : (leg.mode === "plane" ? " · прямой" : "");
  return `${kind} ${leg.depart} → ${leg.arrive} · ${leg.duration}${via}${leg.mode === "plane" && !leg.baggage ? " · без багажа" : ""}`;
};
const timelineEl = (items) => el("ol", { class: "timeline" }, items.map((t) => el("li", { class: t.level }, el("time", {}, t.t), el("span", {}, t.label))));
const tripRoute = (t) => ({ origin: { name: t.origin, lat: t.origin_lat, lon: t.origin_lon }, targets: [{ name: t.dest, lat: t.lat, lon: t.lon }] });
const detailBlock = (title, ...children) => el("details", {class:"compact-details"}, el("summary",{},title), ...children);
const shortLeg = leg => leg.mode === "train" ? "Поезд" : leg.stops ? `Перелёт с пересадкой: ${leg.via}` : "Прямой перелёт";
function cancellation(hotel) {
  if (!hotel.free_cancel_days) return "Невозвратный тариф";
  const when=new Date(hotel.date_in+"T00:00:00Z");when.setUTCDate(when.getUTCDate()-hotel.free_cancel_days);
  return `Бесплатная отмена до ${new Intl.DateTimeFormat("ru-RU",{day:"numeric",month:"short",timeZone:"UTC"}).format(when)}`;
}
function legDetails(leg, from, to) {
  return el("div",{}, el("p",{},`${from} → ${to}`), el("p",{},`${leg.carrier} · ${leg.number} · ${leg.seat_class}`),
    el("p",{},`${leg.depart} → ${leg.arrive} · ${leg.duration}`),
    el("p",{},leg.stops ? `Пересадка: ${leg.via}, ${leg.layover}` : "Без пересадок"),
    el("p",{},leg.mode === "train" ? "Правила багажа нужно уточнить у перевозчика" : leg.baggage ? "Багаж включён" : "Без багажа"),
    el("strong",{class:"component-price"},leg.price," за всех"));
}
function hotelDetails(hotel) {
  return el("div",{},el("p",{},`${hotel.name} · ${hotel.stars}★ · ${hotel.rating}`),
    el("p",{},`${hotel.dates} · ${hotel.meal}`),
    el("p",{},`Заезд с ${hotel.check_in} · выезд до ${hotel.check_out || "уточняется"}`),
    el("p",{},cancellation(hotel)),
    el("p",{},hotel.beach_km != null ? `${hotel.beach_km} км до пляжа` : `${hotel.center_km} км до центра`),
    el("div",{class:"tags"},(hotel.amenities||[]).map(name=>el("span",{class:"tag"},name))),
    el("strong",{class:"component-price"},hotel.price," за проживание"),hotelSource(hotel));
}
function transferDetails(transfer, editable = false) {
  const parts=[el("p",{},`${transfer.price} за всех · обе стороны`)];
  for (const [key,title] of [["in","До отеля"],["out","Обратно к отправлению"]]) {
    const leg=transfer[key];if(!leg)continue;
    parts.push(el("div",{class:"transfer-leg"},el("h4",{},title),el("p",{},`${leg.from} → ${leg.to}`),
      el("p",{},`${leg.pickup} → ${leg.arrive} · ${leg.minutes}`),el("p",{},leg.note),
      el("p",{},`${leg.price} · ${leg.people}`)));
  }
  if(transfer.arrival_buffer) parts.push(el("p",{class:"detail-note"},`После прибытия заложено ${transfer.arrival_buffer} на выход. Обратно — ${transfer.departure_buffer} до отправления. Место встречи и детские кресла требуют уточнения.`));
  if(editable) {
    const select=el("select",{id:"transfer-kind","aria-label":"Тип трансфера"},
      ...[["auto","Подобрать автоматически"],["taxi","Индивидуальный / минивэн"],["shuttle","Групповой"]].map(([value,label])=>el("option",{value,selected:value===(transfer.preference||"auto")},label)));
    select.onchange=async()=>{select.disabled=true;await changeTransfer(select.value);if(select.isConnected)select.disabled=false;};
    parts.push(el("label",{for:"transfer-kind"},"Тип трансфера в обе стороны"),select,el("p",{class:"detail-note"},"Цена и время пересчитаются. Отель и билеты сохранятся."),el("p",{id:"transfer-status",role:"status"}));
  }
  return el("div",{},...parts);
}
function packageDetails(k, trip) {
  return detailBlock("Все условия поездки",el("div",{class:"package-details"},
    el('section',{},el('h4',{},'Отель'),hotelDetails(k.hotel)),
    el('section',{},el('h4',{},'Туда'),legDetails(k.out,trip.origin,trip.dest)),
    el('section',{},el('h4',{},'Обратно'),legDetails(k.back,trip.dest,trip.origin)),
    el('section',{},el('h4',{},'Трансферы'),transferDetails(k.transfer)),
    el('section',{},el('h4',{},'Поездка по часам'),timelineEl(k.timeline))));
}
function comparePackages(cards, items) {
  if (items.length < 2) return cards;
  const optionAttrs = (item) => { const key = "hotel:" + String(item.hotel.id || item.hotel.name);
    return {"data-option-key":key, hidden:preferenceData.hidden.includes(key)}; };
  const fields=[["Стоимость за всех", x=>x.total],["Отель",x=>x.hotel.name],["Питание",x=>x.hotel.meal],
    ["Отмена отеля",x=>cancellation(x.hotel)],["Туда",x=>legLine(x.out)],["Обратно",x=>legLine(x.back)],
    ["Трансфер в обе стороны",x=>`${x.transfer.price} · ${x.transfer.note} · ${x.transfer.minutes}`],
    ["Компромиссы",x=>(x.tradeoffs||[]).join("; ")||"—"]];
  const common=fields.filter(([label,get])=>["Питание","Туда","Обратно"].includes(label)&&items.every(x=>get(x)===get(items[0])));
  const table = el("div", {class:"compare-scroll", hidden:true, tabindex:"0", role:"region", "aria-label":"Сравнение вариантов"},
    common.length ? el("p",{class:"compare-common"},"Во всех вариантах: "+common.map(([label,get])=>`${label.toLowerCase()} — ${get(items[0])}`).join("; ")) : null,
    el("table", {class:"compare-table"},
      el("thead", {}, el("tr", {}, el("th", {scope:"col"}, "Параметр"),
        ...items.map((item, i) => el("th", {scope:"col", ...optionAttrs(item)}, item.title || `Вариант ${i+1}`)))),
      el("tbody", {}, ...fields.filter(field=>!common.includes(field)).map(([label, get]) =>
          el("tr", {}, el("th", {scope:"row"}, label), ...items.map((item) => el("td", optionAttrs(item), get(item))))),
        el("tr", {}, el("th", {scope:"row"}, "Выбор"), ...items.map((item, i) =>
          el("td", optionAttrs(item), sayBtn("Выбрать", `беру ${i+1} вариант`, "btn ghost")))))));
  const cardButton = el("button", {type:"button", "aria-pressed":"true"}, "Карточки");
  const tableButton = el("button", {type:"button", "aria-pressed":"false"}, "Сравнить");
  function show(compact) {
    cards.hidden=compact; table.hidden=!compact;
    cardButton.setAttribute("aria-pressed",String(!compact)); tableButton.setAttribute("aria-pressed",String(compact));
  }
  cardButton.addEventListener("click",() => show(false)); tableButton.addEventListener("click",() => show(true));
  return el("div", {}, el("div", {class:"compare-toggle", role:"group", "aria-label":"Вид вариантов"}, cardButton, tableButton), cards, table);
}

const views = {
  real_hotels(p) {
    drawMap({targets: p.items.map((h) => ({name:h.name, lat:h.lat, lon:h.lon}))});
    return [el("h2", {class:"section-title"}, "Отели из открытого каталога"),
      el("p", {class:"section-sub"}, "Адреса и названия из Overture Maps. Наличие, цены и условия не проверены."),
      el("div", {class:"cards"}, p.items.map((h, i) => el("article", {class:"card"},
        el("div", {class:"kicker"}, `Запись ${i + 1}`), el("h3", {}, h.name),
        el("p", {}, h.address || "Адрес в каталоге не указан"),
        el("div", {class:"actions"}, sayBtn("Выбрать отель", String(i + 1), "btn accent")))))];
  },
  real_hotel_selected(p) {
    const h = p.hotel;
    if (h.lat != null && h.lon != null) drawMap({targets:[{name:h.name,lat:h.lat,lon:h.lon}]});
    return [el("h2", {class:"section-title"}, "Выбранный отель"),
      el("article", {class:"card"}, el("h3", {}, h.name),
        el("p", {}, h.address || "Адрес в каталоге не указан"),
        el("p", {class:"src"}, "Запись Overture Maps. Цены, наличие и бронирование не подтверждены."),
        el("div", {class:"actions"}, sayBtn("Другие отели", "покажи реальные отели", "btn ghost")))];
  },
  place_info(p) {
    const d = p.place;
    drawMap({ targets: [{ name: d.name, lat: d.lat, lon: d.lon }] });
    return [el("h2", { class: "section-title" }, d.name), el("p", { class: "section-sub" }, d.country),
      el("article", { class: "card" }, el("h3", {}, "Место найдено"),
        el("p", {}, "В демонстрационном каталоге пока нет предложений для этого места. Данные о ценах и наличии не выдумываем."),
        sayBtn("Другие направления", "покажи ещё", "btn ghost"))];
  },
  ideas(p) {
    drawMap({ targets: p.items.map((d) => ({ name: d.name, country: d.country, lat: d.lat, lon: d.lon })) });
    return [el("h2", { class: "section-title" }, "Идеи для поездки"),
      el("p", { class: "section-sub" }, "Пока без расчёта дат и цены. Выберите направление, чтобы продолжить."),
      el("div", { class: "cards" }, p.items.map((d, i) => el("article", { class: "card" },
        gallery(d.gallery?.length ? d.gallery : savedDestinationPhotos(d.id), { alt: d.name }),
        el("div", { class: "kicker" }, `${i + 1} · ${d.country}`), el("h3", {}, d.name),
        el("div", { class: "tags" }, d.highlights.slice(0, 3).map((h) => el("span", { class: "tag" }, h))),
        el("div", { class: "actions" }, destinationBtn("Хочу сюда", d, "btn accent")))))];
  },
  tent_transport(p) {
    drawMap(tripRoute(p.trip));
    return [el("h2", { class: "section-title" }, "Дорога и своя палатка"),
      el("p", { class: "section-sub" }, "Расписание и цены демонстрационные. Отель не включён; место стоянки, питание и трансфер нужно проверить отдельно."),
      el("div", { class: "cards" }, p.items.map((item, i) => el("article", { class: "card" },
        el("div", { class: "kicker" }, `Вариант ${i + 1} · дорога туда и обратно`),
        el("div", { class: "price num" }, item.total, el("small", {}, p.trip.people)),
        el("dl", { class: "facts" }, el("dt", {}, "Туда"), el("dd", {}, legLine(item.out)),
          el("dt", {}, "Обратно"), el("dd", {}, legLine(item.back))),
        el("div", { class: "actions" }, sayBtn("Выбрать дорогу", `беру ${i + 1} вариант`, "btn accent")))))];
  },
  tent_cart(p) {
    drawMap(tripRoute(p.trip));
    return [el("h2", { class: "section-title" }, "Корзина · дорога"),
      el("p", { class: "section-sub" }, "Демонстрация. Стоянка, питание и трансфер в сумму не входят."),
      el("article", { class: "card" }, el("dl", { class: "facts" }, el("dt", {}, "Туда"), el("dd", {}, legLine(p.out)),
        el("dt", {}, "Обратно"), el("dd", {}, legLine(p.back))),
        el("div", { class: "price num" }, p.total, el("small", {}, "Только дорога · модельные цены")),
        el("div", { class: "actions" }, sayBtn("Выбрать способ оплаты", "да, оформляй", "btn accent"),
          sayBtn("К вариантам", "нет")))];
  },
  tent_order(p) {
    const o = p.order;
    return [el("h2", { class: "section-title" }, "Демонстрация завершена"),
      el("p", { class: "section-sub" }, "Денег не списано, билеты не куплены, место стоянки не забронировано."),
      el("article", { class: "card" }, el("h3", {}, `${o.origin} — ${o.dest}`),
        el("p", {}, `Условный заказ ${o.number}`), el("p", {}, `Туда: ${o.out}`), el("p", {}, `Обратно: ${o.back}`))];
  },
  destinations(p) {
    drawMap({ origin: p.origin, targets: p.items.map((d) => ({ name: d.name, country: d.country, lat: d.lat, lon: d.lon })) });
    return [el("h2", { class: "section-title" }, "Куда можно поехать"),
      el("p", { class: "section-sub" }, `Демо-цены за поездку на всех: дорога, отель, трансферы, ${p.nights_label || p.nights + " ночей"}. Наличие не проверялось.`),
      el("div", { class: "cards" }, p.items.map((d, i) => el("article", { class: "card" + (i === 0 ? " best" : "") },
        gallery(d.gallery || [d.image], { alt: d.name }),
        el("div", { class: "kicker" }, el("span", {}, `${i + 1} · ${d.country}`), i === 0 && p.accessibility_status !== "unverified" && !p.requirements_unverified ? el("b", {}, "Лучше всего подходит") : null),
        el("h3", {}, d.name),
        el("div", { class: "price num" }, `от ${d.total}`, el("small", {}, "за всю поездку на всех")),
        d.visa ? el("details", {class:"compact-details visa-details"}, el("summary", {}, "Условия въезда · требуют проверки"), el("p", {}, `Демо-справка: ${d.visa}. Актуальные требования зависят от гражданства и не проверены.`)) : null,
        el("dl", { class: "facts" }, el("dt", {}, "Климат в среднем"), el("dd", {}, d.weather || "—"),
          el("dt", {}, "Дорога"), el("dd", {}, `${d.mode === "train" ? "поезд" : d.stops ? "с пересадкой" : "прямой рейс"}, ${d.travel}`)),
        marks("why", d.reasons.filter((r) => !/^(перелёт|поезд)/.test(r))),
        d.risks.filter((r) => !r.startsWith("виза")).length ? marks("", d.risks.filter((r) => !r.startsWith("виза")).map((t) => ({ level: "warn", text: t }))) : null,
        el("div", { class: "tags" }, d.highlights.map((h) => el("span", { class: "tag" }, h))),
        el("div", { class: "actions" }, destinationBtn(`Выбрать ${d.name}`, d, i === 0 ? "btn accent" : "btn ghost")))))];
  },
  packages(p) {
    drawMap(tripRoute(p.trip));
    const out = [];
    if(p.notice && !lastData?.reply?.includes(p.notice))out.push(el("p",{class:"notice"},p.notice));
    if(p.diff?.length)out.push(el("p",{class:"notice"},"Пересобрал план: "+p.diff.join("; ")+"."));
    if(p.relaxed?.length)out.push(el("p",{class:"notice"},"Чтобы что-то нашлось, я "+p.relaxed.join(", ")+"."));
    const packageCards=el("div",{class:"cards"},p.items.map((k,i)=>el("article",{class:"card package-card"+(i===0?" best":"")},
      photo(k.hotel.image,{alt:k.hotel.name,badge:"Демо · фото-иллюстрация"}),
      el("div",{class:"kicker"},el("span",{},`Вариант ${i+1}`),i===0&&p.accessibility_status!=="unverified"&&!p.requirements_unverified?el("b",{},"Рекомендую"):null),
      el("h3",{},k.hotel.name),el("div",{class:"price num"},k.total,el("small",{},`${p.trip.people} · вся поездка`)),
      el("p",{class:"package-hotel"},`${k.hotel.stars}★ · ${k.hotel.area}`),
      el("p",{class:"detail-note"},`${k.hotel.meal} · ${k.hotel.amenities.slice(0,2).join(" · ")}`),
      el("div",{class:"package-route-preview"},el("p",{},"Туда · "+legLine(k.out)),el("p",{},"Обратно · "+legLine(k.back)),el("p",{},"Трансферы в обе стороны · "+k.transfer.note)),
      el("p",{class:"cancellation-summary"},cancellation(k.hotel)),
      marks("why",k.why.filter(t=>!t.includes(k.hotel.name)&&!/(?:завтрак|полупансион|всё включено|бесплатная отмена|перелёт без пересадок)/i.test(t)).slice(0,2)),
      k.tradeoffs.length?marks("trade",k.tradeoffs.slice(0,1)):null,
      k.checks.some(c=>c.level==="risk")?marks("",k.checks.filter(c=>c.level==="risk")):null,
      el("div",{class:"actions"},sayBtn("В корзину",`беру ${i+1} вариант`,i===0?"btn accent":"btn ghost")),
      packageDetails(k,p.trip))));
    out.push(el("h2",{class:"section-title"},p.items.length>1?`${p.items.length} варианта вашей поездки`:"Ваша поездка"),
      el("p",{class:"section-sub"},"Дорога, отель и трансферы включены · демо-расчёт"),
      comparePackages(packageCards,p.items));
    out.unshift(el("div",{class:"results-toolbar"},datesButton(),el("span",{class:"demo-label"},"Демо-цены и условия")));
    return out;
  },
  hotels(p) {
    return [el("h2", { class: "section-title" }, "Другие отели"),
      el("p", { class: "section-sub" }, "Выберите — пересоберу поездку с ним, дорогу оставлю. Отзывы, оценки и цены — демо."),
      el("div", { class: "cards" }, p.items.map((h, i) => el("article", { class: "card" },
        photo(h.image, { alt: h.name, badge: "иллюстрация" }),
        el("div", { class: "kicker" }, el("span", {}, `${h.stars}★ · ${h.area} · демо`), el("span", {}, `${h.rating} · ${h.reviews} отзывов · демо`)),
        el("h3", {}, h.name), hotelSource(h),
        el("div", { class: "price num" }, h.price, el("small", {}, `${h.per_night} за ночь · ${h.meal}`)),
        el("div", { class: "tags" }, h.amenities.map((a) => el("span", { class: "tag" }, a))),
        el("div", {}, el("h4", {}, "Примеры отзывов · не реальные"), marks("why", h.praise), marks("trade", h.complaints)),
        el("div", { class: "actions" }, sayBtn("Взять этот отель", `${i + 1}`)))))];
  },
  cart(p) {
    drawMap(tripRoute(p.trip));
    const k=p.package;
    const rows=[
      ["Туда",`${k.out.carrier} ${k.out.number}`,k.out.price],
      ["Проживание",`${k.hotel.name} · ${k.hotel.dates}`,k.hotel.price],
      ["Трансферы",`${k.transfer.note} · обе стороны`,k.transfer.price],
      ["Обратно",`${k.back.carrier} ${k.back.number}`,k.back.price]
    ];
    const component=(title,content,action)=>el("section",{class:"trip-component"},el("h3",{},title),content,action||null);
    return [p.diff?.length?el("p",{class:"notice"},"Обновил поездку: "+p.diff.join("; ")+"."):null,
      el("h2",{class:"section-title"},"План и корзина"),
      el("p",{class:"section-sub"},"Все части поездки собраны вместе. Можно изменить каждую."),
      el("div",{class:"component-layout"},
        el("article",{class:"card basket-total"},
          el("table",{class:"receipt"},el("tbody",{},rows.map(([a,b,c])=>el("tr",{},el("td",{},el("div",{},a),el("small",{},b)),el("td",{},c))),
            el("tr",{class:"total"},el("td",{},"Итого"),el("td",{},p.total)))),
          el("p",{class:"detail-note"},"Демо-расчёт за всех. Реальная бронь и списание не выполняются."),
          el("div",{class:"actions"},sayBtn("Перейти к оплате","да, оформляй","btn accent"),sayBtn("← Назад к выбору","нет, вернуться к вариантам","text-button"))),
        el("div",{class:"trip-components"},
          component("Туда",legDetails(k.out,p.trip.origin,p.trip.dest),el("button",{type:"button",class:"text-button",onclick:()=>experience.openCondition("transport")},"Изменить дорогу")),
          component("Проживание",hotelDetails(k.hotel),sayBtn("Другие отели","покажи другие отели","text-button")),
          component("Трансферы",transferDetails(k.transfer,true)),
          component("Обратно",legDetails(k.back,p.trip.dest,p.trip.origin)),
          detailBlock("Поездка по часам и состыковки",timelineEl(k.timeline),marks("",k.checks))))];
  },
  payment(p) {
    drawMap(tripRoute(p.trip));
    return [el("h2", { class: "section-title" }, "Способ оплаты"),
      el("p", { class: "section-sub" }, "Демонстрационный сценарий: денег не спишем, реальную бронь не создадим."),
      el("article", { class: "card" }, el("h3", {}, `Итого ${p.total}`),
        el("p", {}, p.method_name ? `Выбрано: ${p.method_name}` : "Выберите способ оплаты. Вводить данные карты не нужно."),
        el("div", { class: "actions" }, sayBtn("Демо-карта", "оплата картой", p.method === "card" ? "btn accent" : "btn ghost"),
          sayBtn("Демо-СБП", "оплата СБП", p.method === "sbp" ? "btn accent" : "btn ghost")),
        p.method ? el("div", { class: "actions" }, sayBtn("Подтвердить демонстрацию", "да, подтверждаю", "btn accent"),
          sayBtn("Вернуться в корзину", "нет")) : sayBtn("Вернуться в корзину", "нет"))];
  },
  order(p) {
    const o = p.order;
    const cancel = o.cancel_until ? `бесплатно до ${o.cancel_until.split("-").reverse().join(".")}` : "невозвратный тариф";
    return [el("h2", { class: "section-title" }, "Демонстрация завершена"),
      el("p", { class: "section-sub" }, "Денег не списано, реальная бронь не создана. Билеты и ваучер не отправляются."),
      el("article", { class: "pass" },
        el("div", { class: "main" },
          photo(o.image, { alt: o.dest }),
          el("div", { class: "route" }, el("h3", {class:"route-title"}, o.origin, " → ", o.dest)),
          el("dl", { class: "facts" }, el("dt", {}, "Туда"), el("dd", {}, o.out), el("dt", {}, "Обратно"), el("dd", {}, o.back),
            el("dt", {}, "Отель"), el("dd", {}, `${o.hotel} · ${o.hotel_dates || ""}`), el("dt", {}, "Отмена"), el("dd", {}, cancel)),
          p.requests && p.requests.length ? el("div", {}, el("h4", {}, "Запросы в отель"), marks("why", p.requests)) : null,
          el("div", { class: "actions" }, sayBtn("Ранний заезд", "запроси ранний заезд"), sayBtn("Поздний выезд", "поздний выезд"),
            el("button", {type:"button",class:"btn ghost",onclick:()=>experience.openCondition("dates")},"Изменить даты"), sayBtn("Отменить", "отмени бронь"))),
        el("div", { class: "stub" },
          el("div", { class: "label" }, "Номер заказа"), el("div", { class: "big num" }, o.number),
          el("div", { class: "label" }, "Демо-сумма"), el("div", { class: "big num" }, new Intl.NumberFormat("ru-RU").format(o.total) + " ₽"),
          el("div", { class: "label" }, "Путешественники"), el("div", {}, o.people || "")))];
  },
};

function addMessage(role, content, meta) {
  const m = el("div", { class: `msg ${role}` }, content, meta ? el("span", { class: "meta" }, meta) : null);
  m.dataset.text=typeof content === "string" ? content : content.textContent;
  m.dataset.role=role;
  $("log").append(m); preferences.apply();
  requestAnimationFrame(()=>{const scroll=$("conversation-scroll");scroll.scrollTop=scroll.scrollHeight;}); return m;
}
function renderStages(stage) {
  const list = info ? info.stages : [];
  const idx = list.findIndex((s) => s.key === stage);
  $("stages").replaceChildren(...list.map((s, i) => el("li", { class: i < idx ? "done" : i === idx ? "now" : null }, {start:"Запрос",destination:"Куда",plan:"Выбор",cart:"План",payment:"Оплата",booked:"Готово"}[s.key] || s.title)));
}
function dateControls(single=false){return el('button',{type:'button',class:'btn ghost date-range-open',onclick:()=>openDates(single)},single?'Выбрать дату':'Выбрать даты');}
function renderSuggest(data) {
  const stage = typeof data === "string" ? data : data.stage;
  if (!conversationStarted) {
    const starters = [
      ["К морю на неделю", "Хочу к морю на неделю: отдохнуть и жить рядом с пляжем. Предложи направления.", "sea"],
      ["В горы за тишиной", "Хочу в горы, красивый вид и спокойные прогулки. Предложи направления.", "alpine"],
      ["Предложи сам", "Предложи сам несколько разных идей для отдыха, пока без дат.", null]
    ];
    $("suggest").replaceChildren(...starters.map(([label,text,mood]) => el("button", {type:"button",onclick:()=>{
      if(text){experience.setMood(mood);send(text);}else{experience.showIdeas();}
    }},label)));
    return;
  }
  const payload = typeof data === "object" ? data.payload || {} : {};
  // Explicit server choices take precedence over stage-based convenience controls.
  if (Array.isArray(data.suggestions) && data.suggestions.includes("новая поездка")) {
    $("suggest").replaceChildren(...data.suggestions.map((text) => el("button", {type:"button", onclick:() => send(text)}, text)));
    return;
  }
  const question = typeof data === "object" ? String(data.reply || "").split("?")[0].toLowerCase() : "";
  if (payload.kind === "question" && (["when", "dates", "date_from", "date_to", "transfer_date", "flight_date"].includes(payload.field) ||
      (!payload.field && String(data.reply || "").includes("?") && /когда|дат[ыу]|месяц|время года/.test(question)))) {
    const choices = Array.isArray(data.suggestions) && data.suggestions.length ? data.suggestions : ["пока не знаю"];
    const preferred = choices.includes("предложи сам") ? ["предложи сам"] : choices;
    const buttons = preferred.filter((text) => typeof text === "string" && text.trim()).map((text) =>
      el("button", {type:"button", onclick:() => send(text)}, text[0].toUpperCase() + text.slice(1)));
    $("suggest").replaceChildren(dateControls(["transfer_date", "flight_date"].includes(payload.field)), ...buttons);
    return;
  }
  if (payload.kind === "question" && (payload.field === "origin" ||
      (!payload.field && String(data.reply || "").includes("?") && /откуда|город отправления|город вылета/.test(question)))) {
    $("suggest").replaceChildren(el("button", {type:"button", onclick:()=>experience.openCondition("origin")}, "Указать город")); return;
  }
  if (payload.kind === "question" && payload.field === "duration") {
    const nights = /ноч/i.test(String(data.reply || ""));
    const choices = nights ? [["3 ночи", "на 3 ночи"], ["7 ночей", "на 7 ночей"]] : [["3 дня", "на 3 дня"], ["7 дней", "на 7 дней"]];
    $("suggest").replaceChildren(...[...choices, ["Предложи сам", "предложи сам"]]
      .map(([label, text]) => el("button", {type:"button", onclick:() => send(text)}, label)));
    return;
  }
  if (payload.kind === "question" && payload.field === "people") {
    $("suggest").replaceChildren(...[["1 взрослый", "1 взрослый"], ["2 взрослых", "2 взрослых"], ["Предложи сам", "предложи сам"]]
      .map(([label, text]) => el("button", {type:"button", onclick:() => send(text)}, label)));
    return;
  }
  if (payload.kind === "question" && payload.field === "passengers") {
    $("suggest").replaceChildren(...["1 человек", "2 человека"].map((text) =>
      el("button", {type:"button", onclick:() => send(text)}, text)));
    return;
  }
  const supplied = typeof data === "object" && Array.isArray(data.suggestions) ?
    data.suggestions.filter((text) => typeof text === "string" && !(info?.examples || []).includes(text)) : [];
  const understood = typeof data === "object" ? data.understood || [] : [];
  const options = (typeof data === "object" && Array.isArray(data.suggestions) ? supplied : (inspiration.quick?.[stage] || [])).filter((text) =>
    !(understood.includes("по России") && /только по России/i.test(text)) &&
    !(understood.includes("за границу") && /за границу/i.test(text)));
  const useful = options.filter(text => !/два дня|2 дня|бюджет меньше|с нами собака|к морю|в горы/i.test(text));
  const isQuestion = payload.kind === "question";
  $("suggest").replaceChildren(...(isQuestion ? useful.slice(0, 3) : []).map((text) => el("button", {type:"button", onclick:() => send(text)}, /не знаю/i.test(text) ? "Предложи сам" : text)));
}
function render(data) {
  sessionId = data.session_id; lastData = data;
  renderStages(data.stage); renderHead(data); renderConditions(data); renderSuggest(data);
  tripMap.setTripContext?.(data.trip_summary);
  document.querySelector(".board").classList.toggle("compact", ["plan", "cart", "booked"].includes(data.stage));
  const p = data.payload || {};
  $("map").hidden = p.kind === "order";
  const notices = [p.kind !== "packages" ? p.notice : null, p.travel_notice, p.pet_notice]
    .filter(text=>text && !data.reply?.includes(text)).map(text => el("p", {class:"notice"}, text));
  if (views[p.kind]) $("view").replaceChildren(...[...notices, ...views[p.kind](p)].filter(Boolean));
  else if (["greeting", "flight_results", "service_results"].includes(p.kind)) { $("view").replaceChildren(); drawMap({}); }
  else if (p.kind === "question") {
    $("view").replaceChildren(...notices);
    if (data.stage !== "destination") drawMap({});
  }
  decorateOptions(p);
  preferences.apply(); experience.update(data);
  journeyUI.update(data);
}
async function post(path, body) {
  if(path==='/api/chat' && !body.event_id && !body.destination_id && !/^(?:беру|оплат|да[, ]|нет[, ]|[1-9]$)/i.test(body.text||'')) body.preferences=selectionPreferences();
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const detail=await r.json().catch(()=>({}));
    const error=new Error(typeof detail.detail === "string" ? detail.detail : "Не удалось отправить. Текст сохранён — попробуйте ещё раз.");
    error.status=r.status;throw error;
  }
  return r.json();
}
function showMoodChoices() {
  const choices=[["Море","sea","Хочу к морю"],["Снежные горы","alpine","Хочу в горы кататься на лыжах"],
    ["Город","city","Хочу в интересный город"],["Лес и тишина","forest","Хочу на природу в лес"],["Закаты вдвоём","sunset","Хочу романтическую поездку к морю"]];
  $("suggest").replaceChildren(el("div",{class:"mood-choices"},choices.map(([label,mood,text])=>el("button",{type:"button",onclick:()=>{
    experience.setMood(mood); send(text+", пока не знаю куда. Предложи идеи без дат.");
  }},label))),el("button",{type:"button",class:"example-link",onclick:()=>experience.openExamples()},"Или взять готовый пример ↗"));
}
function setBusy(value) {
  busy=value; $("send").disabled=value;
  $("mic-button").disabled=value;
  $("reset").disabled=value; $("conditions-edit").disabled=value;
  tripSentence.setBusy(value);
  $("trip-context").querySelectorAll("button").forEach(button=>{button.disabled=value;});
}
function editTurn(turn) {
  if(busy) return;
  editing=Boolean(turn && lastData?.can_undo);
  $("edit-banner").hidden=!editing;
  experience.fill(editing ? turn.text : "");
}
function attachEdit(turn,data) {
  $("log").querySelectorAll(".latest-user").forEach((n)=>n.classList.remove("latest-user"));
  if(!data.can_undo) return;
  turn.user.classList.add("latest-user");
  turn.user.append(el("button",{type:"button",class:"message-edit text-button",onclick:()=>editTurn(turn)},"Изменить"));
}
// Best-effort draft protection complements server-side detection; it is not a
// complete detector of every personal or health detail.
function sensitiveDraft(text) {
  return /инвалид|коляск|костыл|ходунк|маломобиль|ограниченн[а-яё]*\s+(?:возможност|подвижност)|незряч|слабовид|слабослыш|беременн|аллерги|непереносим|веган|вегетариан|халяль|кошер|диагноз|болезн|лекарств|(?:я\s+вешу|мой\s+вес)|паспорт|снилс|телефон|парол|(?:^|[^а-яёa-z0-9_])(?:без|не\s+ем|исключить)\s+(?:орех|арахис|глютен|лактоз|кунжут|кешью|клубник|молок|рыб|мяс|яиц|со[ия]|пшениц|морепродукт)|(?:реб[её]н[а-яё]*|дет(?:ям|ей|и|ьми)|малыш[а-яё]*|сыну|дочери|дочке)[^.!?\n]{0,30}\d{1,3}|\bcvv\b|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\+7|8)[\s().-]*(?:\d[\s().-]*){10}/i.test(text);
}
const privateRecoveryText = "[Сообщение со сведениями, которые не сохранены в браузере]";
function saveTrip() {
  if(!sessionId || !lastData)return;
  const messages=[...$("log").querySelectorAll(".msg")].filter(node=>!node.querySelector(".typing"))
    .map(node=>({role:node.dataset.role,text:node.dataset.sensitive === "true" ? privateRecoveryText : (node.dataset.text||""),
      kind:node.dataset.kind||"",sensitive:node.dataset.sensitive === "true"}));
  const draft = $("text").value;
  const ageAnswer = lastData.payload?.field === "children" && /(?:лет|год(?:а)?|месяц[а-яё]*|мес)(?:$|[^а-яё])/i.test(draft);
  const saved=tripStorage.write({session_id:sessionId,revision:lastData.revision,messages,
    draft:sensitiveDraft(draft) || ageAnswer || ["children_ages","children_age_unit","room_allocation"].includes(lastData.payload?.field) ? "" : draft,editing,panel:journeyUI.panel()});
  $("save-status").hidden=saved;
  $("save-status").textContent=saved ? "" : "Не удалось сохранить поездку в браузере";
}
async function restoreTrip() {
  const saved=tripStorage.read();if(!saved)return false;
  let data;
  try {data=await post("/api/session",{session_id:saved.session_id});}
  catch(error){
    if(error.status===404){tripStorage.clear();addMessage("bot","Прошлая сессия завершилась. Начнём новую поездку.");return false;}
    throw error;
  }
  const records=Array.isArray(saved.messages)?saved.messages.slice(-60):[];
  $("log").replaceChildren();let user=null,bot=null;
  for(const record of records){
    if(!["user","bot"].includes(record.role)||typeof record.text!=="string")continue;
    let content=record.text.slice(0,20000);
    if(record.role==="bot"){content=el("div");renderTravelReply(content,record.text.slice(0,20000),record.kind||"");}
    const node=addMessage(record.role,content);node.dataset.text=record.text.slice(0,20000);node.dataset.kind=record.kind||"";
    node.dataset.sensitive=record.sensitive ? "true" : "false";
    if(record.role==="user"){user=node;bot=null;}else if(user)bot=node;
  }
  conversationStarted=Boolean(user)||Boolean(data.understood?.length);
  render(data);
  if(saved.revision===data.revision && user && bot){
    if(bot.dataset.sensitive === "true"){
      const reply=el("div");renderTravelReply(reply,data.reply,data.payload?.kind);bot.replaceChildren(reply);bot.dataset.text=data.reply;
    }
    if(user.dataset.sensitive !== "true"){latestTurn={text:user.dataset.text,user,bot};attachEdit(latestTurn,data);}else latestTurn=null;
    journeyUI.addResultLink(bot);
  }else{
    const reply=el("div");renderTravelReply(reply,data.reply,data.payload?.kind);
    const latest=addMessage("bot",reply);latest.dataset.text=data.reply;latest.dataset.kind=data.payload?.kind||"";
    latest.dataset.sensitive=data.input_sensitive || data.payload?.accessibility_status === "unverified" || data.payload?.requirements_unverified ? "true" : "false";
    journeyUI.addResultLink(latest);latestTurn=null;
  }
  $("text").value=typeof saved.draft==="string"?saved.draft.slice(0,4000):"";
  $("text").dispatchEvent(new Event("input",{bubbles:true}));
  editing=Boolean(saved.editing && latestTurn && data.can_undo);$("edit-banner").hidden=!editing;
  journeyUI.show(["chat","results","map"].includes(saved.panel)?saved.panel:"chat",false);
  saveTrip();return true;
}
async function changeTransfer(kind) {
  if(busy||!sessionId||!lastData)return;
  setBusy(true);
  const label={auto:"Подобрать трансфер автоматически",taxi:"Индивидуальный трансфер",shuttle:"Групповой трансфер"}[kind];
  try{
    const data=await post("/api/trip/transfer",{session_id:sessionId,revision:lastData.revision,kind});
    const user=addMessage("user",label),reply=el("div");renderTravelReply(reply,data.reply,data.payload?.kind);
    const bot=addMessage("bot",reply);bot.dataset.text=data.reply;bot.dataset.kind=data.payload?.kind||"";
    bot.dataset.sensitive=data.payload?.accessibility_status === "unverified" || data.payload?.requirements_unverified ? "true" : "false";
    latestTurn={text:label,user,bot};editing=false;$("edit-banner").hidden=true;
    render(data);journeyUI.addResultLink(bot);journeyUI.show("results",false);saveTrip();
    $("say").textContent="Трансферы, время и общая сумма обновлены.";
  }catch(error){
    $("say").textContent=error.message;
    if($("transfer-status"))$("transfer-status").textContent=error.message;
    if($("transfer-kind"))$("transfer-kind").value=lastData.payload.package.transfer.preference||"auto";
  }finally{setBusy(false);}
}
$("text").addEventListener("input",()=>saveTrip());
window.addEventListener("pagehide",()=>saveTrip());
async function send(text, selection = {}) {
  if(busy || !text.trim()) return;
  if(voice.isActive()) voice.cancel();
  const replacing=editing && !Object.keys(selection).length ? latestTurn : null;
  const previousStarted=conversationStarted;
  if(!conversationStarted) $("view").replaceChildren();
  conversationStarted=true; $("suggest").replaceChildren(); setBusy(true);
  const user=replacing ? replacing.user : addMessage("user",text);
  const typing=addMessage("bot",el("span",{class:"typing",role:"status","aria-label":"Подбираю варианты"},el("i"),el("i"),el("i")));
  try {
    const detected = sessionId ? null : await Promise.race([approximateCity, new Promise((resolve) => setTimeout(() => resolve(null), 2000))]);
    const data=await post(replacing ? "/api/chat/edit" : "/api/chat",{text,session_id:sessionId,revision:lastData?.revision,...selection,detected_city:detected});
    typing.remove();
    if(replacing){replacing.bot.remove();user.replaceChildren(text);user.dataset.text=text;}
    user.dataset.sensitive=data.input_sensitive ? "true" : "false";
    const reply=el("div"); renderTravelReply(reply,data.reply,(data.payload||{}).kind);
    const bot=addMessage("bot",reply);
    bot.dataset.text=data.reply;bot.dataset.kind=data.payload?.kind || "";
    bot.dataset.sensitive=data.input_sensitive || data.payload?.accessibility_status === "unverified" || data.payload?.requirements_unverified ? "true" : "false";
    latestTurn={text,user,bot}; editing=false; $("edit-banner").hidden=true;
    render(data); attachEdit(latestTurn,data); $("say").textContent="";
    journeyUI.addResultLink(bot);
    experience.showChat();
    saveTrip();
    return true;
  } catch(error) {
    typing.remove(); if(!replacing)user.remove();
    conversationStarted=previousStarted;
    if(!$("text").value)experience.fill(text);
    addMessage("bot",error.message || "Не удалось отправить. Текст сохранён — попробуйте ещё раз.");
    renderSuggest(lastData || "start"); return false;
  } finally {setBusy(false);voice.update();$("text").focus({preventScroll:true});}
}
function sendTripChange(text, selection = {}) {
  if(busy) return;
  // Editing a summary field is a new refinement, even while an older message
  // is being rewritten in the composer.
  editing=false; $("edit-banner").hidden=true;
  return send(text,selection);
}
async function undoTurn() {
  if(busy || !lastData?.can_undo || !latestTurn) return;
  setBusy(true);
  try {
    const data=await post("/api/chat/undo",{session_id:sessionId,revision:lastData.revision});
    const text=latestTurn.text;latestTurn.user.remove();latestTurn.bot.remove();latestTurn=null;editing=false;
    $("edit-banner").hidden=true;
    conversationStarted=Boolean($("log").querySelector(".user"));
    render(data);experience.fill(text);voice.clearStatus();
    saveTrip();
    $("voice-status").hidden=false;$("voice-status").textContent="Последняя реплика отменена. Можно исправить и отправить снова.";
  } catch(error){addMessage("bot",error.message);} finally {setBusy(false);}
}
function greet(){addMessage("bot","Расскажите, какой отдых хочется. Подберём отель, дорогу и трансферы — можно начать с пары слов.");}
function start(){conversationStarted=false;lastDestination=null;lastData=null;latestTurn=null;editing=false;
  document.querySelector('.board').classList.remove('compact');
  $("map").hidden=false;renderStages("start");renderHead(null);renderConditions(null);renderSaved();renderSuggest("start");
  $("view").replaceChildren();drawMap({});tripMap.reset();experience.reset();journeyUI.update(null);journeyUI.show("chat",false);greet();}
$("ask").addEventListener("submit",(event)=>{
  event.preventDefault();if(busy)return;
  if(voice.isActive()){voice.toggle();return;}
  const text=$("text").value.trim();
  if(!text){$("voice-status").hidden=false;$("voice-status").textContent="Напишите сообщение или нажмите микрофон.";$("text").focus();return;}
  experience.fill("");voice.clearStatus();send(text);
});
async function resetConversation(){
  if(busy)return;voice.cancel();setBusy(true);
  try {if(sessionId)await post("/api/reset",{session_id:sessionId});
    tripStorage.clear();sessionId=null;$("save-status").hidden=true;$("log").replaceChildren();$("view").replaceChildren();$("say").textContent="";start();
  }catch(error){addMessage("bot","Не удалось начать новую поездку. Попробуйте ещё раз.");}finally{setBusy(false);}
}
async function initialise() {
  setBusy(true);
  let ready = false;
  const load = async (url) => {
    const response = await fetch(url, {cache: "no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };
  try {
    const [i, l, credits, prompts] = await Promise.all([
      load("/api/info"), load("/static/land.geojson"),
      load("/static/img/credits.json").catch(() => ({})),
      load("/static/inspiration.json").catch(() => null),
    ]);
    $("startup-error")?.remove();
    info = i; imageCredits = credits; inspiration = prompts || inspiration;
    tripMap.setData(i, l); experience.configureExamples(i); $("log").replaceChildren();start();
    if (!(await restoreTrip())) journeyUI.firstVisit();
    ready = true;
  } catch (_) {
    tripMap.unavailable();
    $("startup-error")?.remove();
    const retry = el("button", {type:"button", class:"startup-retry", onclick: () => {
      retry.disabled = true;
      initialise();
    }}, "Повторить");
    const message = addMessage("bot", el("div", {role:"status"},
      el("span", {}, "Не удалось подключиться. Проверьте, что приложение запущено."), retry));
    message.id = "startup-error";
  } finally {setBusy(!ready);}
}
initialise();

$("saved-open").onclick=()=>{renderSaved();renderHidden();$("saved-dialog").showModal();};
$("saved-open").replaceChildren(odinIcon('heart'));
$("help-open").onclick=()=>journeyUI.openTour();
window.addEventListener('message',event=>{if(event.source===parent&&event.data?.type==='odin-widget-hidden')voice.cancel();});
