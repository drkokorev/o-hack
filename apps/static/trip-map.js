/* Reusable map. The host provides the chat callback; data stays in the map API. */
(function () {
  "use strict";
  const scriptUrl = document.currentScript && document.currentScript.src;
  const staticRoot = scriptUrl ? new URL(".", scriptUrl) : new URL("/static/", location.href);
  const asset = (path) => {
    const url = new URL(path, staticRoot);
    if (!path.startsWith("vendor/")) url.searchParams.set("v", "refine-3");
    return url.href;
  };
  const ORIGIN = staticRoot.origin;
  const fmt = new Intl.NumberFormat("ru-RU");
  const KINDS = { all: "Все места", attraction: "Что посмотреть", event: "События", city: "Города", hotel: "Размещение",
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
    let events = [], landmarks = [], settings = {}, eventChecked = null;
    let options = {}, kind = "all", controller = null, resetViewPending = false, routeCameraKey=null, fittedZoom=null;
    let globeMode='earth', earthSurface=null, basemap=null, imageCredits={}, eventWindow='soon', tripContext={}, eventPeriodChosen=false;
    try { if(localStorage.getItem('odin.globe')==='atlas') globeMode='atlas'; } catch (_) {}
    const theme=()=>document.documentElement.dataset.theme==='dark'?'dark':'light';
    let sequence = 0, detailSequence = 0, timer = 0, userMoved = false, manualCountry = null, initialCountry = null;
    let clusterMarkers = [], eventMarkers = [], landmarkMarkers = [], targetMarkers = [], records = new Map(), currentItems = [], visibleEvents = [], visibleLandmarks = [];
    let popup = null, popupObserver = null, mapReady = false, earthReady = false, fallback = null, loadComplete = false, three = null, threeLoading = false;
    const holder = node("div", { class: "map-canvas", "aria-label": "Глобус с местами и событиями" });
    const worldCenter = () => Array.isArray(settings.world_center) && settings.world_center.length === 2 &&
      settings.world_center.every(Number.isFinite) ? settings.world_center : [0, 0];
    const overviewZoom = () => {
      // Fit the complete sphere to the available surface, including short laptops.
      const width = holder?.clientWidth || container.clientWidth || 600;
      const height = holder?.clientHeight || 500;
      return Math.max(-.3, Math.min(2, Math.log2(Math.min(width - 64, height - 76) / 145)));
    };
    const status = node("span", { class: "map-status", role: "status", "aria-live": "polite" }, "Загружаем карту…");
    const filter = node("select", { class: "map-kind", "aria-label": "Тип мест",
      onchange: (e) => { kind = e.target.value; renderFeatured(); renderLandmarks(); renderEvents(); schedule(); } },
      Object.entries(KINDS).map(([id, title]) => node("option", { value: id }, title)));
    const modeSwitch=node('div',{class:'globe-modes',role:'group','aria-label':'Вид глобуса'},
      ...[['earth','Географическая'],['atlas','Дизайнерская']].map(([id,label])=>node('button',{type:'button','data-globe-mode':id,'aria-pressed':globeMode===id,onclick:()=>setGlobeMode(id)},label)));
    const eventPeriod=node('select',{class:'map-event-period','aria-label':'Когда проходят события',onchange:e=>{eventPeriodChosen=true;eventWindow=e.target.value;renderFeatured();renderLandmarks();renderEvents();schedule();}},
      node('option',{value:'trip',disabled:true},'Для вашей поездки'),node('option',{value:'soon',selected:true},'Ближайшие 3 месяца'),node('option',{value:'all'},'Весь календарь'));
    const featuredList=node('div',{class:'event-discovery-list'});
    const featured=node('section',{class:'event-discovery','aria-label':'Поводы поехать',hidden:true},
      node('div',{class:'event-discovery-head'},node('strong',{},'Поводы поехать'),eventPeriod),featuredList);
    function setGlobeMode(value) {
      globeMode=value;surface.dataset.globe=value;
      try {localStorage.setItem('odin.globe',value);} catch (_) {}
      for(const button of modeSwitch.children)button.setAttribute('aria-pressed',String(button.dataset.globeMode===value));
      if(map){earthSurface?.setStyle(value==='atlas'?'map':'satellite');basemap?.set(theme(),globeMode);renderGeography();map.triggerRepaint();}
    }
    const scope = node("button", { type: "button", class: "map-scope", hidden:true, 'aria-label':'К глобусу',title:'К глобусу', onclick: () => world() }, window.odinIcon('globe'));
    const zoomBy = (delta) => map && map.easeTo({zoom: Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), map.getZoom() + delta)),
      duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650, easing: (t) => 1 - Math.pow(1-t, 3)});
    const controls = node("div", { class: "map-controls" },
      node("button", { type: "button", "aria-label": "Приблизить карту", onclick: () => zoomBy(0.7) }, window.odinIcon("plus")),
      node("button", { type: "button", "aria-label": "Отдалить карту", onclick: () => zoomBy(-0.7) }, window.odinIcon("minus")),scope);
    const detailList = node("div", { class: "map-choice", hidden: true, role: "region",
      "aria-label": "Несколько объектов рядом" });
    const footer = node("div", { class: "map-footer" },
      node("div", {class:"map-credits"}, node("span", {}, "Открытые данные · наличие не проверено"),
        node("details", {}, node("summary", {}, "Источники изображения и моделей"),
          node("p", {}, "Поверхность Земли: ", safeLink("https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/", "NASA Earth Observatory, октябрь 2004"), "."),
          node("p", {}, "32 архитектурные и природные миниатюры созданы для проекта. Модели стилизованы, масштаб увеличен. ",
            safeLink(asset("models/landmarks/manifest.json"), "Состав коллекции")),
          node("p", {}, "Фотографии событий или их городов: автор и лицензия указаны в карточке."))));
    const hintTitle=node("span", {}, "Вращайте глобус"),hintDetail=node("small", {}, "Нажмите на место или событие");
    const surface = node("div", { class: "map-surface" }, holder, controls,
      node("div", {class:"globe-hint", "aria-hidden":"true"},
        node("span", {class:"globe-hint-symbol"}, "✦"),node("span", {},hintTitle,hintDetail)));
    function updateHint() {
      const detailed=map && map.getZoom()>=6;
      surface.classList.toggle("map-detailed",Boolean(detailed));
      hintTitle.textContent=detailed ? "Исследуйте город" : "Вращайте глобус";
      hintDetail.textContent=detailed ? "Выберите видимую метку" : "Приближайте, чтобы открыть больше мест";
    }
    const head = node("div", { class: "map-head" }, node("div", { class: "map-caption" },
      node("b", {}, "Исследуйте мир"), node("small", {}, "Крупные места — сразу, остальные — при приближении")),
      modeSwitch, node("div", { class: "map-tools" }, filter));
    const body = node("div", { class: "map-frame" }, head, surface,
      node("div", { class: "map-status-row" }, status,
        node("span", { class: "map-legend" }, "Места рядом объединены · все объекты в списке ниже")),
      detailList,featured);
    document.getElementById("map-source-details")?.replaceChildren(footer);
    surface.dataset.globe=globeMode;
    const mapNotice=node('button',{type:'button',class:'map-tiles-notice',hidden:true,onclick:()=>{map?.triggerRepaint();basemap?.set(theme(),globeMode);}},'Улицы не загрузились. Приблизьте ещё раз или проверьте сеть.');
    surface.append(mapNotice);
    container.classList.add("trip-map");
    container.replaceChildren(body);
    // Size the globe from the free space, not from the current booking stage.
    const sizeSurface=()=>{
      if(!container.clientWidth)return;
      const reserved=(document.querySelector('.quiet-footer')?.offsetHeight||0)+(document.querySelector('.panel-navigation')?.offsetHeight||0)+featured.offsetHeight+24;
      const available=innerHeight-(surface.getBoundingClientRect().top+scrollY)-reserved;
      const height=Math.round(Math.max(matchMedia('(max-width:900px)').matches?300:320,Math.min(720,available)));
      if(surface.style.height!==`${height}px`)surface.style.height=`${height}px`;
    };
    const layoutObserver=new ResizeObserver(sizeSurface);
    [head,featured,document.getElementById('head'),document.getElementById('journey'),document.querySelector('header.top'),document.querySelector('.quiet-footer')].filter(Boolean).forEach(el=>layoutObserver.observe(el));
    window.addEventListener('resize',sizeSurface);sizeSurface();

    function showStatus(text, error = false) {
      status.textContent = error || /первые 2 000|не загруз|недоступ/i.test(text) ? text : "";
      status.classList.toggle("error", error);
    }
    function clearMarkers(markers) {
      for (const marker of markers) marker.remove();
      markers.length = 0;
    }
    function visualBounds(element) {
      const box=element.getBoundingClientRect();
      const result={left:box.left,right:box.right,top:box.top,bottom:box.bottom};
      for (const item of element.querySelectorAll('.landmark-label,.landmark-count,.event-label,.event-count')) {
        if (item.hidden || getComputedStyle(item).display==='none') continue;
        const child=item.getBoundingClientRect();
        if (!child.width || !child.height) continue;
        result.left=Math.min(result.left,child.left);result.right=Math.max(result.right,child.right);
        result.top=Math.min(result.top,child.top);result.bottom=Math.max(result.bottom,child.bottom);
      }
      return result;
    }
    function placeWithoutOverlap(marker, occupied, rect) {
      const button = marker.getElement();
      if (button.classList.contains("maplibregl-marker-covered")) {button.hidden=true;return;}
      const original = visualBounds(button);
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
      if (!map || map.getProjection()?.type !== "globe") return true;
      const center = map.getCenter(), radians = Math.PI / 180;
      const a = center.lat * radians, b = lat * radians;
      // Items only leave as they approach the planet's far side.
      return Math.sin(a) * Math.sin(b) + Math.cos(a) * Math.cos(b) * Math.cos((lon - center.lng) * radians) > 0.60;
    }
    function closePopup() {
      if (popupObserver) popupObserver.disconnect();popupObserver=null;
      if (popup) popup.remove();popup=null;
    }
    function makePopup(lon, lat, content) {
      closePopup();
      const position=map.project([lon,lat]);
      const anchor=holder.clientWidth<650 ? 'center' : position.x<holder.clientWidth/2 ? 'left' : 'right';
      const card=new lib.Popup({closeButton:true,closeOnClick:false,focusAfterOpen:false,anchor,
        maxWidth:`${Math.min(310,Math.max(180,holder.clientWidth-24))}px`})
        .setLngLat([lon,lat]).setDOMContent(content).addTo(map);
      popup=card;
      card.on('close',()=>{if (popup===card) {if (popupObserver) popupObserver.disconnect();popupObserver=null;popup=null;}});
      const container=card.getElement(),box=container.querySelector('.maplibregl-popup-content');
      if (box) {box.style.maxHeight=`${Math.max(160,holder.clientHeight-24)}px`;box.style.overflowY='auto';}
      function keepInMap() {
        if (popup!==card) return;
        card.setOffset([0,0]);
        const bounds=holder.getBoundingClientRect(),current=container.getBoundingClientRect(),gap=8;
        const dx=current.left<bounds.left+gap ? bounds.left+gap-current.left :
          current.right>bounds.right-gap ? bounds.right-gap-current.right : 0;
        const dy=current.top<bounds.top+gap ? bounds.top+gap-current.top :
          current.bottom>bounds.bottom-gap ? bounds.bottom-gap-current.bottom : 0;
        if (dx || dy) card.setOffset([dx,dy]);
      }
      keepInMap();
      if (box && typeof ResizeObserver!=='undefined') {
        popupObserver=new ResizeObserver(()=>requestAnimationFrame(keepInMap));popupObserver.observe(box);
      }
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
              favorite.replaceChildren(window.odinIcon("heart",saved),saved ? " В избранном" : " В избранное");
            } }, window.odinIcon("heart",Boolean(isFavorite?.(point))),isFavorite?.(point) ? " В избранном" : " В избранное");
          content.append(favorite);
        }
      } else if (point.kind === "camping") {
        content.append(node("p", { class: "map-note" }, "Условия размещения не проверены."));
      } else if (point.kind === "airport") {
        content.append(node("p", { class: "map-note" }, "Аэропорт отмечен как ориентир. Отдельный выбор аэропорта пока не поддерживается; город вылета можно изменить в условиях поездки."));
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
    function eventPhoto(event) {
      // Thematic covers carry an explicit label; never imply a photo of a future edition.
      if(event.image?.src && event.image?.credit && event.image?.page &&
        /^\/static\//.test(event.image.src)) return {...event.image,kind:event.image.kind||'event'};
      const city=(info?.places||[]).find(p=>p.name===event.city);
      const key=city && `dest/${city.id}.jpg`,credit=key && imageCredits[key];
      return credit ? {src:asset(`img/${key}`),credit:`${credit.author} · ${credit.license}`,page:credit.page,kind:'city'} : null;
    }
    function eventName(event) {return event.short_name || event.name.replace(/^Формула-1: Гран-при · /,'F1 · ').replace(/^Фестиваль /,'');}
    function monogram(event) {return eventName(event).split(/\s+/).slice(0,2).map(x=>x[0]).join('').toLocaleUpperCase('ru-RU');}
    function eventContent(event) {
      const photo=eventPhoto(event);
      const content=node('div',{class:'map-pop event-story'},
        photo ? node('figure',{class:'event-photo'},node('img',{src:photo.src,alt:photo.alt||(photo.kind==='city'?`Город события — ${event.city}`:event.name),decoding:'async',onerror:e=>{e.target.parentElement.hidden=true;}}),
          node('figcaption',{},photo.kind==='theme'?'Тематическое фото':photo.kind==='city'?'Город события':'Фото события')) : node('div',{class:'event-poster','aria-hidden':'true'},node('span',{},monogram(event)),node('small',{},event.category)),
        node('div',{class:'map-pop-kind'},event.category),node('strong',{},event.name),
        node('p',{class:'event-when'},event.dates),node('p',{class:'event-location'},`${event.city}, ${event.country}`),
        node('p',{class:'event-story-copy'},event.description || ({
          race:'Добавьте гоночный уик-энд к поездке и оставьте время на сам город.',
          sport:'Совместите поездку с большим спортивным событием.',
          music:'Постройте поездку вокруг музыки, а между выступлениями откройте город.',
          film:'Совместите кинопрограмму с прогулками по городу.',
          art:'Выберите искусство как повод познакомиться с городом.',
          culture:'Добавьте событие к прогулкам и знакомству с городом.'
        }[event.icon] || 'Сделайте это событие поводом для небольшой поездки.')),
        node('button',{type:'button',class:'map-choose',onclick:()=>{closePopup();onChoose({kind:'event',id:event.id,name:event.city,event:event.name,start:event.start,end:event.end,lat:event.lat,lon:event.lon});}},'Хочу на событие'),
        node('details',{class:'event-source'},node('summary',{},'Место, билеты и источник'),
          node('p',{},`${event.location_note || 'Метка показывает город, не вход на площадку.'} Билеты не проверены.`),
          event.status_note ? node('p',{},event.status_note):null,
          node('p',{},`Проверено ${eventChecked} · `,safeLink(event.url,event.source)),
          photo ? node('p',{},'Фото: ',safeLink(photo.page,photo.credit),photo.license_url?[' · ',safeLink(photo.license_url,'Лицензия')]:null,' · Кадрирование при показе.'):null));
      return content;
    }
    function eventMatches(event){
      const now=new Date(),today=now.toISOString().slice(0,10),horizon=new Date(now.getTime()+92*86400000).toISOString().slice(0,10);
      if(event.end<today)return false;
      if(eventWindow==='soon')return event.start<=horizon;
      if(eventWindow==='trip'&&tripContext.date_from){
        return event.end>=tripContext.date_from&&event.start<=(tripContext.date_to||tripContext.date_from)&&(!tripContext.destination||event.city===tripContext.destination);
      }
      return true;
    }
    const eventOrder=(a,b)=>(b.priority||0)-(a.priority||0)||a.start.localeCompare(b.start)||a.id.localeCompare(b.id);
    function openEvent(event){
      if(!mapReady)return;
      closePopup();
      map.once('moveend',()=>makePopup(event.lon,event.lat,eventContent(event)));
      map.flyTo({center:[event.lon,event.lat],zoom:Math.max(overviewZoom(),3.2),duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:750});
    }
    function renderFeatured(){
      featured.hidden=!events.length||!['all','event'].includes(kind);
      const eligible=events.filter(eventMatches).sort(eventOrder),cities=new Set(),picks=[];
      for(const event of eligible){if(!cities.has(event.city)){picks.push(event);cities.add(event.city);}if(picks.length===3)break;}
      featuredList.replaceChildren(...picks.map(event=>node('button',{type:'button',class:'event-teaser','data-event-id':event.id,onclick:()=>openEvent(event)},
        node('img',{src:eventPhoto(event)?.src,alt:'',decoding:'async'}),node('span',{},node('b',{},eventName(event)),node('small',{},event.city),node('small',{},event.dates)))));
      if(!picks.length)featuredList.append(node('p',{class:'event-empty'},eventWindow==='trip'?'На эти даты в выбранном городе пока нет событий. Можно открыть весь календарь.':'В этой подборке пока нет ближайших событий. Откройте весь календарь.'));
      requestAnimationFrame(sizeSurface);
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
        liberty:"M9 36h14M11 34l2-15h6l2 15M13 14a3 3 0 1 0 6 0a3 3 0 1 0-6 0M19 20l5-8V5M22 5h4",
        heritage_culture:"M4 14h24L16 7zM6 15v14M12 15v14M20 15v14M26 15v14M3 31h26",
        heritage_nature:"M3 29 12 12l6 10 4-7 7 14zM9 19l3-3 3 3M19 22l3-3 3 3" };
      path.setAttribute("d", shapes[kind] || shapes.tower); path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor");
      path.setAttribute("stroke-width", "1.8"); path.setAttribute("stroke-linecap", "round"); path.setAttribute("stroke-linejoin", "round");
      svg.append(path); return svg;
    }
    function focusOn(lon,lat) {
      if (!map) return;
      closePopup();map.easeTo({center:[lon,lat],zoom:Math.max(5,map.getZoom()),
        duration:matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650});
    }
    function landmarkContent(place, grouped = [], nearbyEvents = []) {
      const content = node("div", { class: "map-pop" },
        node("div", { class: "map-pop-kind" }, place.heritage ? place.category : "Идея для поездки"), node("strong", {}, place.name),
        node("p", {}, place.city || place.country), node("p", { class: "map-note" }, place.heritage ?
          "Условный значок. Координата объекта из списка ЮНЕСКО; вход может находиться в другом месте." :
          "Стилизованная миниатюра; масштаб увеличен, координаты приблизительные."),
        node("div", { class: "map-pop-links" }, safeLink(place.url, place.heritage ? "ЮНЕСКО ↗" : "Официальный сайт ↗"),
          place.heritage ? safeLink("https://creativecommons.org/licenses/by-sa/4.0/", "CC BY-SA 4.0 ↗") : null),
        node("p", {class:"map-question"}, "Хотите посетить это место?"),
        node("button", { type: "button", class: "map-choose", onclick: () => {
          closePopup(); onChoose({ kind:place.heritage ? "heritage" : "landmark", name:place.city || place.country,
            landmark:place.name, country:place.country, lat:place.lat, lon:place.lon });
        } }, place.city ? "Хочу сюда" : "Обсудить место"),
        node("button", {type:"button",class:"map-inspect",onclick:()=>focusOn(place.lon,place.lat)}, "Посмотреть ближе"));
      const others=grouped.filter((item)=>item!==place);
      if (others.length) content.append(node("details", {class:"map-nearby"},
        node("summary", {}, `Ещё мест на этом участке: ${others.length}`),
        ...others.map((item)=>node("button", {type:"button",class:"map-event-row",
          onclick:()=>makePopup(item.lon,item.lat,landmarkContent(item))}, item.city ? `${item.city} · ${item.name}` : item.name))));
      if (nearbyEvents.length) content.append(node("details", {class:"map-nearby"},
        node("summary", {}, `События на этом участке: ${nearbyEvents.length}`),
        ...nearbyEvents.map((event)=>node("button", {type:"button",class:"map-event-row",
          onclick:()=>makePopup(event.lon,event.lat,eventContent(event))}, `${event.city} · ${event.name} · ${event.dates}`))));
      return content;
    }
    function updateLandmarkBadge(marker) {
      const state=marker._odinState,button=marker.getElement();
      const count=state.group.length-1+state.events.length;
      const badge=button.querySelector('.landmark-count');badge.hidden=count===0;badge.textContent=count ? `+${count}` : '';
      button.title=count ? `Ещё объектов на участке: ${count}` : '';
    }
    function refreshModelStates() {
      for (const marker of [...landmarkMarkers,...eventMarkers]) {
        const el=marker.getElement(), model=marker._odinModel;
        const state=three && model ? three.getModelState(model) : 'loading';
        el.classList.toggle('model-pending',el.classList.contains('heritage-marker') || state==='loading' || state==='failed');
        if (state==='failed') el.title='Модель не загрузилась; место доступно по значку';
      }
    }
    function renderLandmarks() {
      visibleLandmarks = [];
      if (!map || !["all", "attraction"].includes(kind)) {
        clearMarkers(landmarkMarkers); if (three) three.setLandmarks([]); return;
      }
      if (!three && !threeLoading) {
        threeLoading = true;
        import(asset("globe-model-layer.mjs")).then((module) => {
          if (!map) return;
          three = module.createGlobeModelLayer(map, lib, refreshModelStates, landmarks.filter(p=>!p.heritage).map(p=>p.icon));
          renderLandmarks(); renderEvents(); schedule();
        }).catch(() => { /* Accessible markers remain if 3D is unavailable. */ });
      }
      const models=[],rect=holder.getBoundingClientRect(), occupied=[], selected=[];
      const controlBoxes=[...controls.children].filter(el=>!el.hidden).map(el=>el.getBoundingClientRect());
      const landmarkCap=map.getZoom()<3 ? 4 : map.getZoom()<6 ? 7 : 12;
      const eventAnchors=kind==='all' ? events.filter(e=>eventMatches(e)&&onVisibleHemisphere(e.lon,e.lat)).sort(eventOrder).slice(0,24).map(e=>map.project([e.lon,e.lat])) : [];
      const importance=place=>{const p=map.project([place.lon,place.lat]);return (place.priority||0)+(map.getZoom()>=3?Math.max(0,180-Math.hypot(p.x-rect.width/2,p.y-rect.height/2)*8):0);};
      for (const place of [...landmarks].sort((a,b)=>importance(b)-importance(a))) {
        if (!onVisibleHemisphere(place.lon, place.lat)) continue;
        const position=map.project([place.lon,place.lat]);
        if (position.x<0 || position.x>rect.width || position.y<0 || position.y>rect.height) continue;
        visibleLandmarks.push(place);
        // Small heritage markers appear only when their surroundings are legible.
        if (place.heritage && map.getZoom()<3) continue;
        const size=place.heritage ? 38 : rect.width<500 ? 58 : 68;
        const box={left:position.x-size/2,right:position.x+size/2,top:position.y-size,bottom:position.y+(place.heritage ? 4 : 28)};
        if(controlBoxes.some(b=>box.left+rect.left<b.right+6&&box.right+rect.left>b.left-6&&box.top+rect.top<b.bottom+6&&box.bottom+rect.top>b.top-6))continue;
        const overlapping=occupied.find((item)=>box.left<item.box.right+4 && box.right>item.box.left-4 &&
          box.top<item.box.bottom+4 && box.bottom>item.box.top-4);
        if (overlapping) {overlapping.group.push(place);continue;}
        if (kind==='all' && selected.length>=2 && eventAnchors.some(p=>Math.hypot(position.x-p.x,position.y-p.y)<90)) continue;
        if(selected.length>=landmarkCap) continue;
        const item={place,group:[place],box};occupied.push(item);selected.push(item);
      }
      const previous=new Map(landmarkMarkers.map((marker)=>[marker._odinKey,marker]));
      const next=[];
      for (const item of selected) {
        const place=item.place,key=`${place.icon}:${place.lon}:${place.lat}:${place.name}`;
        let marker=previous.get(key);
        if (!marker) {
          const state={place,group:item.group,events:[]};
          const visual=node("span", {class:"landmark-hit-area", "aria-hidden":"true"},
            node("span", {class:"landmark-fallback"}, landmarkIcon(place.icon)));
          const button=node("button", {class:"landmark-marker model-pending",type:"button",
            onclick:(event)=>{event.stopPropagation();makePopup(state.place.lon,state.place.lat,landmarkContent(state.place,state.group,state.events));}},
            visual,node("span", {class:"landmark-label"}),node("span", {class:"landmark-count",hidden:true}));
          marker=new lib.Marker({element:button,anchor:"bottom",opacityWhenCovered:0}).setLngLat([place.lon,place.lat]).addTo(map);
          marker._odinKey=key;marker._odinState=state;marker._odinModel=place.icon;
        } else {previous.delete(key);marker._odinState.place=place;marker._odinState.group=item.group;marker._odinState.events=[];}
        const button=marker.getElement(),label=place.city || place.name;
        button.classList.toggle('heritage-marker',Boolean(place.heritage));
        button.setAttribute("aria-label",place.heritage ? place.name : `${label}: ${place.name}`);
        button.querySelector('.landmark-label').textContent=label;
        updateLandmarkBadge(marker);
        button.hidden=button.classList.contains('maplibregl-marker-covered');button.inert=button.hidden || map.isMoving();
        next.push(marker);if (!place.heritage && !button.hidden) models.push({kind:place.icon,lon:place.lon,lat:place.lat});
      }
      for (const marker of previous.values()) marker.remove();
      landmarkMarkers=next;
      if (three) three.setLandmarks(models);
      refreshModelStates();
    }
    function renderEvents() {
      if (!map || !lib) return;
      for(const marker of landmarkMarkers){marker._odinState.events=[];updateLandmarkBadge(marker);}
      if(!['all','event'].includes(kind)){clearMarkers(eventMarkers);visibleEvents=[];return;}
      const rect=holder.getBoundingClientRect(),zoom=map.getZoom();
      const occupied=[...targetMarkers,...landmarkMarkers].map(m=>m.getElement()).filter(el=>!el.hidden).map(visualBounds);
      occupied.push(...[...controls.children].map(b=>b.getBoundingClientRect()));
      const groups=[];visibleEvents=[];
      for(const event of events){
        if(!eventMatches(event) || !onVisibleHemisphere(event.lon,event.lat))continue;
        const pos=map.project([event.lon,event.lat]);
        if(pos.x<24||pos.y<50||pos.x>rect.width-24||pos.y>rect.height-55)continue;
        visibleEvents.push(event);
        let group=groups.find(g=>Math.hypot(g.x-pos.x,g.y-pos.y)<(zoom<3?64:zoom<6?52:36));
        if(!group){group={x:pos.x,y:pos.y,events:[]};groups.push(group);}
        group.events.push(event);
      }
      for(const group of groups)group.events.sort(eventOrder);
      groups.sort((a,b)=>eventOrder(a.events[0],b.events[0]));
      const cap=zoom<3? (rect.width<500?3:5):zoom<6?8:12;
      const previous=new Map(eventMarkers.map(m=>[m._odinKey,m])),next=[];
      for(const entry of groups){
        if(next.filter(m=>!m.getElement().hidden).length>=cap)break;
        const first=entry.events[0],key=first.id;let marker=previous.get(key);
        if(!marker){
          const state={events:entry.events};
          const photo=eventPhoto(first);
          const button=node('button',{class:'event-marker event-medallion',type:'button',onclick:e=>{
            e.stopPropagation();if(map.isMoving())return;
            const group=state.events,lead=group[0];
            if(group.length===1){makePopup(lead.lon,lead.lat,eventContent(lead));return;}
            const content=node('div',{class:'map-pop event-group'},node('div',{class:'map-pop-kind'},`${group.length} событий рядом`),node('strong',{},'Повод для поездки'),
              node('button',{type:'button',class:'map-inspect',onclick:()=>{closePopup();map.easeTo({center:[lead.lon,lead.lat],zoom:Math.min(13,map.getZoom()+2),duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:650});}},'Приблизить события'),
              ...group.slice(0,3).map(ev=>node('button',{type:'button',class:'map-event-row',onclick:()=>makePopup(ev.lon,ev.lat,eventContent(ev))},node('b',{},eventName(ev)),node('small',{},`${ev.city} · ${ev.dates}`))),
              group.length>3 ? node('details',{class:'event-source'},node('summary',{},`Ещё событий: ${group.length-3}`),...group.slice(3).map(ev=>node('button',{type:'button',class:'map-event-row',onclick:()=>makePopup(ev.lon,ev.lat,eventContent(ev))},node('b',{},eventName(ev)),node('small',{},ev.dates)))) : null);
            makePopup(lead.lon,lead.lat,content);
          }},node('span',{class:'event-portrait','aria-hidden':'true'},node('span',{class:'event-monogram'},monogram(first)),photo?node('img',{src:photo.src,alt:'',decoding:'async',onerror:e=>e.target.remove()}):null),
          node('span',{class:'event-count',hidden:true}),node('span',{class:'event-label'},eventName(first)));
          marker=new lib.Marker({element:button,anchor:'bottom',opacityWhenCovered:0}).setLngLat([first.lon,first.lat]).addTo(map);
          marker._odinKey=key;marker._odinState=state;
        }else{previous.delete(key);marker._odinState.events=entry.events;}
        const button=marker.getElement();button.hidden=false;
        button.setAttribute('aria-label',entry.events.length>1?`${first.city}: ${entry.events.length} событий, ${eventName(first)}`:`Событие: ${first.name}, ${first.city}`);
        const count=button.querySelector('.event-count');count.hidden=entry.events.length===1;count.textContent='+'+(entry.events.length-1);
        button.hidden=true;button.inert=true;next.push(marker);
      }
      for(const marker of previous.values())marker.remove();eventMarkers=next;
      // MapLibre positions a new DOM marker on the next render. Measure after it,
      // otherwise an initially unpositioned label is incorrectly hidden forever.
      requestAnimationFrame(()=>requestAnimationFrame(()=>{
        if(map.isMoving() || eventMarkers!==next)return;
        const taken=[...targetMarkers,...landmarkMarkers].map(m=>m.getElement()).filter(el=>!el.hidden).map(visualBounds);
        taken.push(...[...controls.children].map(b=>b.getBoundingClientRect()));
        const area=holder.getBoundingClientRect();
        for(const marker of next){const el=marker.getElement();el.hidden=false;placeWithoutOverlap(marker,taken,area);el.inert=el.hidden;}
        renderGeography();
      }));
    }
    const geography = [
      ['Европа',15,54,false],['Азия',95,46,false],['Африка',20,0,false],
      ['Северная Америка',-103,45,false],['Южная Америка',-60,-18,false],['Австралия',134,-25,false],
      ['Тихий океан',-150,5,true],['Атлантический океан',-35,8,true],['Индийский океан',78,-23,true]
    ];
    let geographyMarkers=[];
    function renderGeography() {
      if(!map || !lib)return;
      if(!geographyMarkers.length)geographyMarkers=geography.map(([name,lon,lat,ocean])=>new lib.Marker({element:node('span',{class:'globe-geography-label'+(ocean?' ocean-label':''),'aria-hidden':'true'},name),anchor:'center',opacityWhenCovered:0}).setLngLat([lon,lat]).addTo(map));
      const rect=holder.getBoundingClientRect();
      const occupied=[...landmarkMarkers,...eventMarkers,...clusterMarkers,...targetMarkers].map(m=>m.getElement()).filter(e=>!e.hidden).map(visualBounds);
      for(const marker of geographyMarkers){
        const el=marker.getElement(), p=marker.getLngLat();
        el.hidden=globeMode!=='atlas'||map.getZoom()>3.2||map.isMoving()||!onVisibleHemisphere(p.lng,p.lat);
        if(el.hidden)continue;
        const center=map.getCenter(),r=Math.PI/180;
        const facing=Math.sin(center.lat*r)*Math.sin(p.lat*r)+Math.cos(center.lat*r)*Math.cos(p.lat*r)*Math.cos((p.lng-center.lng)*r);
        if(facing<(el.textContent.length>14?.76:.65)){el.hidden=true;continue;}
        requestAnimationFrame(()=>{
          if(map.isMoving()||globeMode!=='atlas')return;
          el.hidden=false;
          placeWithoutOverlap(marker,occupied,{left:rect.left+22,right:rect.right-22,top:rect.top+24,bottom:rect.bottom-50});
        });
      }
    }
    let expansion=null, expansionOverlay=null, expansionTimer=0;
    function clearExpansion(){if(expansionOverlay)expansionOverlay.remove();expansionOverlay=null;clearTimeout(expansionTimer);}
    function expandGroup(item){
      clearExpansion();closePopup();
      expansion={lon:item.lon,lat:item.lat,bounds:item.cellBounds,count:item.count};
      map.easeTo({center:[item.lon,item.lat],zoom:Math.min(13,map.getZoom()+2.1),duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:700,easing:t=>1-Math.pow(1-t,3)});
    }
    function revealExpansion(items){
      if(!expansion)return;
      const parent=expansion;expansion=null;
      if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
      const area=holder.getBoundingClientRect(),from=map.project([parent.lon,parent.lat]);
      const children=items.filter(item=>!parent.bounds||(item.lon>=parent.bounds[0]&&item.lon<=parent.bounds[2]&&item.lat>=parent.bounds[1]&&item.lat<=parent.bounds[3]))
        .map(item=>map.project([item.lon,item.lat])).filter(p=>p.x>20&&p.y>20&&p.x<area.width-20&&p.y<area.height-30).slice(0,16);
      if(!children.length)return;
      clearExpansion();
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('cluster-expansion');svg.setAttribute('viewBox',`0 0 ${area.width} ${area.height}`);svg.setAttribute('aria-hidden','true');
      const shape=(type,attrs)=>{const el=document.createElementNS(svg.namespaceURI,type);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,String(value));svg.append(el);return el;};
      shape('circle',{cx:from.x,cy:from.y,r:18,class:'cluster-origin-ring'}).animate([{opacity:.8},{opacity:0,r:32}],{duration:700,fill:'forwards'});
      children.forEach((to,i)=>{
        const length=Math.hypot(to.x-from.x,to.y-from.y),line=shape('line',{x1:from.x,y1:from.y,x2:to.x,y2:to.y});
        line.style.strokeDasharray=String(length);line.animate([{strokeDashoffset:length,opacity:.65},{strokeDashoffset:0,opacity:.65},{strokeDashoffset:0,opacity:0}],{duration:1050,delay:i*18,fill:'both'});
        const dot=shape('circle',{cx:to.x,cy:to.y,r:7});dot.animate([{opacity:0},{opacity:.85,offset:.35},{opacity:0}],{duration:1100,delay:i*18,fill:'both'});
      });
      holder.append(svg);expansionOverlay=svg;expansionTimer=setTimeout(clearExpansion,1500);
    }
    function renderClusters(items) {
      clearMarkers(clusterMarkers);
      // At world scale prefer a few discovery markers; show groups on approach.
      if (map.getZoom() < 2.8 && kind === "all") return;
      const rect = holder.getBoundingClientRect();
      const occupied = [...eventMarkers, ...targetMarkers, ...landmarkMarkers].map((marker) => marker.getElement())
        .filter((el) => !el.hidden && getComputedStyle(el).opacity !== "0").map(visualBounds);
      occupied.push(...[...controls.querySelectorAll("button")].map((button) => button.getBoundingClientRect()));
      for (const item of items) {
        if(!onVisibleHemisphere(item.lon,item.lat)||clusterMarkers.length>=24) continue;
        const pos = map.project([item.lon, item.lat]);
        if (pos.x < 28 || pos.y < 28 || pos.x > rect.width - 28 || pos.y > rect.height - 28) continue;
        const button = node("button", { type: "button", class: "cluster-marker",
          "aria-label": item.count===1 ? "Открыть место" : `Мест в группе: ${fmt.format(item.count)}. Приблизить`,
          onclick: (event) => { event.stopPropagation(); if(!map.isMoving()){if(item.count===1)openPoint(item.representative_id,item.lat,item.lon);else expandGroup(item);} } },
          fmt.format(item.count));
        button.classList.toggle("singleton",item.count===1);
        const marker = new lib.Marker({ element: button, anchor: "center", opacityWhenCovered: 0 })
          .setLngLat([item.lon, item.lat]).addTo(map);
        marker._odinItem=item;button.hidden=true;button.inert=true;clusterMarkers.push(marker);
      }
      const pending=clusterMarkers;
      requestAnimationFrame(()=>requestAnimationFrame(()=>{
        if(map.isMoving()||clusterMarkers!==pending)return;
        const taken=[...eventMarkers,...targetMarkers,...landmarkMarkers].map(m=>m.getElement()).filter(e=>!e.hidden).map(visualBounds);
        taken.push(...[...controls.children].map(e=>e.getBoundingClientRect()));
        const area=holder.getBoundingClientRect();
        for(const marker of pending){const el=marker.getElement();el.hidden=false;placeWithoutOverlap(marker,taken,area);el.inert=el.hidden;}
        renderGeography();revealExpansion(pending.filter(m=>!m.getElement().hidden).map(m=>m._odinItem));
      }));
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
      detailList.hidden = true; loadComplete = false;
      showStatus("Загружаем места…");
      try {
        if (kind === "event" || kind === "attraction") {
          clearMarkers(clusterMarkers); setPoints([]); currentItems = []; loadComplete = true;

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
          data.items.forEach(item=>{const [x,y]=item.id.split(':').map(Number),size=data.cell_degrees;item.cellBounds=[x*size-180,y*size-90,(x+1)*size-180,(y+1)*size-90];});
          renderClusters(data.items);
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
            if (pages === 2 || data.next_cursor == null) {
              setPoints(currentItems);
              showStatus(`${fmt.format(currentItems.length)} мест${data.next_cursor == null ? "" : " · загружаем ещё…"}`);
            }
            if (data.next_cursor != null && data.next_cursor <= cursor) throw new Error("Invalid cursor");
            cursor = data.next_cursor;
          } while (cursor != null && pages < 2);
          loadComplete = cursor == null;
          if(!loadComplete) showStatus('Показаны первые 2 000 мест. Приблизьте карту или уточните тип.');
          renderGeography();revealExpansion(currentItems);
        }
      } catch (error) {
        if (error.name === "AbortError" || own !== sequence) return;
        loadComplete = false;
        showStatus("Не все места загружены. Двигайте карту или повторите.", true);

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
      const point = worldCenter();
      fittedZoom=overviewZoom();
      map.easeTo({ center: point, zoom: fittedZoom,
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
      if (map && center && (force || !userMoved)) {fittedZoom=overviewZoom();map.easeTo({ center,
        zoom: fittedZoom, duration: 0 });}
    }
    function renderRoute() {
      if (!mapReady || !map.getSource("trip-route")) return;
      const origin = options.origin, targets = options.targets || [];
      clearMarkers(targetMarkers);
      for (const place of targets.filter((t) => t.name && Number.isFinite(t.lat) && Number.isFinite(t.lon))) {
        const button = node("button", {class:"target-marker", type:"button", "aria-label":`Выбрать ${place.name}`,
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
      const cameraKey=JSON.stringify(points.map(p=>[p.lon,p.lat]));
      if(cameraKey===routeCameraKey)return;
      routeCameraKey=cameraKey;
      const duration = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 850;
      if (points.length === 1) {fittedZoom=overviewZoom();map.flyTo({ center: [points[0].lon, points[0].lat], zoom: fittedZoom, duration });}
      if (points.length > 1) {
        const regional = (settings.regional_overviews || []).find((view) => targets.length > 1 &&
          targets.every((target) => target.country === view.country) && Array.isArray(view.center) &&
          view.center.length === 2 && view.center.every(Number.isFinite) && Number.isFinite(view.zoom));
        const longitudes = points.map((p) => p.lon), span = Math.max(...longitudes) - Math.min(...longitudes);
        if (regional) {
          fittedZoom=overviewZoom();map.flyTo({center:regional.center, zoom:fittedZoom, duration});
        } else if (span > 65) {
          const radians = points.map((p) => p.lon * Math.PI / 180);
          const lon = Math.atan2(radians.reduce((a,v) => a + Math.sin(v), 0), radians.reduce((a,v) => a + Math.cos(v), 0)) * 180 / Math.PI;
          const lat = points.reduce((a,p) => a + p.lat, 0) / points.length;
          fittedZoom=overviewZoom();map.flyTo({center:[lon, lat], zoom:fittedZoom, duration});
        } else {
          fittedZoom=overviewZoom();
          const lon=points.reduce((sum,p)=>sum+p.lon,0)/points.length,lat=points.reduce((sum,p)=>sum+p.lat,0)/points.length;
          map.flyTo({center:[lon,lat],zoom:fittedZoom,duration});
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
        const earthPreparation = import(asset("globe-earth.mjs")).then(async (module) => ({
          module, image: await module.prepareEarthImage(asset("assets/earth-blue-marble-200410.jpg")),
        })).catch(() => null);
        const [module, mapCatalog, shapes, eventData, landmarkData, mapSettings, heritageData, countryData] = await Promise.all([
          import(asset("vendor/maplibre/maplibre-gl.mjs")),
          json(api("/api/map/catalog")), json(asset("countries.geojson")),
          json(asset("events.json")).catch(() => ({ events: [], checked_at: null })),
          json(asset("landmarks.json")).catch(() => ({landmarks:[]})),
          json(asset("map-settings.json")).catch(() => ({})),
          json(asset("heritage.json")).catch(() => ({sites:[]})),
          json(api("/api/map/countries")).catch(() => ({items:[]})),
        ]);
        lib = module; catalog = mapCatalog; countries = shapes;
        imageCredits=await json(asset('img/credits.json')).catch(()=>({}));
        settings = mapSettings;
        events = eventData.events || []; eventChecked = eventData.checked_at || "дата неизвестна";
        renderFeatured();
        countryNames = new Map((countryData.items || []).map((item) => [item.code,item.name]));
        landmarks = [...(landmarkData.landmarks || []), ...(heritageData.sites || []).map((item) => ({...item,heritage:true}))]
          .filter((p) => p.name && Number.isFinite(p.lat) && Number.isFinite(p.lon));
        map = new lib.Map({
          container: holder, center: countryCenter(manualCountry || initialCountry) || worldCenter(), zoom: overviewZoom(),
          canvasContextAttributes: {antialias: true}, pixelRatio:Math.min(devicePixelRatio||1,matchMedia("(max-width:700px)").matches?1.5:2),
          minZoom: -0.3, maxZoom: 16, attributionControl: false, cooperativeGestures: false,
          style: { version: 8, glyphs:"https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
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
                paint: { "line-color": "#19645d", "line-width": 2, "line-dasharray": [2, 2] } },
              { id: "catalog-points", type: "circle", source: "catalog-points",
                paint: { "circle-radius": 7, "circle-color": "#0e41d2",
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
        map.setSky({"sky-color":"#071b25", "horizon-color":"#396b70", "fog-color":"#0a2530",
          "atmosphere-blend":["interpolate",["linear"],["zoom"],0,0.75,5,0.6,7,0]});
        earthPreparation.then(async (prepared) => {
          if (map && prepared) {earthSurface=await prepared.module.addEarthSurface(map,prepared.image);earthReady=Boolean(earthSurface);earthSurface?.setStyle(globeMode==='atlas'?'map':'satellite');basemap?.setEarthReady(earthReady);}
        }).catch(() => { /* Existing vector globe remains available offline. */ });
        const {installBasemap}=await import(asset('globe-basemap.mjs'));
        basemap=installBasemap(map,state=>{mapNotice.hidden=state!=='error';surface.dataset.tiles=state;});
        basemap.set(theme(),globeMode);basemap.setEarthReady(earthReady);

        document.addEventListener('odin:theme',()=>basemap.set(theme(),globeMode));
        map.on('webglcontextlost',()=>{earthReady=false;mapReady=false;showStatus('Восстанавливаем глобус…');});
        map.on('webglcontextrestored',()=>setTimeout(()=>{
          try{earthSurface?.restore();three?.restore();earthReady=Boolean(earthSurface);mapReady=true;basemap.setEarthReady(earthReady);renderRoute();renderLandmarks();renderEvents();schedule();map.triggerRepaint();}
          catch(_){basemap.setEarthReady(false);showStatus('Поверхность восстанавливается. Карта доступна.',true);}
        },100));
        mapReady = true;
        fittedZoom=holder.clientWidth>0?map.getZoom():null;
        const resizeObserver=new ResizeObserver(()=>requestAnimationFrame(()=>{
          if(!map || !holder.clientWidth || !holder.clientHeight)return;
          map.resize();
          if(resetViewPending){
            resetViewPending=false;fittedZoom=overviewZoom();map.jumpTo({center:worldCenter(),zoom:fittedZoom});
          } else if(fittedZoom===null || Math.abs(map.getZoom()-fittedZoom)<.08){
            fittedZoom=overviewZoom();map.jumpTo({zoom:fittedZoom});
          }
        }));
        resizeObserver.observe(holder);
        map.on('remove',()=>resizeObserver.disconnect());
        map.on("movestart", (event) => {
          if (event.originalEvent) {userMoved = true;expansion=null;clearExpansion();}
          geographyMarkers.forEach(m=>m.getElement().hidden=true);
          closePopup();
          // Old markers can overlap while the camera moves; keep their visuals
          // but make only the freshly laid-out markers interactive.
          [...clusterMarkers, ...eventMarkers, ...landmarkMarkers, ...targetMarkers].forEach((marker) => { marker.getElement().inert = true; });
          if (controller) controller.abort();
          detailSequence++;
          sequence++;
        });
        const syncScope = () => {
          scope.hidden=map.getZoom()<=overviewZoom()+.1 && !options.targets?.length;
        };
        function syncTargetVisibility(){for(const marker of targetMarkers){const p=marker.getLngLat(),el=marker.getElement();el.hidden=!onVisibleHemisphere(p.lng,p.lat);el.inert=el.hidden||map.isMoving();}}
        map.on('move',()=>{for(const marker of [...landmarkMarkers,...eventMarkers,...targetMarkers,...clusterMarkers]){const p=marker.getLngLat();if(!onVisibleHemisphere(p.lng,p.lat))marker.getElement().hidden=true;}
          if(kind==='all'&&map.getZoom()<2.8)for(const marker of clusterMarkers){marker.getElement().hidden=true;marker.getElement().inert=true;}});
        map.on("moveend", () => { syncScope(); updateHint();syncTargetVisibility(); renderLandmarks(); renderEvents(); renderGeography(); schedule(); });
        syncScope();
        map.on("click", (event) => {
          const features = map.queryRenderedFeatures([[event.point.x-14,event.point.y-14],[event.point.x+14,event.point.y+14]], { layers: ["catalog-points"] });
          if (features.length) showOverlapping(features, event.lngLat);
        });
        map.on("click", "land", (event) => {
          if (map.queryRenderedFeatures([[event.point.x-14,event.point.y-14],[event.point.x+14,event.point.y+14]], {layers:["catalog-points"]}).length) return;
          const feature=event.features?.[0], code=feature?.properties?.code;
          const name=countryNames.get(code); if (!name) return;
          // A blank region is a navigation target, never an invisible destination.
          if(map.getZoom()>=9)return;
          closePopup();
          map.easeTo({center:[event.lngLat.lng,event.lngLat.lat],zoom:Math.min(10,map.getZoom()+2),duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:700});
        });
        map.on("mouseenter", "catalog-points", () => { holder.style.cursor = "pointer"; });
        map.on("mouseleave", "catalog-points", () => { holder.style.cursor = ""; });
        updateHint();  renderLandmarks(); renderEvents(); renderGeography(); renderRoute(); schedule();
      } catch (_) {
        if (map) { map.remove(); map = null; }
        await legacyFallback("Подробный каталог карты недоступен.");
      }
    }
    return {
      setData(catalogue, geography) {
        info = catalogue; land = geography;
        if (!map && !fallback) init();
        else if (fallback) fallback.setData(catalogue, geography);
      },
      draw(next = {}) {
        options = next;
        if (options.origin || options.targets?.length) resetViewPending=false;
        if (fallback) drawFallback(next);
        else if (mapReady) renderRoute();
      },
      setCountry(code, force = false) { setCountry(code, force); },
      setTripContext(summary){
        tripContext=summary||{};
        eventPeriod.querySelector('[value="trip"]').disabled=!tripContext.date_from;
        if(!eventPeriodChosen)eventWindow=tripContext.date_from?'trip':'soon';
        if(eventWindow==='trip'&&!tripContext.date_from)eventWindow='soon';
        eventPeriod.value=eventWindow;renderFeatured();if(mapReady){renderLandmarks();renderEvents();schedule();}
      },
      reset() {
        options={};routeCameraKey=null;userMoved=false;kind='all';filter.value='all';eventWindow='soon';eventPeriod.value='soon';eventPeriodChosen=false;tripContext={};eventPeriod.querySelector('[value="trip"]').disabled=true;renderFeatured();
        closePopup();expansion=null;clearExpansion();
        resetViewPending=true;
        if(mapReady) requestAnimationFrame(()=>{renderRoute();if(holder.clientWidth&&holder.clientHeight){resetViewPending=false;map.resize();world();}});
      },
      showPoint(point) {
        if (!map || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return;
        map.once("moveend", () => openPoint(point.id, point.lat, point.lon));
        map.flyTo({center:[point.lon,point.lat], zoom:12, duration:matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 800});
      },
      getView() { return map ? {center:map.getCenter().toArray(), zoom:map.getZoom(), projection:map.getProjection()?.type || null, earth:earthReady, surfaceLayer:Boolean(map.getLayer('earth-imagery')), modelLayer:Boolean(map.getLayer('discovery-3d')), mode:globeMode, detail:basemap?.getState()||"idle", theme:theme(), models:three?.getLoadedModels() || []} : null; },
      retry() { if (map) schedule(); },
      unavailable() { showStatus("Не удалось загрузить карту. Повторите подключение.", true); },
    };
  };
})();
