/* Reusable map. The host provides the chat callback; data stays in the map API. */
(function () {
  "use strict";
  const scriptUrl = document.currentScript && document.currentScript.src;
  const staticRoot = scriptUrl ? new URL(".", scriptUrl) : new URL("/static/", location.href);
  const asset = (path) => {
    const url = new URL(path, staticRoot);
    if (!path.startsWith("vendor/")) url.searchParams.set("v", "globe-20261028-3");
    return url.href;
  };
  const ORIGIN = staticRoot.origin;
  const fmt = new Intl.NumberFormat("ru-RU");
  const KINDS = { all: "Всё на глобусе", attraction: "Достопримечательности", event: "События", city: "Города", hotel: "Размещение",
    airport: "Аэропорты", beach: "Пляжи", camping: "Кемпинги" };
  const KIND_NAMES = { city: "Населённый пункт", hotel: "Объект размещения",
    airport: "Аэропорт", beach: "Пляж", camping: "Кемпинг" };
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
    const response = await fetch(url, { signal, cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  function normalizeLon(value) {
    return ((value + 180) % 360 + 360) % 360 - 180;
  }
  function boundsFor(map) {
    const b = map.getBounds();
    const rawWest = b.getWest(), rawEast = b.getEast();
    const south = Math.max(-90, Math.min(90, b.getSouth()));
    const north = Math.max(south, Math.min(90, b.getNorth()));
    if (rawEast - rawWest >= 359.9) return { west: -180, east: 180, south, north, span: 360 };
    const west = normalizeLon(rawWest), east = normalizeLon(rawEast);
    return { west, east, south, north, span: (east - west + 360) % 360 || 360 };
  }

  window.createTripMap = function createTripMap({ container, onChoose, onFavorite, isFavorite, apiBase = ORIGIN }) {
    const api = (path) => new URL(path, apiBase).href;
    let info = null, land = null, lib = null, map = null, catalog = null, countries = null, countryNames = new Map();
    let events = [], landmarks = [], settings = {}, eventChecked = null, eventIcon = () => node("span", {"aria-hidden":"true"}, "✦");
    let options = {}, kind = "all", controller = null;
    let sequence = 0, detailSequence = 0, timer = 0, userMoved = false, manualCountry = null, initialCountry = null;
    let clusterMarkers = [], eventMarkers = [], landmarkMarkers = [], targetMarkers = [], records = new Map(), currentItems = [], visibleEvents = [], visibleLandmarks = [], listShown = 40;
    let popup = null, mapReady = false, fallback = null, loadComplete = false, three = null, threeLoading = false;
    const holder = node("div", { class: "map-canvas", "aria-label": "Глобус с местами и событиями" });
    const worldCenter = () => Array.isArray(settings.world_center) && settings.world_center.length === 2 &&
      settings.world_center.every(Number.isFinite) ? settings.world_center : [0, 0];
    const overviewZoom = () => {
      const value = settings.world_zoom?.[matchMedia("(max-width: 700px)").matches ? "mobile" : "desktop"];
      return Number.isFinite(value) ? value : 1;
    };
    const status = node("span", { class: "map-status", role: "status", "aria-live": "polite" }, "Загружаем карту…");
    const filter = node("select", { class: "map-kind", "aria-label": "Тип мест",
      onchange: (e) => { kind = e.target.value; renderLandmarks(); renderEvents(); schedule(); } },
      Object.entries(KINDS).map(([id, title]) => node("option", { value: id }, title)));
    const scope = node("button", { type: "button", class: "map-scope", onclick: () => world() }, "Весь мир");
    const zoomBy = (delta) => map && map.easeTo({zoom: Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), map.getZoom() + delta)),
      duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650, easing: (t) => 1 - Math.pow(1-t, 3)});
    const controls = node("div", { class: "map-controls" },
      node("button", { type: "button", "aria-label": "Приблизить карту", onclick: () => zoomBy(0.7) }, "+"),
      node("button", { type: "button", "aria-label": "Отдалить карту", onclick: () => zoomBy(-0.7) }, "−"));
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
    const surface = node("div", { class: "map-surface" }, holder, controls,
      node("div", {class:"globe-hint", "aria-hidden":"true"},
        node("span", {class:"globe-hint-symbol"}, "✦"),
        node("span", {}, "Вращайте глобус", node("small", {}, "Нажмите на место или событие"))));
    const head = node("div", { class: "map-head" }, node("div", { class: "map-caption" },
      node("b", {}, "Исследуйте мир"), node("small", {}, "Места и события на глобусе")),
      node("div", { class: "map-tools" }, filter, scope));
    const body = node("div", { class: "map-frame" }, head, surface,
      node("div", { class: "map-status-row" }, status,
        node("span", { class: "map-legend" }, "● места  ·  ◉ события")),
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
    function placeWithoutOverlap(marker, occupied, rect) {
      const button = marker.getElement();
      if (button.classList.contains("maplibregl-marker-covered")) return;
      const original = button.getBoundingClientRect();
      const collides = (candidate) => occupied.some((r) => candidate.left < r.right + 4 && candidate.right > r.left - 4 &&
        candidate.top < r.bottom + 4 && candidate.bottom > r.top - 4);
      // A marker must remain at its real map coordinate. When the view is
      // crowded, the item remains reachable in the text list below the map.
      for (const radius of [0]) {
        for (const degrees of radius ? [0,45,90,135,180,225,270,315] : [0]) {
          const radians = degrees * Math.PI / 180, dx = Math.round(Math.cos(radians)*radius), dy = Math.round(Math.sin(radians)*radius);
          const box = {left:original.left+dx,right:original.right+dx,top:original.top+dy,bottom:original.bottom+dy};
          if (box.left >= rect.left && box.right <= rect.right && box.top >= rect.top && box.bottom <= rect.bottom && !collides(box)) {
            marker.setOffset([dx, dy]); occupied.push(box); return;
          }
        }
      }
      // Keep a crowded group reachable in the map's text list instead of
      // placing an overlapping, partially unclickable button on the globe.
      button.hidden = true;
    }
    function onVisibleHemisphere(lon, lat) {
      if (!map || map.getProjection().type !== "globe") return true;
      const center = map.getCenter(), radians = Math.PI / 180;
      const a = center.lat * radians, b = lat * radians;
      // Omit raised models near the horizon: their enlarged silhouettes would
      // otherwise extend far outside the planet and obscure their real anchor.
      return Math.sin(a) * Math.sin(b) + Math.cos(a) * Math.cos(b) * Math.cos((lon - center.lng) * radians) > 0.55;
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
        if (onFavorite) {
          const favorite = node("button", {type:"button", class:"map-favorite", "aria-pressed":String(Boolean(isFavorite?.(point))),
            "aria-label":`В избранное: ${point.name || "место"}`, onclick:() => {
              const saved = onFavorite(point); favorite.setAttribute("aria-pressed",String(saved));
              favorite.textContent = saved ? "♥ В избранном" : "♡ В избранное";
            } }, isFavorite?.(point) ? "♥ В избранном" : "♡ В избранное");
          content.append(favorite);
        }
      } else if (point.kind === "camping") {
        content.append(node("p", { class: "map-note" }, "Условия размещения не проверены."));
      } else if (point.kind === "airport") {
        content.append(node("p", { class: "map-note" }, "Рейсы и билеты не проверены."));
      }
      content.append(node("p", { class: "map-source" }, source.name, " · ", source.details));
      const links = node("div", { class: "map-pop-links" },
        safeLink(source.url, "Источник ↗"), safeLink(point.website, "Сайт объекта ↗"));
      if (links.childNodes.length) content.append(links);
      if ((point.kind === "city" || point.kind === "hotel") && point.name) {
        content.append(node("p", { class: "map-question" }, point.kind === "hotel" ?
          "Хотите остановиться в этом отеле?" : "Хотите поехать сюда?"));
        content.append(node("button", { type: "button", class: "map-choose",
          onclick: () => { closePopup(); onChoose(point); } }, point.kind === "hotel" ? "Выбрать этот отель" : "Хочу сюда"));
      }
      return content;
    }
    async function openPoint(id, lat, lon) {
      const request = ++detailSequence;
      try {
        const point = await json(api(`/api/map/point/${encodeURIComponent(id)}`));
        if (request !== detailSequence || !map) return;
        // The click may be on the edge of a rendered circle; anchor the card
        // to the sourced point rather than the cursor's nearby coordinates.
        makePopup(point.lon, point.lat, pointContent(point));
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
        node("p", {}, event.dates), node("p", { class: "map-note" },
          `${event.location_note || "Метка показывает город."} Билеты не проверены.`),
        event.status_note ? node("p", { class: "map-note" }, event.status_note) : null,
        node("p", { class: "map-source" }, `Источник: ${event.source} · проверено ${eventChecked}`),
        node("div", { class: "map-pop-links" }, safeLink(event.url, "Источник ↗")),
        node("button", { type: "button", class: "map-choose", "data-sound":"select",
          onclick: () => { closePopup(); onChoose({ kind:"event", id:event.id, name:event.city, event:event.name,
            lat:event.lat, lon:event.lon }); } }, "Хочу на событие"));
    }
    function landmarkIcon(kind) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 32 38"); svg.setAttribute("aria-hidden", "true");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const shapes = { tower: "M16 2v5M13 8h6M15 8c-1 12-3 20-9 27m11-27c1 12 3 20 9 27M9 26h14M11 19h10M12 35c0-5 8-5 8 0M5 36h22",
        kremlin: "M3 35h26M5 35V18h22v17M8 18v-6l4-5 4 5v6M16 18v-9l4-5 4 5v9M5 23h22M9 35v-6h4v6M20 35v-6h4v6",
        spire: "M16 2v5M15 7h2v8h2v5h2v5h2v10H9V25h2v-5h2v-5h2zM7 36h18",
        clocktower:"M10 36V8h12v28M8 8h16L16 2zM13 15h6v6h-6zM6 36h20",
        colosseum:"M4 33V17q12-9 24 0v16q-12 7-24 0zM4 24q12 7 24 0M9 18v14m5-16v18m5-18v18m5-16v14",
        gate:"M6 35V12m20 23V12M3 12h26M5 8h22M8 5h16M13 13h6v10h-6z",
        pyramids:"M2 35L13 10l11 25zM16 35L24 18l7 17z",
        liberty:"M9 36h14M11 34l2-15h6l2 15M13 14a3 3 0 1 0 6 0a3 3 0 1 0-6 0M19 20l5-8V5M22 5h4" };
      path.setAttribute("d", shapes[kind] || shapes.tower); path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor");
      path.setAttribute("stroke-width", "1.8"); path.setAttribute("stroke-linecap", "round"); path.setAttribute("stroke-linejoin", "round");
      svg.append(path); return svg;
    }
    function landmarkContent(place) {
      return node("div", { class: "map-pop" },
        node("div", { class: "map-pop-kind" }, place.heritage ? place.category : "Идея для поездки"), node("strong", {}, place.name),
        node("p", {}, place.city || place.country), node("p", { class: "map-note" }, place.heritage ?
          "Условный значок. Координата объекта из списка ЮНЕСКО; вход может находиться в другом месте." :
          "Стилизованная модель у достопримечательности; масштаб увеличен."),
        node("div", { class: "map-pop-links" }, safeLink(place.url, place.heritage ? "ЮНЕСКО ↗" : "Официальный сайт ↗"),
          place.heritage ? safeLink("https://creativecommons.org/licenses/by-sa/4.0/", "CC BY-SA 4.0 ↗") : null),
        node("p", {class:"map-question"}, "Хотите посетить это место?"),
        node("button", { type: "button", class: "map-choose", "data-sound":"select", onclick: () => {
          closePopup(); onChoose({ kind:place.heritage ? "heritage" : "landmark", name:place.city || place.country,
            landmark:place.name, country:place.country, lat:place.lat, lon:place.lon });
        } }, place.city ? "Выбрать город" : "Обсудить место"));
    }
    function renderLandmarks() {
      clearMarkers(landmarkMarkers);
      visibleLandmarks = [];
      if (!map || map.getZoom() >= 10 || !["all", "attraction"].includes(kind)) {
        if (three) three.setLandmarks([]); return;
      }
      if (!three && !threeLoading) {
        threeLoading = true;
        import(asset("globe-model-layer.mjs")).then((module) => {
          if (!map) return;
          three = module.createGlobeModelLayer(map, lib); renderLandmarks(); renderEvents(); schedule();
        }).catch(() => { /* Keep the accessible 2D marker if 3D is unavailable. */ });
      }
      const models = [];
      const rect = holder.getBoundingClientRect();
      const overview = map.getZoom() < 2.8;
      const occupied = [];
      for (const place of landmarks) {
        if (place.heritage && map.getZoom() < 3) continue;
        if (!onVisibleHemisphere(place.lon, place.lat)) continue;
        const position = map.project([place.lon, place.lat]);
        if (position.x >= 0 && position.x <= rect.width && position.y >= 0 && position.y <= rect.height)
          visibleLandmarks.push(place);
        const size = overview ? 76 : 112, height = size + 23;
        const box = {left:position.x-size/2, right:position.x+size/2, top:position.y-height, bottom:position.y};
        if (box.left < 0 || box.right > rect.width || box.top < 0 || box.bottom > rect.height) continue;
        if (occupied.some((other) => box.left < other.right + 4 && box.right > other.left - 4 &&
          box.top < other.bottom + 4 && box.bottom > other.top - 4)) continue;
        occupied.push(box);
        const visual = three ? node("span", {class:"landmark-hit-area", "aria-hidden":"true"}) : landmarkIcon(place.icon);
        const label = place.city || place.name;
        const button = node("button", { class: `landmark-marker${overview ? " overview" : ""}`, type: "button", "data-sound":"select", "aria-label": `${label}: ${place.name}`,
          onclick: (event) => { event.stopPropagation(); makePopup(place.lon, place.lat, landmarkContent(place)); }
        }, visual, node("span", {class:"landmark-label"}, label));
        if (three) models.push({kind:place.icon, lon:place.lon, lat:place.lat});
        landmarkMarkers.push(new lib.Marker({ element: button, anchor: "bottom", opacityWhenCovered: 0 })
          .setLngLat([place.lon, place.lat]).addTo(map));
      }
      if (three) three.setLandmarks(models);
    }
    function renderEvents() {
      if (!map || !lib) return;
      clearMarkers(eventMarkers);
      if (!["all", "event"].includes(kind)) {
        visibleEvents = []; if (three) three.setEvents([]); renderList(); return;
      }
      const today = new Date().toISOString().slice(0, 10);
      const rect = holder.getBoundingClientRect();
      const occupied = [...targetMarkers, ...landmarkMarkers].map((marker) => marker.getElement())
        .filter((el) => getComputedStyle(el).opacity !== "0").map((el) => el.getBoundingClientRect());
      occupied.push(...[...controls.querySelectorAll("button")].map((button) => button.getBoundingClientRect()));
      const groups = [];
      const models = [];
      visibleEvents = [];
      for (const event of events) {
        if (event.end < today) continue;
        if (!onVisibleHemisphere(event.lon, event.lat)) continue;
        const pos = map.project([event.lon, event.lat]);
        if (pos.x < 22 || pos.y < 22 || pos.x > rect.width - 22 || pos.y > rect.height - 22) continue;
        visibleEvents.push(event);
        let group = groups.find((candidate) => Math.hypot(candidate.x - pos.x, candidate.y - pos.y) < 55);
        if (!group) { group = { x: pos.x, y: pos.y, events: [] }; groups.push(group); }
        group.events.push(event);
      }
      // At world scale events in neighbouring cities can overlap. Give the
      // location nearest the user's focus the visible model; the rest stay in
      // the list. Otherwise a distant city can cover the selected one.
      groups.sort((a, b) => Math.hypot(a.x - rect.width / 2, a.y - rect.height / 2) -
        Math.hypot(b.x - rect.width / 2, b.y - rect.height / 2));
      for (const { events: group } of groups) {
        group.sort((a, b) => a.start.localeCompare(b.start));
        const first = group[0];
        const button = node("button", { class: `event-marker${three ? " has-3d" : ""}`, type: "button", "data-sound":"event",
          "aria-label": group.length === 1 ? `Событие: ${first.name}, ${first.city}` : `События: ${group.length}`,
          onclick: (event) => {
            event.stopPropagation();
            if (group.length === 1) { makePopup(first.lon, first.lat, eventContent(first)); return; }
            const content = node("div", { class: "map-pop" }, node("strong", {}, "События рядом"),
              ...group.map((event) => node("button", { type: "button", class: "map-event-row",
                onclick: () => makePopup(event.lon, event.lat, eventContent(event)) },
                `${event.city} · ${event.name} · ${event.dates}`)));
            makePopup(first.lon, first.lat, content);
          } }, three ? node("span", {class:"event-hit-area", "aria-hidden":"true"}) : eventIcon(first.icon),
          group.length > 1 ? node("span", {class:"event-count"}, String(group.length)) : null);
        const marker = new lib.Marker({ element: button, anchor: three ? "bottom" : "center", opacityWhenCovered: 0 }).setLngLat([first.lon, first.lat]).addTo(map);
        eventMarkers.push(marker); placeWithoutOverlap(marker, occupied, rect);
        if (three && !button.hidden && !button.classList.contains("maplibregl-marker-covered"))
          models.push({kind:first.icon, lon:first.lon, lat:first.lat, event:true});
      }
      if (three) three.setEvents(models);
      renderList();
    }
    function renderClusters(items) {
      clearMarkers(clusterMarkers);
      // At the world scale the globe is for discovery; the full cluster list
      // is still available below and clusters appear as the user zooms in.
      if (map.getZoom() < 2.8 && kind === "all") return;
      const rect = holder.getBoundingClientRect();
      const occupied = [...eventMarkers, ...targetMarkers, ...landmarkMarkers].map((marker) => marker.getElement())
        .filter((el) => getComputedStyle(el).opacity !== "0").map((el) => el.getBoundingClientRect());
      occupied.push(...[...controls.querySelectorAll("button")].map((button) => button.getBoundingClientRect()));
      for (const item of items) {
        const pos = map.project([item.lon, item.lat]);
        if (pos.x < 28 || pos.y < 28 || pos.x > rect.width - 28 || pos.y > rect.height - 28) continue;
        const button = node("button", { type: "button", class: "cluster-marker",
          "aria-label": `Мест в группе: ${fmt.format(item.count)}. Приблизить`,
          onclick: (event) => { event.stopPropagation(); map.easeTo({ center: [item.lon, item.lat], zoom: Math.min(13, map.getZoom() + 2.1),
            duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 }); } },
          fmt.format(item.count));
        const marker = new lib.Marker({ element: button, anchor: "center", opacityWhenCovered: 0 })
          .setLngLat([item.lon, item.lat]).addTo(map);
        clusterMarkers.push(marker);
        placeWithoutOverlap(marker, occupied, rect);
      }
    }
    function renderList() {
      const query = search.value.trim().toLocaleLowerCase("ru-RU");
      const matched = currentItems.filter((item) => !query ||
        (item.name || KIND_NAMES[item.kind] || "").toLocaleLowerCase("ru-RU").includes(query));
      const matchedEvents = visibleEvents.filter((event) => !query ||
        `${event.city} ${event.name}`.toLocaleLowerCase("ru-RU").includes(query));
      const matchedLandmarks = visibleLandmarks.filter((place) => !query ||
        `${place.city || ""} ${place.country || ""} ${place.name}`.toLocaleLowerCase("ru-RU").includes(query));
      itemsList.replaceChildren(...matchedEvents.map((event) => node("button", {type:"button", class:"map-list-row",
        onclick:() => makePopup(event.lon, event.lat, eventContent(event))},
        `${event.city} · ${event.name} · ${event.dates}`, node("small", {}, "Событие"))),
        ...matchedLandmarks.map((place) => node("button", {type:"button", class:"map-list-row",
          onclick:() => makePopup(place.lon, place.lat, landmarkContent(place))},
          `${place.city || place.country} · ${place.name}`, node("small", {}, "Место"))),
        ...matched.slice(0, listShown).map((item) => {
        if (item.count != null) return node("button", { type: "button", class: "map-list-row",
          onclick: () => map.easeTo({ center: [item.lon, item.lat], zoom: Math.min(13, map.getZoom() + 2.1) }) },
          `Группа · ${fmt.format(item.count)} мест`);
        return node("button", { type: "button", class: "map-list-row",
          onclick: () => { map.jumpTo({ center: [item.lon, item.lat] }); openPoint(item.id, item.lat, item.lon); } },
          item.name || KIND_NAMES[item.kind] || "Место", node("small", {}, KIND_NAMES[item.kind] || ""));
      }));
      more.hidden = matched.length <= listShown;
      if (!matched.length && !matchedEvents.length && !matchedLandmarks.length) itemsList.append(node("p", { class: "map-empty" },
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
        if (kind === "event" || kind === "attraction") {
          clearMarkers(clusterMarkers); setPoints([]); currentItems = []; loadComplete = true;
          renderList();
          showStatus(kind === "event" ? `События в видимой части глобуса: ${visibleEvents.length}` :
            map.getZoom() >= 10 ? "Отдалите глобус, чтобы увидеть достопримечательности" :
              "Приблизьте глобус, чтобы увидеть больше мест");
          return;
        }
        if (!individual) {
          setPoints([]); currentItems = [];
          const zoom = Math.max(0, Math.min(8, Math.floor(map.getZoom()) + 2));
          const data = await json(api(`/api/map/clusters?${queryParams(bounds, { zoom: String(zoom) })}`), signal);
          if (own !== sequence) return;
          if (data.catalog_version !== catalog.catalog_version) { await reloadCatalog(); return; }
          currentItems = data.items; loadComplete = true;
          renderClusters(data.items); renderList();
          const total = data.items.reduce((sum, item) => sum + item.count, 0);
          showStatus(map.getZoom() < 2.8 && kind === "all" ? "Откройте место или событие на глобусе" :
            `${fmt.format(total)} записей в области · приблизьте группу`);
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
      const point = countryCenter(manualCountry || initialCountry) || worldCenter();
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
      clearMarkers(targetMarkers);
      for (const place of targets.filter((t) => t.name && Number.isFinite(t.lat) && Number.isFinite(t.lon))) {
        const button = node("button", {class:"target-marker", type:"button", "data-sound":"select", "aria-label":`Выбрать ${place.name}`,
          onclick:() => onChoose(place)}, node("span", {class:"target-dot", "aria-hidden":"true"}), place.name);
        targetMarkers.push(new lib.Marker({element:button, anchor:"bottom", opacityWhenCovered:0})
          .setLngLat([place.lon, place.lat]).addTo(map));
      }
      const features = origin ? targets.filter((t) => Number.isFinite(t.lon) && Number.isFinite(t.lat)).map((t) => ({
        type: "Feature", properties: {}, geometry: { type: "LineString",
          coordinates: [[origin.lon, origin.lat], [t.lon, t.lat]] },
      })) : [];
      map.getSource("trip-route").setData({ type: "FeatureCollection", features });
      const points = [origin, ...targets].filter((p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lon));
      const duration = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 850;
      if (points.length === 1) map.flyTo({ center: [points[0].lon, points[0].lat], zoom: 4, duration });
      if (points.length > 1) {
        const regional = (settings.regional_overviews || []).find((view) => targets.length > 1 &&
          targets.every((target) => target.country === view.country) && Array.isArray(view.center) &&
          view.center.length === 2 && view.center.every(Number.isFinite) && Number.isFinite(view.zoom));
        const longitudes = points.map((p) => p.lon), span = Math.max(...longitudes) - Math.min(...longitudes);
        if (regional) {
          map.flyTo({center:regional.center, zoom:Math.min(regional.zoom, overviewZoom()), duration});
        } else if (span > 65) {
          const radians = points.map((p) => p.lon * Math.PI / 180);
          const lon = Math.atan2(radians.reduce((a,v) => a + Math.sin(v), 0), radians.reduce((a,v) => a + Math.cos(v), 0)) * 180 / Math.PI;
          const lat = points.reduce((a,p) => a + p.lat, 0) / points.length;
          map.flyTo({center:[lon, lat], zoom:Math.min(1.1, overviewZoom()), duration});
        } else {
          const bounds = new lib.LngLatBounds(); points.forEach((p) => bounds.extend([p.lon, p.lat]));
          map.fitBounds(bounds, {padding:65, maxZoom:4, duration});
        }
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
        const [module, mapCatalog, shapes, eventData, landmarkData, iconModule, mapSettings, heritageData, countryData] = await Promise.all([
          import(asset("vendor/maplibre/maplibre-gl.mjs")),
          json(api("/api/map/catalog")), json(asset("countries.geojson")),
          json(asset("events.json")).catch(() => ({ events: [], checked_at: null })),
          json(asset("landmarks.json")).catch(() => ({landmarks:[]})),
          import(asset("event-icons.mjs")).catch(() => null),
          json(asset("map-settings.json")).catch(() => ({})),
          json(asset("heritage.json")).catch(() => ({sites:[]})),
          json(api("/api/map/countries")).catch(() => ({items:[]})),
        ]);
        lib = module; catalog = mapCatalog; countries = shapes;
        settings = mapSettings;
        events = eventData.events || []; eventChecked = eventData.checked_at || "дата неизвестна";
        countryNames = new Map((countryData.items || []).map((item) => [item.code,item.name]));
        landmarks = [...(landmarkData.landmarks || []), ...(heritageData.sites || []).map((item) => ({...item,heritage:true}))]
          .filter((p) => p.name && Number.isFinite(p.lat) && Number.isFinite(p.lon));
        if (iconModule) eventIcon = iconModule.eventIcon;
        map = new lib.Map({
          container: holder, center: countryCenter(manualCountry || initialCountry) || worldCenter(), zoom: overviewZoom(),
          canvasContextAttributes: {antialias: true},
          minZoom: 0.5, maxZoom: 16, attributionControl: false, cooperativeGestures: true,
          style: { version: 8,
            sources: {
              countries: { type: "geojson", data: shapes },
              "catalog-points": { type: "geojson", data: { type: "FeatureCollection", features: [] } },
              "trip-route": { type: "geojson", data: { type: "FeatureCollection", features: [] } },
            },
            layers: [
              { id: "ocean", type: "background", paint: { "background-color": "#c4dfe1" } },
              { id: "land", type: "fill", source: "countries",
                paint: { "fill-color": "#b4cfae", "fill-outline-color": "#8aaf9c" } },
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
        map.setSky({"sky-color":"#e5f0ed", "horizon-color":"#d5eae6", "fog-color":"#e5f0ed",
          "atmosphere-blend":["interpolate",["linear"],["zoom"],0,0.4,5,0.4,7,0]});
        import(asset("globe-shading.mjs")).then((module) => { if (map) module.addGlobeShading(map); }).catch(() => {});
        mapReady = true;
        map.on("movestart", (event) => {
          if (event.originalEvent) userMoved = true;
          closePopup();
          // Old markers can overlap while the camera moves; keep their visuals
          // but make only the freshly laid-out markers interactive.
          [...clusterMarkers, ...eventMarkers].forEach((marker) => { marker.getElement().inert = true; });
          if (controller) controller.abort();
          detailSequence++;
          sequence++;
        });
        map.on("moveend", () => { renderLandmarks(); renderEvents(); schedule(); });
        map.on("click", "catalog-points", (event) => {
          const features = map.queryRenderedFeatures(event.point, { layers: ["catalog-points"] });
          if (features.length) showOverlapping(features, event.lngLat);
        });
        map.on("click", "land", (event) => {
          if (map.queryRenderedFeatures(event.point, {layers:["catalog-points"]}).length) return;
          const feature=event.features?.[0], code=feature?.properties?.code;
          const name=countryNames.get(code); if (!name) return;
          makePopup(event.lngLat.lng,event.lngLat.lat,node("div", {class:"map-pop"},
            node("div", {class:"map-pop-kind"}, "Страна"), node("strong", {}, name),
            node("p", {class:"map-question"}, "Хотите поехать сюда?"),
            node("button", {type:"button",class:"map-choose",onclick:() => {
              closePopup(); onChoose({kind:"country",code,name,lat:event.lngLat.lat,lon:event.lngLat.lng});
            }}, "Хочу сюда")));
        });
        map.on("mouseenter", "catalog-points", () => { holder.style.cursor = "pointer"; });
        map.on("mouseleave", "catalog-points", () => { holder.style.cursor = ""; });
        fillLegacySelect(); renderLandmarks(); renderEvents(); renderRoute(); schedule();
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
      showPoint(point) {
        if (!map || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return;
        map.once("moveend", () => openPoint(point.id, point.lat, point.lon));
        map.flyTo({center:[point.lon,point.lat], zoom:12, duration:matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 800});
      },
      getView() { return map ? {center:map.getCenter().toArray(), zoom:map.getZoom(), projection:map.getProjection()?.type || null} : null; },
      retry() { if (map) schedule(); },
      unavailable() { showStatus("Не удалось загрузить карту. Повторите подключение.", true); },
    };
  };
})();
