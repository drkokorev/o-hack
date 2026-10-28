const $ = (id) => document.getElementById(id);
let sessionId = null, busy = false, info = null;
const QUICK = {
  destination: ["покажи другие направления", "только по России", "а за границу?"],
  plan: ["а если на два дня позже?", "подешевле", "покажи другие отели", "только без пересадок", "другое направление"],
  cart: ["да, оформляй", "нет, вернуться к вариантам", "а если на день раньше?"],
  payment: ["оплата картой", "оплата СБП", "нет"],
  booked: ["запроси ранний заезд", "поздний выезд", "перенеси на 2 дня позже", "отмени бронь"],
};

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

const tripMap = createTripMap({ container: $("map"), onChoose: (place) => send(`хочу в ${place.name}`) });
const drawMap = (options = {}) => tripMap.draw(options);

function renderHead(data) {
  const p = (data && data.payload) || {};
  const trip = p.trip || (p.order && { origin_code: p.order.origin_code, dest_code: p.order.dest_code, origin: p.order.origin, dest: p.order.dest });
  const understood = data ? data.understood : [], assumed = data ? data.assumptions || [] : [];
  const chips = understood.map((c) => el("span", { class: "chip" }, c))
    .concat(assumed.map((a) => el("span", { class: "chip assumed", title: "Агент предположил сам — поправьте, если не так" }, a)));
  if (p.kind === "order") { $("head").replaceChildren(); return; }
  if (trip && trip.dest_code) {
    $("head").replaceChildren(el("div", { class: "route" },
      el("div", { class: "codes" }, trip.origin_code, el("i", {}, "→"), trip.dest_code),
      el("div", { class: "names" }, [trip.origin + " — " + trip.dest, trip.dates, trip.people].filter(Boolean).join(" · "))),
      chips.length ? el("div", { class: "chips" }, chips) : null);
  } else if (chips.length) {
    const title = data.stage === "destination" ? "Подбираю направление" : "Уточняю поездку";
    $("head").replaceChildren(el("div", { class: "hero" }, el("h1", {}, title)), el("div", { class: "chips" }, chips));
  } else {
    $("head").replaceChildren(el("div", { class: "hero" },
      el("h1", {}, "Расскажите о поездке. Остальное соберёт агент."),
      el("p", {}, "Направление, перелёт или поезд, отель и трансфер — с объяснением выбора, проверкой состыковок и оформлением.")));
  }
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

const views = {
  place_info(p) {
    const d = p.place;
    drawMap({ targets: [{ name: d.name, lat: d.lat, lon: d.lon }] });
    return [el("h2", { class: "section-title" }, d.name), el("p", { class: "section-sub" }, d.country),
      el("article", { class: "card" }, el("h3", {}, "Место найдено"),
        el("p", {}, "В демонстрационном каталоге пока нет предложений для этого места. Данные о ценах и наличии не выдумываем."),
        sayBtn("Другие направления", "покажи ещё", "btn ghost"))];
  },
  ideas(p) {
    drawMap({ targets: p.items.map((d) => ({ name: d.name, lat: d.lat, lon: d.lon })) });
    return [el("h2", { class: "section-title" }, "Идеи для поездки"),
      el("p", { class: "section-sub" }, "Пока без расчёта дат и цены. Выберите направление, чтобы продолжить."),
      el("div", { class: "cards" }, p.items.map((d, i) => el("article", { class: "card" },
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
    drawMap({ origin: p.origin, targets: p.items.map((d) => ({ name: d.name, lat: d.lat, lon: d.lon })) });
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
        el("div", { class: "cal", role: "list" }, p.calendar.map((d) => el("button", {
          type: "button", class: [d.cheap ? "cheap" : "", d.chosen ? "chosen" : ""].join(" "), title: `${d.day} ${d.month}: ${d.label}`,
          onclick: () => d.chosen || send(`с ${d.day} ${d.month}`) },
          el("span", {}, d.wd), el("b", {}, String(d.day)),
          el("span", { class: "bar", style: `height:${(6 + 22 * (d.price - lo) / Math.max(hi - lo, 1)).toFixed(0)}px` }),
          el("span", {}, d.label)))));
    }
    out.push(el("h2", { class: "section-title" }, p.items.length > 1 ? `${p.items.length} способа поехать` : "Ваша поездка"),
      el("p", { class: "section-sub" }, `${p.trip.weather ? "Климат — средние за 2022–2025 годы, не прогноз: " + p.trip.weather + ". " : ""}Демо-цены и расписание смоделированы; наличие не проверялось.`),
      el("div", { class: "cards" }, p.items.map((k, i) => el("article", { class: "card" + (i === 0 ? " best" : "") },
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
        el("div", { class: "actions" }, sayBtn("Выбрать вариант", `беру ${i + 1} вариант`, i === 0 ? "btn accent" : "btn ghost"))))));
    return out;
  },
  hotels(p) {
    return [el("h2", { class: "section-title" }, "Другие отели"),
      el("p", { class: "section-sub" }, "Выберите — пересоберу поездку с ним, дорогу оставлю. Отзывы, оценки и цены — демо."),
      el("div", { class: "cards" }, p.items.map((h, i) => el("article", { class: "card" },
        photo(h.image, { alt: h.name, badge: "иллюстрация" }),
        el("div", { class: "kicker" }, el("span", {}, `${h.stars}★ · ${h.area}`), el("span", {}, `${h.rating} · ${h.reviews} отзывов`)),
        el("h3", {}, h.name), hotelSource(h),
        el("div", { class: "price num" }, h.price, el("small", {}, `${h.per_night} за ночь · ${h.meal}`)),
        el("div", { class: "tags" }, h.amenities.map((a) => el("span", { class: "tag" }, a))),
        el("div", {}, el("h4", {}, "Хвалят"), marks("why", h.praise)),
        el("div", {}, el("h4", {}, "Жалуются"), marks("trade", h.complaints)),
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
    $("map").replaceChildren();
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
  $("log").append(m); $("log").scrollTop = $("log").scrollHeight; return m;
}
function shortReply(text, kind) {
  if (kind === "order") { const lines = text.split("\n"); return [lines[0], lines[lines.length - 1]].join("\n"); }
  if (!["destinations", "packages", "cart", "hotels"].includes(kind)) return text;
  const blocks = text.split("\n\n");
  const head = blocks[0].split("\n").filter((l) => !/^\s*(\d+\.|•)\s/.test(l));
  if (blocks.length === 1) {
    const first = head.slice(0, kind === "cart" ? 1 : 3);
    const last = head[head.length - 1];
    return [...first, last].filter((line, index, all) => line && all.indexOf(line) === index).join("\n");
  }
  const assumptions = blocks.find((b) => b.startsWith("Я предположил:"));
  return [head.slice(0, kind === "cart" ? 1 : 3).join("\n"), assumptions, blocks[blocks.length - 1]]
    .filter((part, index, all) => part && all.indexOf(part) === index).join("\n\n");
}
function renderStages(stage) {
  const list = info ? info.stages : [];
  const idx = list.findIndex((s) => s.key === stage);
  $("stages").replaceChildren(...list.map((s, i) => el("li", { class: i < idx ? "done" : i === idx ? "now" : null }, s.title)));
}
function renderSuggest(data) {
  const stage = typeof data === "string" ? data : data.stage;
  const items = Array.isArray(data.suggestions) ? data.suggestions :
    (stage === "start" ? (info ? info.examples : []) : (QUICK[stage] || []));
  $("suggest").replaceChildren(...items.map((q) => el("button", { type: "button", onclick: () => send(q) }, q)));
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
  return el("div", { class: "actions" }, button,
    el("p", { class: "src" }, "Только с разрешения браузера. Координаты остаются в браузере; город нужно подтвердить."), result);
}
function render(data) {
  sessionId = data.session_id;
  renderStages(data.stage); renderHead(data); renderSuggest(data);
  document.querySelector(".board").classList.toggle("compact", ["plan", "cart", "booked"].includes(data.stage));
  const p = data.payload || {};
  const notice = p.notice && p.kind !== "packages" ? el("p", { class: "notice" }, p.notice) : null;
  if (views[p.kind]) $("view").replaceChildren(...[notice, ...views[p.kind](p)].filter(Boolean));
  else if (p.kind === "greeting") { $("view").replaceChildren(); drawMap({}); }
  else if (p.kind === "question") {
    $("view").replaceChildren(...[notice, el("div", { class: "ask-card" }, data.reply.split("\n\n").pop()),
      p.field === "origin" ? locationChoice() : null].filter(Boolean));
    if (data.stage !== "destination") drawMap({});
  }
}
async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`Сервер ответил ${r.status}`);
  return r.json();
}
async function send(text) {
  if (busy || !text.trim()) return;
  busy = true; $("send").disabled = true;
  addMessage("user", text);
  const typing = addMessage("bot", el("span", { class: "typing", role: "status", "aria-label": "Агент думает" }, el("i"), el("i"), el("i")));
  try {
    const data = await post("/api/chat", { text, session_id: sessionId });
    typing.remove();
    addMessage("bot", shortReply(data.reply, (data.payload || {}).kind));
    render(data);
    const mobile = window.matchMedia("(max-width: 900px)").matches;
    $("say").textContent = mobile ? shortReply(data.reply, (data.payload || {}).kind) : "";
    if (data.payload) window.scrollTo({ top: 0, behavior: mobile ? "auto" : "smooth" });
  } catch (e) {
    typing.remove();
    addMessage("bot", "Сервер не ответил. Проверьте, что приложение запущено, и отправьте сообщение ещё раз.");
  } finally { busy = false; $("send").disabled = false; $("text").focus(); }
}
function greet() {
  addMessage("bot", "Привет! Расскажите, какой поездки хочется. Если пока не знаете куда или когда, вместе найдём идеи.");
}
function start() { renderStages("start"); renderHead(null); renderSuggest("start"); drawMap({}); greet(); }
$("ask").addEventListener("submit", (e) => { e.preventDefault(); const t = $("text").value; $("text").value = ""; send(t); });
window.attachVoiceInput({ input: $("text"), button: $("send"), status: $("voice-status"), form: $("ask") });
$("reset").addEventListener("click", async () => {
  if (sessionId) await post("/api/reset", { session_id: sessionId }).catch(() => {});
  sessionId = null; $("log").replaceChildren(); $("view").replaceChildren(); $("say").textContent = ""; start();
});
Promise.all([fetch("/api/info").then((r) => r.json()), fetch("/static/land.geojson").then((r) => r.json())])
  .then(([i, l]) => { info = i; tripMap.setData(i, l); start(); })
  .catch(() => addMessage("bot", "Сервер недоступен."));
