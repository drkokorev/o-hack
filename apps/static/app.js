const $ = (id) => document.getElementById(id);
let sessionId = null, busy = false, info = null, conversationStarted = false, imageCredits = {};
let inspiration = {starters:[], places:[], quick:{}};
let lastDestination = null;
// IPinfo receives the visitor's IP; only a city hint is sent to our server.
const approximateCity = fetch("https://ipinfo.io/json", {cache:"no-store", credentials:"omit", referrerPolicy:"no-referrer"})
  .then((response) => response.ok ? response.json() : null)
  .then((data) => typeof data?.city === "string" && data.city.length <= 100 ? data.city : null)
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

const tripMap = createTripMap({ container: $("map"), onChoose: (place) => {
  if (place.kind === "hotel") return send(`Хочу остановиться в «${place.name}»`, {map_point_id:place.id});
  if (place.kind === "country") return send(`Хочу поехать: ${place.name}`, {map_country_code:place.code});
  if (place.kind === "city") return send(`Хочу поехать: ${place.name}${place.country_name ? `, ${place.country_name}` : ""}`,
    {map_city_id:place.id});
  if (place.event) return send(`Хочу поехать на ${place.event} в ${place.name}`);
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
const voice = createVoiceInput({input:$("text"), button:$("mic"), status:$("voice-status"), dedicated:true});
let lastData = null, latestTurn = null, editing = false;
const experience = createExperience({send, reset:resetConversation, undo:undoTurn, edit:editTurn,
  isBusy:()=>busy, voice, ideas:renderWelcome});

function renderHead(data) {
  const p = (data && data.payload) || {};
  const trip = p.trip || (p.order && { origin_code: p.order.origin_code, dest_code: p.order.dest_code, origin: p.order.origin, dest: p.order.dest });
  if (p.kind === "order") { $("head").replaceChildren(); return; }
  if (trip && trip.dest_code) {
    $("head").replaceChildren(el("div", { class: "route" },
      el("div", { class: "codes" }, trip.origin_code, el("i", {}, "→"), trip.dest_code),
      el("div", { class: "names" }, [trip.origin + " — " + trip.dest, trip.dates, trip.people].filter(Boolean).join(" · "))));
  } else if (data && (data.understood || []).length) {
    const title = data.stage === "destination" ? "Подбираю направление" : "Уточняю поездку";
    $("head").replaceChildren(el("div", { class: "hero" }, el("h1", {}, title)));
  } else {
    $("head").replaceChildren(el("div", { class: "hero" },
      el("h1", {}, "Куда хочется?"),
      el("p", {}, "Выберите место на глобусе. Или просто расскажите, чего хочется.")));
  }
}

function renderConditions(data) {
  const understood = data?.understood || [], assumed = data?.assumptions || [];
  $("trip-context").hidden = !understood.length && !assumed.length;
  // The optional structured field is authoritative. Older services only expose
  // a list, so recognise a destination there only when it matches their catalog.
  const knownPlaces = new Map((info?.places || []).map((p) => [p.name.toLocaleLowerCase("ru"), p.name]));
  const destination = data?.trip_summary?.destination || understood.map((value) =>
    knownPlaces.get(String(value).trim().toLocaleLowerCase("ru"))).find(Boolean) || null;
  const changed = destination && lastDestination && destination !== lastDestination;
  $("condition-change").hidden = !changed;
  $("condition-change").textContent = changed ? `${lastDestination} → ${destination}` : "";
  lastDestination = destination;
  $("conditions").replaceChildren(...understood.map((c) => el("span", { class: "chip" }, c)),
    ...assumed.map((a) => el("span", { class: "chip assumed", title: "Предположение — можно уточнить в чате" }, a)));

}

function renderSaved() {
  const entries = Object.entries(preferenceData.saved);
  $("saved-places").hidden = !entries.length;
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
      if (button) { button.setAttribute("aria-pressed", "false"); button.textContent = "♡"; }
    } }, "×"));
  }).filter(Boolean));
}
function decorateOptions(payload) {
  if (!["ideas", "destinations", "hotels", "packages"].includes(payload.kind)) return;
  const cards = [...$("view").querySelectorAll(".cards > .card")];
  const section = $("view").querySelector(".cards");
  if (!section) return;
  const restore = el("p", { class: "src" }, "Некоторые варианты скрыты. ",
    el("button", { type: "button", class: "restore-hidden", onclick: () => {
      preferenceData.hidden = []; persistPlaces(); cards.forEach((card) => { card.hidden = false; });
      $("view").querySelectorAll("[data-option-key]").forEach((cell) => {cell.hidden=false;}); restore.remove();
    } }, "Показать скрытые"));
  let hasHidden = false;
  (payload.items || []).forEach((entry, index) => {
    const isHotel = ["hotels", "packages"].includes(payload.kind);
    const place = payload.kind === "packages" ? entry.hotel : entry;
    const card = cards[index]; if (!card || !place || !place.name) return;
    const key = (isHotel ? "hotel:" : "") + String(place.id || place.name);
    card.hidden = preferenceData.hidden.includes(key); hasHidden ||= card.hidden;
    const actions = card.querySelector(".actions"); if (!actions) return;
    const saved = el("button", { type: "button", class: "feedback-button", "data-save-key": key,
      "aria-label": `В избранное: ${place.name}`, "aria-pressed": String(Boolean(preferenceData.saved[key])),
      title: "Сохранить на этом устройстве", onclick: () => {
        if (preferenceData.saved[key]) delete preferenceData.saved[key];
        else preferenceData.saved[key] = {name:place.name, kind:isHotel ? "hotel" : "city", url:isHotel ? place.map_url || null : null};
        saved.setAttribute("aria-pressed", String(Boolean(preferenceData.saved[key])));
        saved.textContent = preferenceData.saved[key] ? "♥" : "♡"; persistPlaces(); renderSaved();
      } }, preferenceData.saved[key] ? "♥" : "♡");
    const hide = el("button", { type: "button", class: "feedback-button", "aria-label": `Скрыть: ${place.name}`,
      title: "Не показывать на этом устройстве", onclick: () => {
        if (!preferenceData.hidden.includes(key)) preferenceData.hidden.push(key);
        persistPlaces(); card.hidden = true;
        $("view").querySelectorAll(`[data-option-key="${CSS.escape(key)}"]`).forEach((cell) => {cell.hidden=true;});
        if (!restore.isConnected) section.before(restore);
      } });
    hide.innerHTML = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 10v9H4v-9h3Zm2 0 3-6c.4-.7 1-1 1.6-.7l.3.1c.7.3.9 1 .7 1.7L14 8h4.2c1.2 0 2 1.1 1.7 2.2l-1.4 5c-.2.8-.9 1.3-1.7 1.3H11a2 2 0 0 1-2-2V10Z" transform="rotate(180 12 12)" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';
    actions.append(saved, hide);
  });
  if (hasHidden) section.before(restore);
}

function savedDestinationPhotos(id) {
  if (!id) return [];
  const keys = [`dest/${id}.jpg`, ...Object.keys(imageCredits).filter((key) => key.startsWith(`gallery/${id}-`)).sort()];
  return keys.filter((key) => imageCredits[key]).map((key) => ({src:`/static/img/${key}`,
    credit:`${imageCredits[key].author}, ${imageCredits[key].license}`, page:imageCredits[key].page}));
}
function renderWelcome() {
  const cards = (inspiration.places || []).map(({id, label, sound}) => {
    const place = (info?.places || []).find((item) => item.id === id);
    const picture = savedDestinationPhotos(id)[0];
    if (!place || !picture) return null;
    return el("article", {class:"inspire-card"}, photo(picture, {alt:place.name}),
      el("button", {type:"button", class:"inspire-select", "data-sound":sound, "aria-label":`Выбрать ${place.name}`,
        onclick:() => send(`хочу в ${place.name}`)}, el("span", {}, label), el("strong", {}, place.name), el("i", {"aria-hidden":"true"}, "↗")));
  }).filter(Boolean);
  if (!cards.length) { $("view").replaceChildren(); return; }
  $("view").replaceChildren(el("section", {class:"inspiration"}, el("div", {class:"inspiration-head"},
    el("h2", {}, "Для вдохновения"), el("span", {}, "С чего начнём?")), el("div", {class:"inspiration-grid"}, cards)));
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
function comparePackages(cards, items) {
  if (items.length < 2) return cards;
  const optionAttrs = (item) => { const key = "hotel:" + String(item.hotel.id || item.hotel.name);
    return {"data-option-key":key, hidden:preferenceData.hidden.includes(key)}; };
  const table = el("div", {class:"compare-scroll", hidden:true, tabindex:"0", role:"region", "aria-label":"Сравнение вариантов"},
    el("table", {class:"compare-table"},
      el("thead", {}, el("tr", {}, el("th", {scope:"col"}, "Параметр"),
        ...items.map((item, i) => el("th", {scope:"col", ...optionAttrs(item)}, item.title || `Вариант ${i+1}`)))),
      el("tbody", {}, ...[["Демо-стоимость", (x) => x.total], ["Размещение", (x) => x.hotel.name],
        ["Питание", (x) => x.hotel.meal], ["Туда", (x) => legLine(x.out)], ["Обратно", (x) => legLine(x.back)],
        ["Компромиссы", (x) => (x.tradeoffs || []).join("; ") || "—"]].map(([label, get]) =>
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
        el("div", { class: "actions" }, sayBtn("Хочу сюда", `давай ${d.name}`, "btn accent")))))];
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
        el("div", { class: "kicker" }, el("span", {}, `${i + 1} · ${d.country}`), i === 0 ? el("b", {}, "Лучше всего подходит") : null),
        el("h3", {}, d.name),
        el("div", { class: "price num" }, `от ${d.total}`, el("small", {}, d.visa ? `виза (демо): ${d.visa}` : "по России")),
        el("dl", { class: "facts" }, el("dt", {}, "Климат в среднем"), el("dd", {}, d.weather || "—"),
          el("dt", {}, "Дорога"), el("dd", {}, `${d.mode === "train" ? "поезд" : d.stops ? "с пересадкой" : "прямой рейс"}, ${d.travel}`)),
        marks("why", d.reasons.filter((r) => !/^(перелёт|поезд)/.test(r))),
        d.risks.filter((r) => !r.startsWith("виза")).length ? marks("", d.risks.filter((r) => !r.startsWith("виза")).map((t) => ({ level: "warn", text: t }))) : null,
        el("div", { class: "tags" }, d.highlights.map((h) => el("span", { class: "tag" }, h))),
        el("div", { class: "actions" }, sayBtn(`Выбрать ${d.name}`, `давай ${d.name}`, i === 0 ? "btn accent" : "btn ghost")))))];
  },
  packages(p) {
    drawMap(tripRoute(p.trip));
    const out = [];
    if (p.notice) out.push(el("p", { class: "notice" }, p.notice));
    if (p.diff && p.diff.length) out.push(el("p", { class: "notice" }, "Пересобрал план: " + p.diff.join("; ") + "."));
    if (p.relaxed && p.relaxed.length) out.push(el("p", { class: "notice" }, "Чтобы что-то нашлось, я " + p.relaxed.join(", ") + "."));
    out.push(gallery(p.trip.gallery || [p.trip.image], { cls: "cover", alt: p.trip.dest,
      over: el("div", { class: "over" }, el("b", {}, p.trip.dest), el("span", {}, p.trip.weather ? `${p.trip.dates} · климат в среднем: ${p.trip.weather}` : p.trip.dates)) }));
    if (p.calendar && p.calendar.length > 3) {
      const prices = p.calendar.map((d) => d.price), lo = Math.min(...prices), hi = Math.max(...prices);
      out.push(el("h2", { class: "section-title" }, "Когда выгоднее ехать"),
        el("p", { class: "section-sub" }, `Дорога туда и обратно на человека по дате заезда, поездка на ${p.trip.dates.match(/\((.*)\)/)?.[1] || "те же ночи"}. Зелёные — самые выгодные дни.`),
        el("div", { class: "cal", role: "group", "aria-label": "Демонстрационные цены по датам" }, p.calendar.map((d) => el("button", {
          type: "button", class: [d.cheap ? "cheap" : "", d.chosen ? "chosen" : ""].join(" "), title: `${d.day} ${d.month}: ${d.label}`,
          onclick: () => d.chosen || send(`с ${d.day} ${d.month}`) },
          el("span", {}, d.wd), el("b", {}, String(d.day)),
          el("span", { class: "bar", style: `height:${(6 + 22 * (d.price - lo) / Math.max(hi - lo, 1)).toFixed(0)}px` }),
          el("span", { "data-rub-price": d.price }, d.label)))));
    }
    const packageCards = el("div", { class: "cards" }, p.items.map((k, i) => el("article", { class: "card" + (i === 0 ? " best" : "") },
        photo(k.hotel.image, { alt: k.hotel.name, badge: "иллюстрация отеля" }),
        el("div", { class: "kicker" }, el("span", {}, `Вариант ${i + 1}`), i === 0 ? el("b", {}, "Рекомендую") : null),
        el("h3", {}, k.title),
        el("div", { class: "price num" }, k.total, el("small", {}, p.trip.people)),
        el("dl", { class: "facts" },
          el("dt", {}, "Туда"), el("dd", {}, legLine(k.out)),
          el("dt", {}, "Обратно"), el("dd", {}, legLine(k.back)),
          el("dt", {}, "Отель"), el("dd", {}, `${k.hotel.name}, ${k.hotel.stars}★, ${k.hotel.rating} · ${k.hotel.meal} · ${k.hotel.dates}`, hotelSource(k.hotel))),
        el("div", {}, el("h4", {}, "Почему подходит"), marks("why", k.why.slice(1, 6))),
        k.tradeoffs.length ? el("div", {}, el("h4", {}, "Чем жертвуем"), marks("trade", k.tradeoffs.slice(0, 4))) : null,
        el("div", {}, el("h4", {}, "Поездка по часам"), timelineEl(k.timeline)),
        k.checks.some((c) => c.level !== "ok") ? el("div", {}, el("h4", {}, "Обратите внимание"), marks("", k.checks.filter((c) => c.level !== "ok"))) : null,
        el("div", { class: "actions" }, sayBtn("Выбрать вариант", `беру ${i + 1} вариант`, i === 0 ? "btn accent" : "btn ghost")))));
    out.push(el("h2", { class: "section-title" }, p.items.length > 1 ? `${p.items.length} способа поехать` : "Ваша поездка"),
      el("p", { class: "section-sub" }, `${p.trip.weather ? "Климат — средние за 2022–2025 годы, не прогноз: " + p.trip.weather + ". " : ""}Демо-цены и расписание смоделированы; наличие не проверялось.`),
      comparePackages(packageCards, p.items));
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
    const k = p.package;
    const rows = [
      [`Туда · ${k.out.carrier} ${k.out.number}`, `${k.out.depart} → ${k.out.arrive}`, k.out.price],
      [`Отель · ${k.hotel.name}, ${k.hotel.stars}★`, `${k.hotel.dates}, ${k.hotel.meal}, заезд с ${k.hotel.check_in}`, k.hotel.price],
      ["Трансферы", `${k.transfer.note}, ${k.transfer.minutes} в одну сторону`, k.transfer.price],
      [`Обратно · ${k.back.carrier} ${k.back.number}`, `${k.back.depart} → ${k.back.arrive}`, k.back.price],
    ];
    return [
      p.diff && p.diff.length ? el("p", { class: "notice" }, "Пересобрал корзину: " + p.diff.join("; ") + ".") : null,
      el("h2", { class: "section-title" }, `Корзина · ${k.title}`),
      el("p", { class: "section-sub" }, "Перед оплатой проверил, что всё стыкуется."),
      el("div", { class: "split" },
        el("article", { class: "card" },
          el("table", { class: "receipt" }, rows.map(([a, b, c]) => el("tr", {}, el("td", {}, el("div", {}, a), el("small", {}, b)), el("td", {}, c))),
            el("tr", { class: "total" }, el("td", {}, "Итого"), el("td", {}, p.total))),
          el("div", { class: "actions" }, el("button", { type: "button", class: "btn accent", onclick: () => send("да, оформляй") }, "Выбрать способ оплаты"),
            sayBtn("К вариантам", "нет, вернуться к вариантам"))),
        el("article", { class: "card" }, photo(k.hotel.image, { alt: k.hotel.name, badge: "иллюстрация отеля" }),
          el("h4", {}, "Поездка по часам"), timelineEl(k.timeline),
          el("h4", {}, "Состыковки"), marks("", k.checks)))];
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
          el("div", { class: "route" }, el("div", { class: "codes" }, o.origin_code, el("i", {}, "→"), o.dest_code)),
          el("dl", { class: "facts" }, el("dt", {}, "Туда"), el("dd", {}, o.out), el("dt", {}, "Обратно"), el("dd", {}, o.back),
            el("dt", {}, "Отель"), el("dd", {}, `${o.hotel} · ${o.hotel_dates || ""}`), el("dt", {}, "Отмена"), el("dd", {}, cancel)),
          p.requests && p.requests.length ? el("div", {}, el("h4", {}, "Запросы в отель"), marks("why", p.requests)) : null,
          el("div", { class: "actions" }, sayBtn("Ранний заезд", "запроси ранний заезд"), sayBtn("Поздний выезд", "поздний выезд"),
            sayBtn("Перенести на 2 дня", "перенеси на 2 дня позже"), sayBtn("Отменить", "отмени бронь"))),
        el("div", { class: "stub" },
          el("div", { class: "label" }, "Номер заказа"), el("div", { class: "big num" }, o.number),
          el("div", { class: "label" }, "Демо-сумма"), el("div", { class: "big num" }, new Intl.NumberFormat("ru-RU").format(o.total) + " ₽"),
          el("div", { class: "label" }, "Путешественники"), el("div", {}, o.people || "")))];
  },
};

function addMessage(role, content, meta) {
  const m = el("div", { class: `msg ${role}` }, content, meta ? el("span", { class: "meta" }, meta) : null);
  $("log").append(m); preferences.apply();
  requestAnimationFrame(()=>{const scroll=$("conversation-scroll");scroll.scrollTop=scroll.scrollHeight;}); return m;
}
function renderStages(stage) {
  const list = info ? info.stages : [];
  const idx = list.findIndex((s) => s.key === stage);
  $("stages").replaceChildren(...list.map((s, i) => el("li", { class: i < idx ? "done" : i === idx ? "now" : null }, s.title)));
}
function dateControls() {
  const today = new Date(); today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
  const min = today.toISOString().slice(0, 10);
  const start = el("input", {type:"date", min, "aria-label":"Дата начала поездки"});
  const end = el("input", {type:"date", min, "aria-label":"Дата окончания поездки"});
  const note = el("span", {class:"date-status", role:"status"});
  start.addEventListener("change", () => { end.min = start.value || min; });
  // Use the explicit numeric range accepted by the existing dialogue parser;
  // Intl.DateTimeFormat adds a locale-dependent "г." that can break parsing.
  const format = (value) => value.split("-").reverse().join(".");
  return el("details", {class:"quick-dates"}, el("summary", {}, "Выбрать даты"),
    el("div", {class:"date-fields"}, el("label", {}, "Туда", start), el("label", {}, "Обратно", end),
      el("button", {type:"button", onclick: () => {
        if (!start.value || !end.value || end.value <= start.value || start.value < min) {
          note.textContent = "Выберите даты поездки."; return;
        }
        send(`с ${format(start.value)} по ${format(end.value)}`);
      }}, "Готово"), note));
}
function renderSuggest(data) {
  const stage = typeof data === "string" ? data : data.stage;
  if (!conversationStarted) {
    const starters = [
      ["К морю", "Хочу к морю, пока не знаю куда. Предложи идеи без дат.", "sea"],
      ["В горы", "Хочу в горы, пока не знаю куда. Предложи идеи без дат.", "alpine"],
      ["Пока не знаю", null, null]
    ];
    $("suggest").replaceChildren(...starters.map(([label,text,mood]) => el("button", {type:"button",onclick:()=>{
      if(text){experience.setMood(mood);send(text);}else{experience.showIdeas();showMoodChoices();}
    }},label)),el("button",{type:"button",class:"example-link",onclick:()=>experience.openExamples()},"Посмотреть примеры запросов ↗"));
    return;
  }
  const payload = typeof data === "object" ? data.payload || {} : {};
  // Explicit server choices take precedence over stage-based convenience controls.
  if (Array.isArray(data.suggestions) && data.suggestions.includes("новая поездка")) {
    $("suggest").replaceChildren(...data.suggestions.map((text) => el("button", {type:"button", onclick:() => send(text)}, text)));
    return;
  }
  const question = typeof data === "object" ? String(data.reply || "").split("?")[0].toLowerCase() : "";
  if (payload.kind === "question" && (["when", "dates", "date_from", "date_to"].includes(payload.field) ||
      (!payload.field && String(data.reply || "").includes("?") && /когда|дат[ыу]|месяц|время года/.test(question)))) {
    $("suggest").replaceChildren(dateControls(), el("button", {type:"button", onclick:() => send("пока не знаю")}, "Пока не знаю"));
    return;
  }
  if (payload.kind === "question" && (payload.field === "origin" ||
      (!payload.field && String(data.reply || "").includes("?") && /откуда|город отправления|город вылета/.test(question)))) {
    $("suggest").replaceChildren(locationChoice()); return;
  }
  if (payload.kind === "question" && payload.field === "duration") {
    const nights = /ноч/i.test(String(data.reply || ""));
    const choices = nights ? [["3 ночи", "на 3 ночи"], ["7 ночей", "на 7 ночей"]] : [["3 дня", "на 3 дня"], ["7 дней", "на 7 дней"]];
    $("suggest").replaceChildren(...[...choices, ["Пока не знаю", "пока не знаю"]]
      .map(([label, text]) => el("button", {type:"button", onclick:() => send(text)}, label)));
    return;
  }
  if (payload.kind === "question" && payload.field === "people") {
    $("suggest").replaceChildren(...[["1 взрослый", "1 взрослый"], ["2 взрослых", "2 взрослых"], ["Пока не знаю", "пока не знаю"]]
      .map(([label, text]) => el("button", {type:"button", onclick:() => send(text)}, label)));
    return;
  }
  const supplied = typeof data === "object" && Array.isArray(data.suggestions) ?
    data.suggestions.filter((text) => typeof text === "string" && !(info?.examples || []).includes(text)) : [];
  const understood = typeof data === "object" ? data.understood || [] : [];
  const options = (typeof data === "object" && Array.isArray(data.suggestions) ? supplied : (inspiration.quick?.[stage] || [])).filter((text) =>
    !(understood.includes("по России") && /только по России/i.test(text)) &&
    !(understood.includes("за границу") && /за границу/i.test(text)));
  $("suggest").replaceChildren(...options.map((text) => el("button", {type:"button", onclick:() => send(text)}, text)));
}
function locationChoice() {
  const result = el("div", { class: "src", role: "status" });
  const button = el("button", { type: "button", class: "btn ghost", onclick: () => {
    if (!navigator.geolocation) { result.textContent = "Браузер не поддерживает определение местоположения."; return; }
    result.textContent = "Запрашиваю разрешение браузера…";
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      const rad = (n) => n * Math.PI / 180;
      const distance = (p) => {
        const a = Math.sin(rad(p.lat - coords.latitude) / 2) ** 2 + Math.cos(rad(coords.latitude)) * Math.cos(rad(p.lat)) *
          Math.sin(rad(p.lon - coords.longitude) / 2) ** 2;
        return 12742 * Math.asin(Math.sqrt(Math.min(1, a)));
      };
      const nearest = (info.origins || []).map((p) => ({ ...p, km: distance(p) })).sort((a, b) => a.km - b.km)[0];
      if (!nearest || nearest.km > 80) {
        result.textContent = "Рядом нет доступного города отправления в демо. Напишите город вручную."; return;
      }
      result.replaceChildren(el("p", {}, `Похоже, вы рядом с городом ${nearest.name}. Использовать его?`),
        sayBtn("Да, использовать", `из ${nearest.name}`, "btn accent"));
    }, () => { result.textContent = "Не удалось определить местоположение. Город можно написать вручную."; },
    { timeout: 8000, maximumAge: 300000, enableHighAccuracy: false });
  } }, "Определить город");
  return el("div", { class: "actions" }, button, result);
}
function render(data) {
  sessionId = data.session_id; lastData = data;
  renderStages(data.stage); renderHead(data); renderConditions(data); renderSuggest(data);
  document.querySelector(".board").classList.toggle("compact", ["plan", "cart", "booked"].includes(data.stage));
  const p = data.payload || {};
  $("map").hidden = p.kind === "order";
  const notice = p.notice && p.kind !== "packages" ? el("p", { class: "notice" }, p.notice) : null;
  if (views[p.kind]) $("view").replaceChildren(...[notice, ...views[p.kind](p)].filter(Boolean));
  else if (["greeting", "flight_results"].includes(p.kind)) { $("view").replaceChildren(); drawMap({}); }
  else if (p.kind === "question") {
    $("view").replaceChildren(...[notice].filter(Boolean));
    if (data.stage !== "destination") drawMap({});
  }
  decorateOptions(p);
  preferences.apply(); experience.update(data);
}
async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const detail=await r.json().catch(()=>({}));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Не удалось отправить. Текст сохранён — попробуйте ещё раз.");
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
  busy=value; $("send").disabled=value; $("undo").disabled=value || !lastData?.can_undo;
  $("reset").disabled=value; $("conditions-edit").disabled=value;
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
    if(replacing){replacing.bot.remove();user.replaceChildren(text);}
    const reply=el("div"); renderTravelReply(reply,data.reply,(data.payload||{}).kind);
    const bot=addMessage("bot",reply);
    latestTurn={text,user,bot}; editing=false; $("edit-banner").hidden=true;
    render(data); attachEdit(latestTurn,data); $("say").textContent="";
    experience.showChat();
    return true;
  } catch(error) {
    typing.remove(); if(!replacing)user.remove();
    conversationStarted=previousStarted;
    if(!$("text").value)experience.fill(text);
    addMessage("bot",error.message || "Не удалось отправить. Текст сохранён — попробуйте ещё раз.");
    renderSuggest(lastData || "start"); return false;
  } finally {setBusy(false);voice.update();$("text").focus({preventScroll:true});}
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
    $("voice-status").hidden=false;$("voice-status").textContent="Последняя реплика отменена. Можно исправить и отправить снова.";
  } catch(error){addMessage("bot",error.message);} finally {setBusy(false);}
}
function greet(){addMessage("bot","Расскажите о поездке — можно начать с желания или описать всё сразу.");}
function start(){conversationStarted=false;lastDestination=null;lastData=null;latestTurn=null;editing=false;
  $("map").hidden=false;renderStages("start");renderHead(null);renderConditions(null);renderSaved();renderSuggest("start");
  $("view").replaceChildren();drawMap({});experience.reset();greet();}
$("ask").addEventListener("submit",(event)=>{
  event.preventDefault();if(busy)return;
  const submit=()=>{
    const text=$("text").value.trim();
    if(!text){$("voice-status").hidden=false;$("voice-status").textContent="Напишите сообщение или нажмите микрофон, чтобы сказать голосом.";$("text").focus();return;}
    experience.fill("");voice.clearStatus();send(text);
  };
  if(voice.isActive()){voice.finish(submit);return;}  // ↑ во время записи — распознать и сразу отправить
  submit();
});
async function resetConversation(){
  if(busy)return;voice.cancel();setBusy(true);
  try {if(sessionId)await post("/api/reset",{session_id:sessionId});
    sessionId=null;$("log").replaceChildren();$("view").replaceChildren();$("say").textContent="";start();
  }catch(error){addMessage("bot","Не удалось начать новую поездку. Попробуйте ещё раз.");}finally{setBusy(false);}
}
async function initialise() {
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
    tripMap.setData(i, l); experience.configureExamples(i); start();
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
  }
}
initialise();
