/* Reusable map. The host provides the chat callback; data stays in the map API. */
(function () {
  "use strict";
  const scriptUrl = document.currentScript && document.currentScript.src;
  const staticRoot = scriptUrl ? new URL(".", scriptUrl) : new URL("/static/", location.href);
  const asset = (path) => new URL(path, staticRoot).href;
  const ORIGIN = staticRoot.origin;
  const fmt = new Intl.NumberFormat("ru-RU");
  const KINDS = { all: "Все места", city: "Города", hotel: "Размещение",
    airport: "Аэропорты", beach: "Пляжи", camping: "Кемпинги" };
  const KIND_NAMES = { city: "Населённый пункт", hotel: "Объект размещения",
    airport: "Аэропорт", beach: "Пляж", camping: "Кемпинг" };
  // Illustrations are deliberately a small curated sample, placed at city
  // centres, not a claim that all landmarks or their tickets are in the catalog.
  const LANDMARKS = [
    { city: "Париж", name: "Эйфелева башня", lat: 48.8566, lon: 2.3522, icon: "tower", url: "https://www.toureiffel.paris/en/access-map" },
    { city: "Москва", name: "Московский Кремль", lat: 55.7558, lon: 37.6173, icon: "kremlin", url: "https://kreml.ru/ru" },
    { city: "Дубай", name: "Бурдж-Халифа", lat: 25.2048, lon: 55.2708, icon: "spire", url: "https://www.burjkhalifa.ae/contact-us/" },
  ];

  function node(tag, attrs, ...children) {
    const n = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value == null || value === false) continue;
      if (key === "class") n.className = value;
      else if (key.startsWith("on")) n.addEventListener(key.slice(2), value);
      else n.setAttribute(key, String(value));
    }
    for (const child of children.flat()) {
      if (child == null || child === false) continue;
      n.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return n;
  }
  function safeUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch (_) { return null; }
  }
  function safeLink(value, label) {
    const href = safeUrl(value);
    return href ? node("a", { href, target: "_blank", rel: "noopener noreferrer" }, label) : null;
  }
  function loadStyle(href) {
    if (document.querySelector(`link[data-map-style="${href}"]`)) return;
    const link = node("link", { rel: "stylesheet", href, "data-map-style": href });
    document.head.append(link);
  }
  async function json(url, signal) {
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  function normalizeLon(value) {
    return ((value + 180) % 360 + 360) % 360 - 180;
  }
  const overviewZoom = () => matchMedia("(max-width: 700px)").matches ? 0.9 : 1.45;
  function boundsFor(map) {
    const b = map.getBounds();
    const rawWest = b.getWest(), rawEast = b.getEast();
    const south = Math.max(-90, Math.min(90, b.getSouth()));
    const north = Math.max(south, Math.min(90, b.getNorth()));
    if (rawEast - rawWest >= 359.9) return { west: -180, east: 180, south, north, span: 360 };
    const west = normalizeLon(rawWest), east = normalizeLon(rawEast);
    return { west, east, south, north, span: (east - west + 360) % 360 || 360 };
  }

  window.createTripMap = function createTripMap({ container, onChoose, apiBase = ORIGIN }) {
    const api = (path) => new URL(path, apiBase).href;
    let info = null, land = null, lib = null, map = null, catalog = null, countries = null;
    let events = [], eventChecked = null, options = {}, kind = "all", controller = null;
    let sequence = 0, detailSequence = 0, timer = 0, userMoved = false, manualCountry = null, initialCountry = null;
    let clusterMarkers = [], eventMarkers = [], landmarkMarkers = [], records = new Map(), currentItems = [], listShown = 40;
    let popup = null, mapReady = false, fallback = null, loadComplete = false;
    const holder = node("div", { class: "map-canvas", "aria-label": "Глобус с местами и событиями" });
    const status = node("span", { class: "map-status", role: "status", "aria-live": "polite" }, "Загружаем карту…");
    const filter = node("select", { class: "map-kind", "aria-label": "Тип мест",
      onchange: (e) => { kind = e.target.value; schedule(); } },
      Object.entries(KINDS).map(([id, title]) => node("option", { value: id }, title)));
    const scope = node("button", { type: "button", class: "map-scope", onclick: () => world() }, "Весь мир");
    const controls = node("div", { class: "map-controls" },
      node("button", { type: "button", "aria-label": "Приблизить карту", onclick: () => map && map.zoomIn() }, "+"),
      node("button", { type: "button", "aria-label": "Отдалить карту", onclick: () => map && map.zoomOut() }, "−"));
    const search = node("input", { type: "search", placeholder: "Поиск в видимой области",
      "aria-label": "Найти место в видимой области", oninput: () => { listShown = 40; renderList(); } });
    const itemsList = node("div", { class: "map-list-items" });
    const more = node("button", { class: "map-more", type: "button",
      onclick: () => { listShown += 40; renderList(); } }, "Показать ещё");
    const list = node("details", { class: "map-list" }, node("summary", {}, "Места и группы на карте"),
      search, itemsList, more);
    const detailList = node("div", { class: "map-choice", hidden: true, role: "region",
      "aria-label": "Несколько объектов рядом" });
    const legacySelect = node("select", { "aria-label": "Выбрать направление из списка",
      onchange: (e) => {
        const place = (info && info.places || []).find((p) => p.id === e.target.value);
        if (place) chooseLegacy(place);
      } });
    const footer = node("div", { class: "map-footer" },
      node("span", {}, "Открытые данные · наличие не проверено"), legacySelect);
    const surface = node("div", { class: "map-surface" }, holder, controls);
    const head = node("div", { class: "map-head" }, node("div", { class: "map-caption" },
      node("b", {}, "Куда отправимся?"), node("small", {}, "Места и события на глобусе")),
      node("div", { class: "map-tools" }, filter, scope));
    const body = node("div", { class: "map-frame" }, head, surface,
      node("div", { class: "map-status-row" }, status,
        node("span", { class: "map-legend" }, "● места  ·  ✦ события")),
      detailList, list, footer);
    container.classList.add("trip-map");
    container.replaceChildren(body);

    function showStatus(text, error = false) {
      status.textContent = text;
      status.classList.toggle("error", error);
    }
    function clearMarkers(markers) {
      for (const marker of markers) marker.remove();
      markers.length = 0;
    }
    function closePopup() { if (popup) popup.remove(); popup = null; }
    function makePopup(lon, lat, content) {
      closePopup();
      popup = new lib.Popup({ closeButton: true, closeOnClick: false, maxWidth: "310px" })
        .setLngLat([lon, lat]).setDOMContent(content).addTo(map);
    }
    function fillLegacySelect() {
      legacySelect.replaceChildren(node("option", { value: "", disabled: true, selected: true }, "Выбрать из списка"),
        ...(info && info.places || []).slice().sort((a, b) => a.name.localeCompare(b.name, "ru"))
          .map((p) => node("option", { value: p.id }, p.name)));
    }
    function chooseLegacy(place) {
      detailList.hidden = false;
      detailList.replaceChildren(node("b", {}, place.name),
        node("button", { type: "button", onclick: () => { detailList.hidden = true; onChoose(place); } }, "Хочу сюда"));
      detailList.querySelector("button").focus();
    }
    function sourceText(point) {
      const meta = (catalog && catalog.sources || {})[point.source] || {};
      const name = point.source_name || meta.name || "Источник не указан";
      const release = point.source_release || meta.release;
      const accessed = point.source_accessed_at || meta.accessed_at;
      const datedRelease = /^\d{4}-\d{2}-\d{2}/.test(String(release || ""));
      const details = [release ? `Снимок: ${release}` : null,
        !datedRelease ? "Дата снимка не указана" : null,
        accessed ? `Получен: ${String(accessed).slice(0, 10)}` : null].filter(Boolean);
      return { name, details: details.join(" · "),
        url: point.source_url || meta.url };
    }
    function pointContent(point) {
      const source = sourceText(point);
      const content = node("div", { class: "map-pop" },
        node("div", { class: "map-pop-kind" }, KIND_NAMES[point.kind] || "Место"),
        node("strong", {}, point.name || KIND_NAMES[point.kind] || "Место"),
        point.address ? node("p", {}, point.address) : null,
        point.country_name ? node("p", {}, point.country_name) : null);
      if (point.kind === "hotel") {
        content.append(node("p", { class: "map-note" }, "Цена, условия и наличие не подтверждены."));
      } else if (point.kind === "camping") {
        content.append(node("p", { class: "map-note" }, "Условия размещения не проверены."));
      } else if (point.kind === "airport") {
        content.append(node("p", { class: "map-note" }, "Рейсы и билеты не проверены."));
      }
      content.append(node("p", { class: "map-source" }, source.name, " · ", source.details));
      const links = node("div", { class: "map-pop-links" },
        safeLink(source.url, "Источник ↗"), safeLink(point.website, "Сайт объекта ↗"));
      if (links.childNodes.length) content.append(links);
      if (point.kind === "city" && point.name) {
        content.append(node("button", { type: "button", class: "map-choose",
          onclick: () => { closePopup(); onChoose(point); } }, "Хочу сюда"));
      }
      return content;
    }
    async function openPoint(id, lat, lon) {
      const request = ++detailSequence;
      try {
        const point = await json(api(`/api/map/point/${encodeURIComponent(id)}`));
        if (request !== detailSequence || !map) return;
        makePopup(lon, lat, pointContent(point));
      } catch (_) { showStatus("Не удалось открыть место. Попробуйте ещё раз.", true); }
    }
    function showOverlapping(features, lngLat) {
      const ids = [...new Set(features.map((feature) => String(feature.properties.id)))];
      if (ids.length === 1) { openPoint(ids[0], lngLat.lat, lngLat.lng); return; }
      detailList.hidden = false;
      detailList.replaceChildren(node("b", {}, `Рядом: ${fmt.format(ids.length)}`),
        ...ids.map((id) => {
          const item = records.get(id);
          return node("button", { type: "button", class: "map-nearby",
            onclick: () => { detailList.hidden = true; openPoint(id, item.lat, item.lon); } },
            item.name || KIND_NAMES[item.kind] || "Место");
        }));
      detailList.querySelector("button")?.focus();
    }
    function eventContent(event) {
      return node("div", { class: "map-pop" }, node("div", { class: "map-pop-kind" }, `Событие · ${event.category}`),
        node("strong", {}, event.name), node("p", {}, `${event.city}, ${event.country}`),
        node("p", {}, event.dates), node("p", { class: "map-note" }, "Метка показывает город. Билеты не проверены."),
        node("p", { class: "map-source" }, `Источник: ${event.source} · проверено ${eventChecked}`),
        node("div", { class: "map-pop-links" }, safeLink(event.url, "Источник ↗")),
        node("button", { type: "button", class: "map-choose",
          onclick: () => { closePopup(); onChoose({ id: event.id, name: event.city, lat: event.lat, lon: event.lon }); } }, "Выбрать город"));
    }
    function landmarkIcon(kind) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 32 38"); svg.setAttribute("aria-hidden", "true");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const shapes = { tower: "M16 2v5M13 8h6M15 8c-1 12-3 20-9 27m11-27c1 12 3 20 9 27M9 26h14M11 19h10M12 35c0-5 8-5 8 0M5 36h22",
        kremlin: "M3 35h26M5 35V18h22v17M8 18v-6l4-5 4 5v6M16 18v-9l4-5 4 5v9M5 23h22M9 35v-6h4v6M20 35v-6h4v6",
        spire: "M16 2v5M15 7h2v8h2v5h2v5h2v10H9V25h2v-5h2v-5h2zM7 36h18" };
      path.setAttribute("d", shapes[kind]); path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor");
      path.setAttribute("stroke-width", "1.8"); path.setAttribute("stroke-linecap", "round"); path.setAttribute("stroke-linejoin", "round");
      svg.append(path); return svg;
    }
    function renderLandmarks() {
      clearMarkers(landmarkMarkers);
      if (!map || map.getZoom() < 3 || map.getZoom() >= 10) return;
      for (const place of LANDMARKS) {
        const button = node("button", { class: "landmark-marker", type: "button", "aria-label": `${place.city}: ${place.name}`,
          onclick: () => makePopup(place.lon, place.lat, node("div", { class: "map-pop" },
            node("div", { class: "map-pop-kind" }, "Идея для поездки"), node("strong", {}, place.name),
            node("p", {}, place.city), node("p", { class: "map-note" }, "Иллюстрация у центра города. Условия посещения уточняйте у источника."),
            node("div", { class: "map-pop-links" }, safeLink(place.url, "Официальный сайт ↗")),
            node("button", { type: "button", class: "map-choose", onclick: () => {
              closePopup(); onChoose({ name: place.city, lat: place.lat, lon: place.lon });
            } }, "Выбрать город"))) }, landmarkIcon(place.icon), node("span", {}, place.city));
        landmarkMarkers.push(new lib.Marker({ element: button, anchor: "bottom", opacityWhenCovered: 0 })
          .setLngLat([place.lon, place.lat]).addTo(map));
      }
    }
    function renderEvents() {
      if (!map || !lib) return;
      clearMarkers(eventMarkers);
      const today = new Date().toISOString().slice(0, 10);
      const groups = [];
      for (const event of events) {
        if (event.end < today) continue;
        const pos = map.project([event.lon, event.lat]);
        let group = groups.find((candidate) => Math.hypot(candidate.x - pos.x, candidate.y - pos.y) < 55);
        if (!group) { group = { x: pos.x, y: pos.y, events: [] }; groups.push(group); }
        group.events.push(event);
      }
      for (const { events: group } of groups) {
        const first = group[0];
        const button = node("button", { class: "event-marker", type: "button",
          "aria-label": group.length === 1 ? `Событие: ${first.name}, ${first.city}` : `События: ${group.length}`,
          onclick: () => {
            if (group.length === 1) { makePopup(first.lon, first.lat, eventContent(first)); return; }
            const content = node("div", { class: "map-pop" }, node("strong", {}, "События рядом"),
              ...group.map((event) => node("button", { type: "button", class: "map-event-row",
                onclick: () => makePopup(event.lon, event.lat, eventContent(event)) },
                `${event.city} · ${event.name}`)));
            makePopup(first.lon, first.lat, content);
          } }, "✦", group.length > 1 ? node("span", {}, String(group.length)) : null);
        eventMarkers.push(new lib.Marker({ element: button, anchor: "center", opacityWhenCovered: 0 }).setLngLat([first.lon, first.lat]).addTo(map));
      }
    }
    function renderClusters(items) {
      clearMarkers(clusterMarkers);
      for (const item of items) {
        const button = node("button", { type: "button", class: "cluster-marker",
          "aria-label": `Мест в группе: ${fmt.format(item.count)}. Приблизить`,
          onclick: () => map.easeTo({ center: [item.lon, item.lat], zoom: Math.min(13, map.getZoom() + 2.1),
            duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 }) },
          fmt.format(item.count));
        clusterMarkers.push(new lib.Marker({ element: button, anchor: "center", opacityWhenCovered: 0 })
          .setLngLat([item.lon, item.lat]).addTo(map));
      }
    }
    function renderList() {
      const query = search.value.trim().toLocaleLowerCase("ru-RU");
      const matched = currentItems.filter((item) => !query ||
        (item.name || KIND_NAMES[item.kind] || "").toLocaleLowerCase("ru-RU").includes(query));
      itemsList.replaceChildren(...matched.slice(0, listShown).map((item) => {
        if (item.count != null) return node("button", { type: "button", class: "map-list-row",
          onclick: () => map.easeTo({ center: [item.lon, item.lat], zoom: Math.min(13, map.getZoom() + 2.1) }) },
          `Группа · ${fmt.format(item.count)} мест`);
        return node("button", { type: "button", class: "map-list-row",
          onclick: () => { map.jumpTo({ center: [item.lon, item.lat] }); openPoint(item.id, item.lat, item.lon); } },
          item.name || KIND_NAMES[item.kind] || "Место", node("small", {}, KIND_NAMES[item.kind] || ""));
      }));
      more.hidden = matched.length <= listShown;
      if (!matched.length) itemsList.append(node("p", { class: "map-empty" },
        loadComplete ? "Нет мест в этой области." : "Загрузка ещё не завершена."));
    }
    function queryParams(bounds, extra) {
      return new URLSearchParams({ kind, west: String(bounds.west), south: String(bounds.south),
        east: String(bounds.east), north: String(bounds.north), ...extra });
    }
    function setPoints(items) {
      records = new Map(items.map((p) => [String(p.id), p]));
      map.getSource("catalog-points").setData({ type: "FeatureCollection", features: items.map((p) => ({
        type: "Feature", properties: { id: String(p.id), kind: p.kind },
        geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      })) });
    }
    async function refresh() {
      if (!map || !catalog) return;
      if (controller) controller.abort();
      controller = new AbortController();
      const signal = controller.signal, own = ++sequence, bounds = boundsFor(map);
      const individual = map.getZoom() >= 10 && bounds.span <= 2 && bounds.north - bounds.south <= 2;
      detailList.hidden = true; loadComplete = false; listShown = 40;
      showStatus("Загружаем места…");
      try {
        if (!individual) {
          setPoints([]); currentItems = [];
          const zoom = Math.max(0, Math.min(8, Math.floor(map.getZoom()) + 2));
          const data = await json(api(`/api/map/clusters?${queryParams(bounds, { zoom: String(zoom) })}`), signal);
          if (own !== sequence) return;
          if (data.catalog_version !== catalog.catalog_version) { await reloadCatalog(); return; }
          currentItems = data.items; loadComplete = true;
          renderClusters(data.items); renderList();
          const total = data.items.reduce((sum, item) => sum + item.count, 0);
          showStatus(`${fmt.format(total)} записей в области · приблизьте группу`);
        } else {
          clearMarkers(clusterMarkers); setPoints([]); currentItems = [];
          let cursor = 0, pages = 0;
          do {
            const data = await json(api(`/api/map/points?${queryParams(bounds, { limit: "1000", cursor: String(cursor) })}`), signal);
            if (own !== sequence) return;
            if (data.catalog_version !== catalog.catalog_version) { await reloadCatalog(); return; }
            currentItems.push(...data.items);
            pages++;
            if (pages % 2 === 0 || data.next_cursor == null) {
              setPoints(currentItems); renderList();
              showStatus(`${fmt.format(currentItems.length)} мест${data.next_cursor == null ? "" : " · загружаем ещё…"}`);
            }
            if (data.next_cursor != null && data.next_cursor <= cursor) throw new Error("Invalid cursor");
            cursor = data.next_cursor;
          } while (cursor != null);
          loadComplete = true; renderList();
        }
      } catch (error) {
        if (error.name === "AbortError" || own !== sequence) return;
        loadComplete = false;
        showStatus("Не все места загружены. Двигайте карту или повторите.", true);
        renderList();
      }
    }
    async function reloadCatalog() {
      catalog = await json(api("/api/map/catalog"));
      schedule();
    }
    function schedule() {
      if (controller) controller.abort();
      sequence++;
      clearTimeout(timer);
      timer = setTimeout(refresh, 180);
    }
    function world() {
      if (!map) return;
      const point = countryCenter(manualCountry || initialCountry) || [10, 25];
      map.easeTo({ center: point, zoom: overviewZoom(),
        duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 });
    }
    function countryCenter(code) {
      const f = countries && countries.features.find((feature) => feature.properties.code === code);
      const p = f && f.properties;
      return p && Number.isFinite(p.label_lon) && Number.isFinite(p.label_lat) ? [p.label_lon, p.label_lat] : null;
    }
    function setCountry(code, force) {
      if (force) manualCountry = code;
      else initialCountry = code;
      const center = countryCenter(code);
      if (map && center && (force || !userMoved)) map.easeTo({ center,
        zoom: matchMedia("(max-width: 700px)").matches ? 0.9 : 1.7, duration: 0 });
    }
    function renderRoute() {
      if (!mapReady || !map.getSource("trip-route")) return;
      const origin = options.origin, targets = options.targets || [];
      const features = origin ? targets.filter((t) => Number.isFinite(t.lon) && Number.isFinite(t.lat)).map((t) => ({
        type: "Feature", properties: {}, geometry: { type: "LineString",
          coordinates: [[origin.lon, origin.lat], [t.lon, t.lat]] },
      })) : [];
      map.getSource("trip-route").setData({ type: "FeatureCollection", features });
      const points = [origin, ...targets].filter((p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lon));
      if (points.length === 1) map.easeTo({ center: [points[0].lon, points[0].lat], zoom: 4 });
      if (points.length > 1) {
        const bounds = new lib.LngLatBounds();
        points.forEach((p) => bounds.extend([p.lon, p.lat]));
        map.fitBounds(bounds, { padding: 65, maxZoom: 5, duration: 650 });
      }
    }
    async function legacyFallback(reason) {
      showStatus(reason || "Подробная карта недоступна.", true);
      try {
        if (!window.createLegacyTripMap) {
          await new Promise((resolve, reject) => {
            const script = node("script", { src: asset("trip-map-legacy.js") });
            script.onload = resolve; script.onerror = reject; document.head.append(script);
          });
        }
        fallback = window.createLegacyTripMap({ container, onChoose });
        fallback.setData(info, land); drawFallback(options);
      } catch (_) { showStatus("Карта недоступна. Напишите направление в чате.", true); }
    }
    function drawFallback(next) {
      fallback.draw(next);
      container.prepend(node("p", { class: "map-fallback-notice", role: "status" },
        "Подробный каталог карты недоступен. Показаны направления приложения."));
    }
    async function init() {
      try {
        loadStyle(asset("vendor/maplibre/maplibre-gl.css"));
        const [module, mapCatalog, shapes, eventData] = await Promise.all([
          import(asset("vendor/maplibre/maplibre-gl.mjs")),
          json(api("/api/map/catalog")), json(asset("countries.geojson")),
          json(asset("events.json")).catch(() => ({ events: [], checked_at: null })),
        ]);
        lib = module; catalog = mapCatalog; countries = shapes;
        events = eventData.events || []; eventChecked = eventData.checked_at || "дата неизвестна";
        map = new lib.Map({
          container: holder, center: countryCenter(manualCountry || initialCountry) || [10, 25], zoom: overviewZoom(),
          minZoom: 0.5, maxZoom: 16, attributionControl: false, cooperativeGestures: true,
          style: { version: 8,
            sources: {
              countries: { type: "geojson", data: shapes },
              "catalog-points": { type: "geojson", data: { type: "FeatureCollection", features: [] } },
              "trip-route": { type: "geojson", data: { type: "FeatureCollection", features: [] } },
            },
            layers: [
              { id: "ocean", type: "background", paint: { "background-color": "#e5f0ed" } },
              { id: "land", type: "fill", source: "countries",
                paint: { "fill-color": "#c7dad0", "fill-outline-color": "#a9c5b9" } },
              { id: "trip-route", type: "line", source: "trip-route",
                paint: { "line-color": "#3152dc", "line-width": 2, "line-dasharray": [2, 2] } },
              { id: "catalog-points", type: "circle", source: "catalog-points",
                paint: { "circle-radius": 5, "circle-color": [
                  "match", ["get", "kind"], "hotel", "#3152dc", "city", "#477b68",
                  "airport", "#a56630", "camping", "#96794c", "beach", "#dba92b", "#3152dc"],
                  "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } },
            ],
          },
        });
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("map load timeout")), 20000);
          map.once("load", () => { clearTimeout(timeout); resolve(); });
          map.once("error", (e) => { clearTimeout(timeout); reject(e.error); });
        });
        map.setProjection({ type: "globe" });
        mapReady = true;
        map.on("movestart", (event) => {
          if (event.originalEvent) { userMoved = true; closePopup(); }
          if (controller) controller.abort();
          detailSequence++;
          sequence++;
        });
        map.on("moveend", () => { renderEvents(); renderLandmarks(); schedule(); });
        map.on("click", "catalog-points", (event) => {
          const features = map.queryRenderedFeatures(event.point, { layers: ["catalog-points"] });
          if (features.length) showOverlapping(features, event.lngLat);
        });
        map.on("mouseenter", "catalog-points", () => { holder.style.cursor = "pointer"; });
        map.on("mouseleave", "catalog-points", () => { holder.style.cursor = ""; });
        fillLegacySelect(); renderEvents(); renderLandmarks(); renderRoute(); schedule();
      } catch (_) {
        if (map) { map.remove(); map = null; }
        await legacyFallback("Подробный каталог карты недоступен.");
      }
    }
    return {
      setData(catalogue, geography) {
        info = catalogue; land = geography; fillLegacySelect();
        if (!map && !fallback) init();
        else if (fallback) fallback.setData(catalogue, geography);
      },
      draw(next = {}) {
        options = next;
        if (fallback) drawFallback(next);
        else if (mapReady) renderRoute();
      },
      setCountry(code, force = false) { setCountry(code, force); },
      retry() { if (map) schedule(); },
    };
  };
})();
