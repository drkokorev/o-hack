/* Standalone map: the host supplies a catalog, geographic shapes and a selection callback. */
window.createTripMap = function createTripMap({ container, onChoose }) {
  let info = null, land = null;
  container.classList.add("trip-map");
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined && child !== false) node.append(child);
    return node;
  }
  function svg(tag, attrs = {}, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text) node.textContent = text;
    return node;
  }
  /* Карта: контуры суши Natural Earth, направления каталога, дуга маршрута. */
  const K = 0.82, LON0 = -180, LAT0 = 85;
  const px = (lon, lat) => [(lon - LON0) * K, LAT0 - lat];
  function arcPath(a, b) {
    const [x1, y1] = px(a.lon, a.lat), [x2, y2] = px(b.lon, b.lat);
    const d = Math.hypot(x2 - x1, y2 - y1) || 1;
    const nx = -(y2 - y1) / d, ny = (x2 - x1) / d;          // нормаль к отрезку
    const sgn = ny > 0 ? -1 : 1;                              // дуга всегда выгибается вверх
    const cx = (x1 + x2) / 2 + sgn * nx * d * 0.22, cy = (y1 + y2) / 2 + sgn * ny * d * 0.22;
    return `M${x1.toFixed(2)},${y1.toFixed(2)} Q${cx.toFixed(2)},${cy.toFixed(2)} ${x2.toFixed(2)},${y2.toFixed(2)}`;
  }
  const FULL = { x: 0, y: 0, w: (180 - LON0) * K, h: 145 };           // весь мир
  const HOME = { x: (5 - LON0) * K, y: 10, w: 165 * K, h: 95 };        // Европа, Азия, Африка
  let worldView = false, lastMapOptions = {};
  function fitView(points) {
    if (!points.length) return HOME;
    const xs = points.map((p) => px(p.lon, p.lat)[0]), ys = points.map((p) => px(p.lon, p.lat)[1]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const ratio = HOME.w / HOME.h;
    let w = Math.max(x1 - x0, 36) * 1.5, h = Math.max(y1 - y0, 20) * 1.6;
    if (w / h < ratio) w = h * ratio; else h = w / ratio;
    if (w > FULL.w) { w = FULL.w; h = w / ratio; }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2 - h * 0.06;
    const x = Math.min(Math.max(cx - w / 2, 0), FULL.w - w), y = Math.min(Math.max(cy - h / 2, 0), FULL.h - h);
    return { x, y, w, h };
  }
  function drawMap(opts = {}, keepView = false) {
    if (!land || !info) return;
    if (!keepView) worldView = false;
    lastMapOptions = opts;
    const pts = [...(opts.origin ? [opts.origin] : []), ...(opts.targets || [])];
    const v = worldView ? FULL : fitView(pts);
    const root = svg("svg", { viewBox: `${v.x.toFixed(2)} ${v.y.toFixed(2)} ${v.w.toFixed(2)} ${v.h.toFixed(2)}`, role: "group", "aria-label": "Выберите направление на карте" });
    root.style.setProperty("--z", (v.w / HOME.w).toFixed(3));
    for (let lat = -60; lat <= 60; lat += 30) {
      const [x1, y1] = px(-180, lat), [x2, y2] = px(180, lat);
      root.append(svg("path", { class: "graticule", d: `M${x1},${y1} L${x2},${y2}` }));
    }
    for (let lon = -150; lon <= 180; lon += 30) {
      const [x1, y1] = px(lon, 85), [x2, y2] = px(lon, -60);
      root.append(svg("path", { class: "graticule", d: `M${x1},${y1} L${x2},${y2}` }));
    }
    for (const feature of land.features) {
      const path = feature.geometry.coordinates.map((ring) => ring.map(([lon, lat], index) => {
        const [x, y] = px(lon, lat); return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
      }).join(" ") + " Z").join(" ");
      root.append(svg("path", { class: "land", d: path }));
    }
    const markers = [];
    const chooseOnMap = (p) => {
      const selected = info.places.find((place) => p.id ? place.id === p.id :
        place.name === p.name && Math.abs(place.lat - p.lat) < 0.001 && Math.abs(place.lon - p.lon) < 0.001) || p;
      const choice = el("div", { class: "map-choice", role: "status" }, el("b", {}, p.name),
        el("button", { type: "button", onclick: () => onChoose(selected) }, "Хочу сюда"));
      container.querySelector(".map-choice")?.remove();
      container.append(choice);
    };
    const bindMarker = (marker, place) => {
      marker.setAttribute("tabindex", markers.length ? "-1" : "0");
      markers.push(marker);
      marker.addEventListener("click", () => chooseOnMap(place));
      marker.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); chooseOnMap(place); }
        if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
          event.preventDefault();
          const delta = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
          const next = markers[(markers.indexOf(marker) + delta + markers.length) % markers.length];
          marker.setAttribute("tabindex", "-1"); next.setAttribute("tabindex", "0"); next.focus();
        }
      });
    };
    const targets = opts.targets || [];
    for (const p of info.places) {
      const [x, y] = px(p.lon, p.lat);
      if (x < v.x || x > v.x + v.w || y < v.y || y > v.y + v.h || targets.some((t) => t.name === p.name)) continue;
      const marker = svg("g", { class: "map-point", role: "button", "aria-label": `Выбрать ${p.name}` });
      marker.append(svg("circle", { cx: x, cy: y, r: 2.3, fill: "transparent" }), svg("circle", { class: "place", cx: x, cy: y, r: 0.55 }));
      bindMarker(marker, p);
      root.append(marker);
    }
    const z = v.w / HOME.w;
    const toDraw = [];
    if (opts.origin || targets.length) {
      const [ox, oy] = opts.origin ? px(opts.origin.lon, opts.origin.lat) : [0, 0];
      if (opts.origin) {
      for (const t of targets) {
        const path = svg("path", { class: "arc" + (targets.length > 1 ? " dim" : ""), d: arcPath(opts.origin, t) });
        root.append(path); if (targets.length === 1) toDraw.push(path);
      }
      root.append(svg("circle", { class: "halo", cx: ox, cy: oy, r: 1.8 * z }), svg("circle", { class: "origin", cx: ox, cy: oy, r: 0.95 * z }),
        svg("text", { class: "label", x: ox - 1.6 * z, y: oy - 1.6 * z, "text-anchor": "end" }, opts.origin.name));
      }
      const placed = opts.origin ? [[ox, oy - 1.6 * z]] : [];
      targets.forEach((t, i) => {
        const [x, y] = px(t.lon, t.lat);
        const right = x >= ox || targets.length === 1;
        let ly = y + 0.8 * z;
        while (placed.some(([px2, py2]) => Math.abs(px2 - x) < 14 * z && Math.abs(py2 - ly) < 2.8 * z)) ly += 2.9 * z;
        placed.push([x, ly]);
        const marker = svg("g", { class: "map-point", role: "button", "aria-label": `Выбрать ${t.name}` });
        marker.append(svg("circle", { cx: x, cy: y, r: 3 * z, fill: "transparent" }), svg("circle", { class: "pin", cx: x, cy: y, r: (targets.length > 1 ? 1.45 : 1.15) * z }));
        bindMarker(marker, t);
        root.append(marker);
        if (targets.length > 1) root.append(svg("text", { class: "badge", x, y: y + 0.05 * z }, String(i + 1)));
        root.append(svg("text", { class: "label", x: x + (right ? 2.2 : -2.2) * z, y: ly, "text-anchor": right ? "start" : "end" }, t.name));
      });
    }
    const scope = el("button", { type: "button", class: "map-scope", "aria-pressed": String(worldView),
      onclick: () => { worldView = !worldView; drawMap(lastMapOptions, true); container.querySelector(".map-scope").focus(); } },
      worldView ? "Приблизить" : "Весь мир");
    const directions = [...info.places].sort((a, b) => a.name.localeCompare(b.name, "ru"));
    const select = el("select", { "aria-label": "Выбрать направление из списка", onchange: (event) => {
      const place = directions.find((item) => item.id === event.target.value);
      if (place) { chooseOnMap(place); container.querySelector(".map-choice button").focus(); }
    } }, el("option", { value: "", disabled: true, selected: true }, "Выбрать из списка"),
    directions.map((place) => el("option", { value: place.id }, place.name)));
    const footer = el("div", { class: "map-footer" }, el("span", {}, "Направления для примера"), select);
    container.replaceChildren(root, el("span", { class: "map-hint" }, "Выберите отмеченное направление"), scope, footer);
    for (const path of toDraw) {
      const len = path.getTotalLength();
      path.style.strokeDasharray = len; path.style.strokeDashoffset = len;
      requestAnimationFrame(() => requestAnimationFrame(() => { path.classList.add("draw"); path.style.strokeDashoffset = 0; }));
    }
  }

  return {
    setData(catalog, geography) { info = catalog; land = geography; },
    draw: drawMap,
  };
};
