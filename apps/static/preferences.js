/* Presentation preferences only; these do not change the agent's trip state. */
window.createPreferences = function createPreferences(map) {
  const currency = document.getElementById("currency");
  const note = document.getElementById("exchange-note");
  const original = new WeakMap();
  let rates = null;
  const euro = new Set("AD AT BE CY DE EE ES FI FR GR HR IE IT LT LU LV MC ME MT NL PT SI SK SM VA".split(" "));
  const read = (key) => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };
  const currencyFor = (code) => euro.has(code) ? "EUR" : code === "US" ? "USD" : "RUB";
  let manualCurrency = read("odin.currency");

  function convert(value) {
    if (currency.value === "RUB" || !rates || !rates.rub_per_unit[currency.value]) return null;
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency: currency.value,
      maximumFractionDigits: 0 }).format(value / rates.rub_per_unit[currency.value]);
  }
  function apply() {
    document.querySelectorAll("#view, #conditions, #trip-summary-line, #log .bot, #say").forEach((root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((node) => {
        if(node.parentElement?.closest('[data-rub-price]')) return;
        const cached = original.get(node);
        const text = cached && node.nodeValue === cached.rendered ? cached.source : node.nodeValue;
        node.nodeValue = text.replace(/((?:\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d+)(?:[,.]\d{1,2})?)\s*₽/g, (match, amount) => {
          const value = Number(amount.replace(/[\s\u00a0\u202f]/g, "").replace(",", "."));
          const changed = convert(value); return changed ? `≈ ${changed}` : match;
        });
        original.set(node, {source:text,rendered:node.nodeValue});
      });
    });
    document.querySelectorAll("[data-rub-price]").forEach((node) => {
      if (!node.dataset.originalLabel) node.dataset.originalLabel = node.textContent;
      const changed = convert(Number(node.dataset.rubPrice));
      node.textContent = changed ? `≈ ${changed}` : node.dataset.originalLabel;
    });
    currency.title = currency.value === "RUB" ? "Валюта демонстрационных цен" :
      "Примерный пересчёт; дата курса указана внизу страницы. Бюджет в диалоге — в рублях";
    note.hidden = currency.value === "RUB" || !rates;
  }
  currency.addEventListener("change", () => { manualCurrency = currency.value; save("odin.currency", manualCurrency); apply(); });
  if (["RUB", "EUR", "USD"].includes(manualCurrency)) currency.value = manualCurrency;
  Promise.all([
    fetch("/api/visitor-country", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).catch(() => null),
    fetch("/static/exchange-rates.json").then((r) => r.json()).catch(() => null),
  ]).then(([location, exchange]) => {
    rates = exchange;
    const selected = location?.country_code;
    if (selected) {
      map.setCountry(selected, false);
      if (!manualCurrency) currency.value = currencyFor(selected);
    }
    if (rates) {
      note.append("≈ ", Object.assign(document.createElement("a"),
        { href: rates.url, target: "_blank", rel: "noopener", textContent: `курс ЦБ на ${rates.date.split("-").reverse().join(".")}` }), " · бюджет в ₽");
    } else {
      currency.value = "RUB"; currency.disabled = true;
      note.textContent = "Курс недоступен; суммы показаны в рублях.";
    }
    apply();
  }).catch(() => { currency.value = "RUB"; currency.disabled = true; });
  return { apply, currency: () => currency.value };
};
